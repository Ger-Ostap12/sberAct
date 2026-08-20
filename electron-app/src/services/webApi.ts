import { AnalysisResult, ExtractedData } from '../types';
import {
  ElectronAPI,
  GenerateDocumentRequest,
  GenerateDocumentResult,
  DownloadAllDocumentsRequest,
  DownloadResult,
  ConvertClassifyResult,
  ConvertScanFlags,
  ConvertJobStatus,
  ConverterStartResult,
  ConverterProcessStatus,
  DocxTextResult,
  LlmHintsStatus,
} from './electronApi';

// Веб-реализация того же контракта, что и мост Electron (preload). Позволяет
// открывать приложение в обычном браузере: все операции идут прямыми fetch к
// backend (CORS на бэкенде открыт). Отличия от десктопа: скачивание падает в
// папку «Загрузки» браузера (без нативного диалога), выбор файла по пути недоступен.

const BASE_URLS = ['http://127.0.0.1:8000', 'http://localhost:8000', 'http://wsl.localhost:8000'];

/** Хост, ответивший первым: дальше ходим сразу в него, без перебора. */
let liveBase: string | null = null;

/** Сброс запомненного хоста — для тестов. */
export function resetLiveBase(): void {
  liveBase = null;
}

/**
 * Запрос к backend с перебором хостов.
 *
 * Перебор идёт ТОЛЬКО по сетевому отказу (fetch отклонён). HTTP-ошибка — это
 * ответ живого хоста, и она возвращается как есть: раньше 502 уводил перебор
 * дальше, наружу летела ошибка от последней базы (wsl.localhost), а настоящая
 * причина терялась — в консоли это выглядело как три разных сбоя вместо одного.
 *
 * Повтор с тем же options безопасен: FormData/Blob — не потоки, fetch
 * сериализует тело заново на каждую попытку.
 */
async function fetchBackend(pathname: string, options?: RequestInit): Promise<Response> {
  // Живой хост — первым, но остальные держим в запасе: он мог отвалиться.
  const ordered = liveBase
    ? [liveBase, ...BASE_URLS.filter((b) => b !== liveBase)]
    : [...BASE_URLS];
  let lastError: unknown;

  for (const base of ordered) {
    // ДВЕ попытки на хост. После простоя браузер переиспользует keep-alive
    // соединение, которое uvicorn уже закрыл (timeout_keep_alive), и запрос падает
    // без ответа — в консоли это выглядит как «CORS policy: No
    // Access-Control-Allow-Origin», хотя CORS исправен и backend жив. Сам браузер
    // повторяет только идемпотентные запросы, а /converter/start — POST, поэтому
    // повтор нужен здесь. Вторая попытка открывает свежий сокет.
    for (let attempt = 0; attempt < 2; attempt++) {
      let res: Response;
      try {
        res = await fetch(`${base}${pathname}`, options);
      } catch (e) {
        lastError = e; // сетевой отказ: вторая попытка, затем следующий хост
        continue;
      }
      liveBase = base;
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      return res;
    }
    if (base === liveBase) liveBase = null; // хост молчит дважды — ищем заново
  }

  throw lastError instanceof Error ? lastError : new Error('Backend недоступен');
}

/** Инициирует скачивание blob в браузере (папка «Загрузки»). */
function triggerBrowserDownload(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Достаёт имя файла из Content-Disposition, иначе fallback. */
function fileNameFromResponse(res: Response, fallback: string): string {
  const cd = res.headers.get('Content-Disposition') || '';
  const match = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1]) : fallback;
}

const notSupported = (method: string) => () => {
  throw new Error(`${method} недоступен в браузере (только в десктоп-версии Electron)`);
};

export const webApi: ElectronAPI = {
  isReady: () => true,

  // Нативные диалоги недоступны в браузере: путь не выбираем, загрузка идёт через <input type=file>.
  selectFile: async () => null,
  saveFile: async () => null,
  readFile: notSupported('readFile') as unknown as ElectronAPI['readFile'],

  analyzeDocument: async (input: File | string): Promise<AnalysisResult> => {
    if (typeof input === 'string') {
      throw new Error('В браузере анализ по пути к файлу недоступен — выберите файл через диалог загрузки');
    }
    const formData = new FormData();
    formData.append('document', input, input.name);
    const res = await fetchBackend('/analyze-document', { method: 'POST', body: formData });
    return res.json();
  },

  generateDocument: async (req: GenerateDocumentRequest): Promise<GenerateDocumentResult> => {
    const res = await fetchBackend('/generate-document', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return res.json();
  },

  getTemplates: async () => {
    const res = await fetchBackend('/templates');
    return res.json();
  },

  getBanks: async () => {
    const res = await fetchBackend('/banks');
    return res.json();
  },

  downloadDocument: async (documentId: string): Promise<DownloadResult> => {
    try {
      const res = await fetchBackend(`/download-document/${documentId}`);
      const blob = await res.blob();
      triggerBrowserDownload(blob, fileNameFromResponse(res, `Судебный_акт_${documentId}.docx`));
      return { success: true };
    } catch (e) {
      return { success: false, error: e instanceof Error ? e.message : 'Ошибка скачивания' };
    }
  },

  downloadAllDocuments: async (data: DownloadAllDocumentsRequest): Promise<DownloadResult> => {
    try {
      const res = await fetchBackend('/download-all-documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const blob = await res.blob();
      triggerBrowserDownload(blob, fileNameFromResponse(res, 'generated_documents.zip'));
      return { success: true };
    } catch (e) {
      return { success: false, error: e instanceof Error ? e.message : 'Ошибка скачивания' };
    }
  },

  getDownloadPaths: async () => ({}),
  getExtractedData: async (): Promise<ExtractedData | null> => null,
  toggleDevTools: () => {
    /* В браузере DevTools открывается клавишей F12 — no-op. */
  },

  // ── Convert-шаг: те же /convert/*-прокси и /analyze-text, что и в Electron ──

  analyzeText: async (text: string, pageCount?: number): Promise<AnalysisResult> => {
    const res = await fetchBackend('/analyze-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, page_count: pageCount ?? null }),
    });
    return res.json();
  },

  convertAnalyze: async (file: File): Promise<ConvertClassifyResult> => {
    const formData = new FormData();
    formData.append('file', file, file.name);
    const res = await fetchBackend('/convert/analyze', { method: 'POST', body: formData });
    return res.json();
  },

  convertScan: async (file: File, flags?: ConvertScanFlags): Promise<{ job_id: string }> => {
    const formData = new FormData();
    formData.append('file', file, file.name);
    // Флаги — form-поля конвертера; шлём только явно заданные (дефолты — его)
    Object.entries(flags ?? {}).forEach(([key, value]) => {
      if (value !== undefined) formData.append(key, String(value));
    });
    const res = await fetchBackend('/convert/scan', { method: 'POST', body: formData });
    return res.json();
  },

  convertNative: async (file: File): Promise<{ job_id: string }> => {
    const formData = new FormData();
    formData.append('file', file, file.name);
    const res = await fetchBackend('/convert/native', { method: 'POST', body: formData });
    return res.json();
  },

  convertStatus: async (jobId: string): Promise<ConvertJobStatus> => {
    const res = await fetchBackend(`/convert/status/${encodeURIComponent(jobId)}`);
    return res.json();
  },

  convertDownload: async (jobId: string): Promise<Blob> => {
    const res = await fetchBackend(`/convert/download/${encodeURIComponent(jobId)}`);
    return res.blob();
  },

  docxText: async (docx: Blob): Promise<DocxTextResult> => {
    const formData = new FormData();
    formData.append('document', docx, 'converted.docx');
    const res = await fetchBackend('/docx-text', { method: 'POST', body: formData });
    return res.json();
  },

  docxApplyEdits: async (docx: Blob, editedText: string): Promise<Blob> => {
    const formData = new FormData();
    formData.append('document', docx, 'converted.docx');
    formData.append('edited_text', editedText);
    const res = await fetchBackend('/docx-apply-edits', { method: 'POST', body: formData });
    return res.blob();
  },

  // В браузере процессом конвертера управляет БЭКЕНД (/converter/*): браузер
  // сам процессы запускать не умеет, а требование — «только фронт + бек»,
  // без третьего терминала.
  converterManaged: true,

  converterStart: async (): Promise<ConverterStartResult> => {
    try {
      const res = await fetchBackend('/converter/start', { method: 'POST' });
      return (await res.json()) as ConverterStartResult;
    } catch (e) {
      return {
        ok: false,
        error: e instanceof Error ? e.message : 'Конвертер недоступен',
      };
    }
  },

  converterStop: async () => {
    try {
      const res = await fetchBackend('/converter/stop', { method: 'POST' });
      return (await res.json()) as { ok: boolean };
    } catch {
      return { ok: false };
    }
  },

  converterStatus: async (): Promise<ConverterProcessStatus> => {
    try {
      const res = await fetchBackend('/converter/status');
      return (await res.json()) as ConverterProcessStatus;
    } catch {
      return { running: false, healthy: false };
    }
  },

  // --- Теневые LLM-подсказки. Всегда через бэкенд (он владеет жизненным
  //     циклом сайдкара и поднимает его сам), никогда напрямую в конвертер.
  // Прогрев модели «на упреждение». Ответ приходит сразу, работа идёт в
  // фоне сайдкара; результат нас не интересует — важно лишь, что к моменту
  // первой подсказки веса уже в памяти.
  llmWarmup: async (): Promise<void> => {
    try {
      await fetchBackend('/llm/warmup', { method: 'POST' });
    } catch {
      // Прогрев — оптимизация. Не поднялся сайдкар или нет модели — работаем
      // как раньше, просто медленнее. Тревожить юриста здесь нечем.
    }
  },

  llmHintsStart: async (
    rawText: string,
    regex: Record<string, string>,
  ): Promise<{ job_id: string }> => {
    const res = await fetchBackend('/llm/hints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rawText, regex }),
    });
    return (await res.json()) as { job_id: string };
  },

  llmHintsStatus: async (jobId: string): Promise<LlmHintsStatus> => {
    const res = await fetchBackend(`/llm/hints/${encodeURIComponent(jobId)}`);
    return (await res.json()) as LlmHintsStatus;
  },

  llmHintsCancel: async (jobId: string): Promise<void> => {
    // Отмена — «лучшее усилие»: если не дошла, сторож простоя всё равно
    // выгрузит сайдкар. Ронять из-за неё интерфейс незачем.
    try {
      await fetchBackend(`/llm/hints/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
    } catch {
      /* игнорируем */
    }
  },

  // В браузере нет Electron: версия из сборочной переменной (иначе метка «dev»).
  getAppVersion: async (): Promise<string> => process.env.REACT_APP_VERSION || 'dev',
};
