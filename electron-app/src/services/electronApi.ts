import { AnalysisResult, ExtractedData } from '../types';
import { Bank } from '../shared/constants/banks';
import { webApi } from './webApi';

// ── Формы запросов/ответов backend (snake_case — как отдаёт Python/preload) ──

export interface GenerateDocumentRequest {
  template_type: string;
  data: Record<string, unknown>;
}

/** Ответ /generate-document. Один документ (document_id/file_path) ИЛИ пакет
 *  (documents/document_ids/count). Ключи snake_case — приходят от backend как есть. */
export interface GenerateDocumentResult {
  success: boolean;
  document_id?: string;
  file_path?: string;
  documents?: Record<string, unknown>;
  document_ids?: string[];
  count?: number;
  error?: string;
  /** Выбранные акты, которые сгенерировать не удалось: нет файла шаблона либо
   *  ветки маппинга. Генерация при этом успешна для остальных актов. */
  warnings?: string[];
}

export interface DownloadAllDocumentsRequest {
  /** Список id через запятую. */
  document_ids: string;
  /** Пустая строка → диалог выбора места сохранения. */
  download_path: string;
}

export interface DownloadResult {
  success: boolean;
  filePath?: string;
  error?: string;
}

// ── OCR-конвертер PDF→DOCX (sidecar; все HTTP-вызовы идут через прокси
//    /convert/* нашего бэкенда — порт конвертера наружу не течёт) ──

/** Результат классификации PDF конвертером (POST /convert/analyze). */
export interface ConvertClassifyResult {
  /** Рекомендация конвертера: 'scan' — образ без текстового слоя, 'native' — текст выделяется. */
  suggested?: 'scan' | 'native';
  confidence?: string;
  /** Человекочитаемое объяснение рекомендации (показываем пользователю). */
  reason?: string;
  [key: string]: unknown;
}

/** Флаги скан-режима конвертера (form-поля POST /convert/scan). */
export interface ConvertScanFlags {
  no_highlight?: boolean;
  word_order?: boolean;
  iim?: boolean;
  ink_bold?: boolean;
  ocr_preprocess?: boolean;
}


/** Одна подсказка теневого LLM-слоя. Ничего не подставляет — только сигнал. */
export interface LlmHint {
  /** Ключ поля формы: `courtName`, `debtors[0].inn`, `mortgageProperties[1].address`. */
  field: string;
  /** Человекочитаемое имя поля для текста подсказки. */
  label: string;
  /** Блок формы, к которому поле относится. */
  block: string;
  /** Что дал обычный разбор. */
  regexValue: string;
  /** Что нашла LLM. Пусто у замечаний о правдоподобии: там сравнивать не с чем. */
  llmValue: string;
  agrees: boolean;
  /**
   * Короткое объяснение, почему значение выглядит неправдоподобным.
   * Есть только у замечаний блока `sanity` — там модель не предлагает
   * альтернативу, а говорит, что значение не похоже на своё поле.
   */
  reason?: string;
}

/** Состояние задачи LLM-проверки (GET /llm/hints/{job_id}). */
export interface LlmHintsStatus {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled';
  blocksDone: number;
  blocksTotal: number;
  lastBlock?: string | null;
  /** Растёт по мере готовности блоков, а не приходит целиком в конце. */
  hints: LlmHint[];
  error?: string | null;
}

/** Статус задачи конвертации (GET /convert/status/{job_id}). */
export interface ConvertJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  /** Человекочитаемая стадия («OCR», «Сборка DOCX», …). */
  stage?: string;
  /** 0..1 — грубые отметки прогресса. */
  progress?: number;
  filename?: string;
  error?: string | null;
}

/** Результат запуска sidecar-процесса конвертера. */
export interface ConverterStartResult {
  ok: boolean;
  /** true — сервис уже был запущен снаружи (не наш процесс). */
  external?: boolean;
  error?: string;
}

export interface ConverterProcessStatus {
  running: boolean;
  healthy: boolean;
}

/** Одна строка секции предпросмотра: текст + глобальный индекс в плоском тексте. */
export interface DocxSectionLine {
  text: string;
  index: number;
}

/** Секция посекционного предпросмотра (представление строк extract_text). */
export interface DocxSection {
  id: string;
  title: string;
  lines: DocxSectionLine[];
}

/** Ответ /docx-text: плоский текст + его секционное представление. */
export interface DocxTextResult {
  success: boolean;
  text: string;
  /** Может отсутствовать (не-DOCX/старый бэкенд) — тогда fallback на text. */
  sections?: DocxSection[];
}

/**
 * Контракт моста preload.js → renderer (contextBridge `electronAPI`).
 * Единственная точка правды о том, что доступно во `window.electronAPI`.
 */
export interface ElectronAPI {
  isReady: () => boolean;
  selectFile: () => Promise<string | null>;
  saveFile: (defaultName: string) => Promise<string | null>;
  readFile: (filePath: string) => Uint8Array;
  analyzeDocument: (input: File | string) => Promise<AnalysisResult>;
  generateDocument: (req: GenerateDocumentRequest) => Promise<GenerateDocumentResult>;
  getTemplates: () => Promise<unknown>;
  /** Единый реестр банков-кредиторов с бэкенда (GET /banks). */
  getBanks: () => Promise<Bank[]>;
  downloadDocument: (documentId: string) => Promise<DownloadResult>;
  downloadAllDocuments: (data: DownloadAllDocumentsRequest) => Promise<DownloadResult>;
  getDownloadPaths: () => Promise<unknown>;
  getExtractedData: () => Promise<ExtractedData | null>;
  toggleDevTools: () => Promise<void> | void;

  // ── Convert-шаг (PDF → OCR-конвертер → предпросмотр → анализ) ──
  /** Анализ уже извлечённого текста (правленого в предпросмотре) — POST /analyze-text. */
  analyzeText: (text: string, pageCount?: number) => Promise<AnalysisResult>;
  /** Классификация PDF: скан или нативный. */
  convertAnalyze: (file: File) => Promise<ConvertClassifyResult>;
  /** Конвертация скана (Docling+Tesseract+LLM), возвращает job_id. */
  convertScan: (file: File, flags?: ConvertScanFlags) => Promise<{ job_id: string }>;
  /** Конвертация нативного PDF (pdf2docx), возвращает job_id. */
  convertNative: (file: File) => Promise<{ job_id: string }>;
  /** Поллинг статуса задачи конвертации. */
  convertStatus: (jobId: string) => Promise<ConvertJobStatus>;
  /** Готовый DOCX задачи (оригинальная вёрстка; «Скачать DOCX»). */
  convertDownload: (jobId: string) => Promise<Blob>;
  /** Текст DOCX тем же экстрактором, что анализ (+ секции для предпросмотра). */
  docxText: (docx: Blob) => Promise<DocxTextResult>;
  /** Вставка правленого текста в оригинальную вёрстку DOCX («Скачать с правками»). */
  docxApplyEdits: (docx: Blob, editedText: string) => Promise<Blob>;
  /** true — процессом конвертера управляет Electron (в браузере он запущен постоянно). */
  converterManaged: boolean;
  /** Запуск sidecar-процесса конвертера (ждёт /health, холодный старт — до минут). */
  converterStart: () => Promise<ConverterStartResult>;
  /** Остановка sidecar-процесса (освобождает память после convert-шага). */
  converterStop: () => Promise<{ ok: boolean }>;
  converterStatus: () => Promise<ConverterProcessStatus>;
  /** Версия приложения (десктоп — app.getVersion(); браузер — REACT_APP_VERSION). */
  getAppVersion: () => Promise<string>;

  // --- Офлайн-обновление с флешки (только десктоп; в браузере отсутствуют) ---
  /** Выбрать папку SberAct-Update на флешке вручную. */
  updatePickSource?: () => Promise<{ ok: boolean; path?: string }>;
  /** Автопоиск папки обновления на съёмных дисках. */
  updateAutoDetect?: () => Promise<{ ok: boolean; path: string | null }>;
  // ── Теневые LLM-подсказки по полям (ипотека) ──
  /** Прогреть модель заранее; «лучшее усилие», ошибки проглатываются. */
  llmWarmup?: () => Promise<void>;
  /** Поставить задачу проверки. Сайдкар поднимает backend сам. */
  llmHintsStart?: (rawText: string, regex: Record<string, string>,
    mortgageKind?: string) => Promise<{ job_id: string }>;
  /** Состояние задачи; `hints` растёт по мере готовности блоков. */
  llmHintsStatus?: (jobId: string) => Promise<LlmHintsStatus>;
  /** Отменить задачу — она занимает почти все ядра, бросать её нельзя. */
  llmHintsCancel?: (jobId: string) => Promise<void>;

  /** Проверить оба канала обновления (app+backend и converter). */
  updateCheck?: (chosenPath?: string) => Promise<UpdateCheckResult>;
  /** Скачать app-обновление в staging electron-updater. */
  updateDownload?: () => Promise<{ ok: boolean; error?: string }>;
  /** Применить: converter-sync + установка/перезапуск. */
  updateApply?: (opts: UpdateApplyOptions) => Promise<{ ok: boolean; restarting?: boolean; error?: string }>;
  /** Прогресс скачивания app-обновления. Возвращает функцию отписки. */
  onUpdateProgress?: (cb: (p: UpdateDownloadProgress) => void) => () => void;
  /** Прогресс копирования файлов конвертера. Возвращает функцию отписки. */
  onConverterProgress?: (cb: (p: { done: number; total: number }) => void) => () => void;
  /** Ошибки апдейтера. Возвращает функцию отписки. */
  onUpdateError?: (cb: (message: string) => void) => () => void;
}

/** Состояние одного канала обновления (app или converter). */
export interface UpdateChannelState {
  available: boolean;
  version?: string | null;
  currentVersion?: string | null;
  installedVersion?: string | null;
  filesChanged?: number;
  filesDeleted?: number;
  bytes?: number;
  error?: string;
}

/** Внутренний план converter-sync (передаётся обратно в updateApply как есть). */
export interface ConverterSyncPlan {
  toCopy: Array<{ path: string; sha256?: string; size?: number }>;
  toDelete: string[];
  flashManifestPath: string;
}

export interface UpdateCheckResult {
  ok: boolean;
  error?: string;
  source?: string;
  app: UpdateChannelState;
  converter: UpdateChannelState;
  _converterPlan?: ConverterSyncPlan | null;
}

export interface UpdateApplyOptions {
  appDownloaded: boolean;
  converterPlan?: ConverterSyncPlan | null;
}

export interface UpdateDownloadProgress {
  percent: number;
  transferred: number;
  total: number;
  bytesPerSecond: number;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
    /** Фолбэк-функция открытия DevTools из консоли (preload). */
    openDevTools?: () => void;
  }
}

/** Доступен ли настоящий мост Electron (десктоп). В браузере — false. */
export const hasElectronAPI = (): boolean =>
  typeof window !== 'undefined' && !!window.electronAPI;

/**
 * Возвращает типизированный `electronAPI` или кидает понятную ошибку, если мост
 * не инициализирован. Только для электрон-специфичных вещей.
 */
export const getElectronAPI = (): ElectronAPI => {
  const api = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!api) {
    throw new Error(
      'Electron API не доступен. Убедитесь, что приложение запущено в Electron.'
    );
  }
  return api;
};

/**
 * Активный API документа: мост Electron (десктоп) либо веб-адаптер на fetch
 * (браузер). Единая точка для операций, которые должны работать в обоих режимах.
 */
export const getApi = (): ElectronAPI =>
  typeof window !== 'undefined' && window.electronAPI ? window.electronAPI : webApi;

// ── Тонкие обёртки: единый вход для компонентов (работают и в Electron, и в браузере) ──

export const analyzeDocument = (input: File | string): Promise<AnalysisResult> =>
  getApi().analyzeDocument(input);

export const generateDocument = (
  req: GenerateDocumentRequest
): Promise<GenerateDocumentResult> => getApi().generateDocument(req);

export const downloadDocument = (documentId: string): Promise<DownloadResult> =>
  getApi().downloadDocument(documentId);

export const downloadAllDocuments = (
  data: DownloadAllDocumentsRequest
): Promise<DownloadResult> => getApi().downloadAllDocuments(data);

export const getExtractedData = (): Promise<ExtractedData | null> =>
  getApi().getExtractedData();

export const selectFile = (): Promise<string | null> => getApi().selectFile();

export const getBanks = (): Promise<Bank[]> => getApi().getBanks();

// ── Convert-шаг ──

export const analyzeText = (text: string, pageCount?: number): Promise<AnalysisResult> =>
  getApi().analyzeText(text, pageCount);

export const convertAnalyze = (file: File): Promise<ConvertClassifyResult> =>
  getApi().convertAnalyze(file);

export const convertScan = (
  file: File,
  flags?: ConvertScanFlags
): Promise<{ job_id: string }> => getApi().convertScan(file, flags);

export const convertNative = (file: File): Promise<{ job_id: string }> =>
  getApi().convertNative(file);

export const convertStatus = (jobId: string): Promise<ConvertJobStatus> =>
  getApi().convertStatus(jobId);

export const convertDownload = (jobId: string): Promise<Blob> =>
  getApi().convertDownload(jobId);

export const docxText = (docx: Blob): Promise<DocxTextResult> =>
  getApi().docxText(docx);

export const docxApplyEdits = (docx: Blob, editedText: string): Promise<Blob> =>
  getApi().docxApplyEdits(docx, editedText);

/** true — UI может (и должен) управлять процессом конвертера (десктоп). */
export const isConverterManaged = (): boolean => getApi().converterManaged;

// Жизненный цикл конвертера — ВСЕГДА через backend, а не через мост Electron.
// Раньше в Electron он шёл по IPC в ManagedService (main.js), и владелец процесса
// расходился с тем, кто видит активность: конвертация идёт fetch'ем в backend мимо
// Electron, поэтому сторож простоя (CONVERTER_IDLE_TIMEOUT_S) не мог погасить
// процесс, запущенный не им, — конвертер держал ~3.5 ГБ до закрытия приложения.
// Единый владелец = backend: один код старта/остановки/простоя на оба режима.
export const converterStart = (): Promise<ConverterStartResult> => webApi.converterStart();

export const converterStop = (): Promise<{ ok: boolean }> => webApi.converterStop();

export const converterStatus = (): Promise<ConverterProcessStatus> => webApi.converterStatus();

// ── Теневые LLM-подсказки ──
// Тоже всегда через webApi, по той же причине, что и конвертер: жизненным
// циклом сайдкара владеет backend, а не интерфейс.
export const llmWarmup = (): Promise<void> => webApi.llmWarmup!();

export const llmHintsStart = (
  rawText: string,
  regex: Record<string, string>,
  mortgageKind?: string,
): Promise<{ job_id: string }> => webApi.llmHintsStart!(rawText, regex, mortgageKind);

export const llmHintsStatus = (jobId: string): Promise<LlmHintsStatus> =>
  webApi.llmHintsStatus!(jobId);

export const llmHintsCancel = (jobId: string): Promise<void> => webApi.llmHintsCancel!(jobId);

/** Версия приложения (десктоп — из main-процесса; браузер — REACT_APP_VERSION). */
export const getAppVersion = (): Promise<string> => getApi().getAppVersion();

// ── Офлайн-обновление с флешки (только десктоп) ──
export const updateCheck = (chosenPath?: string): Promise<UpdateCheckResult> =>
  getElectronAPI().updateCheck!(chosenPath);
export const updatePickSource = (): Promise<{ ok: boolean; path?: string }> =>
  getElectronAPI().updatePickSource!();
export const updateAutoDetect = (): Promise<{ ok: boolean; path: string | null }> =>
  getElectronAPI().updateAutoDetect!();
export const updateDownload = (): Promise<{ ok: boolean; error?: string }> =>
  getElectronAPI().updateDownload!();
export const updateApply = (
  opts: UpdateApplyOptions
): Promise<{ ok: boolean; restarting?: boolean; error?: string }> =>
  getElectronAPI().updateApply!(opts);
export const onUpdateProgress = (cb: (p: UpdateDownloadProgress) => void): (() => void) =>
  getElectronAPI().onUpdateProgress!(cb);
export const onConverterProgress = (cb: (p: { done: number; total: number }) => void): (() => void) =>
  getElectronAPI().onConverterProgress!(cb);
export const onUpdateError = (cb: (message: string) => void): (() => void) =>
  getElectronAPI().onUpdateError!(cb);

/** Переключение DevTools с фолбэком на глобальную openDevTools (как было в App). */
export const toggleDevTools = (): void => {
  const api = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (api && typeof api.toggleDevTools === 'function') {
    api.toggleDevTools();
  } else if (typeof window !== 'undefined' && typeof window.openDevTools === 'function') {
    window.openDevTools();
  } else {
    console.warn('DevTools API not available');
  }
};
