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
