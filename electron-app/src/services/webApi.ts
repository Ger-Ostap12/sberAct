import { AnalysisResult, ExtractedData } from '../types';
import {
  ElectronAPI,
  GenerateDocumentRequest,
  GenerateDocumentResult,
  DownloadAllDocumentsRequest,
  DownloadResult,
} from './electronApi';

// Веб-реализация того же контракта, что и мост Electron (preload). Позволяет
// открывать приложение в обычном браузере: все операции идут прямыми fetch к
// backend (CORS на бэкенде открыт). Отличия от десктопа: скачивание падает в
// папку «Загрузки» браузера (без нативного диалога), выбор файла по пути недоступен.

const BASE_URLS = ['http://127.0.0.1:8000', 'http://localhost:8000', 'http://wsl.localhost:8000'];

/** Пробует несколько хостов backend, возвращает первый успешный ответ. */
async function fetchBackend(pathname: string, options?: RequestInit): Promise<Response> {
  let lastError: unknown;
  for (const base of BASE_URLS) {
    try {
      const res = await fetch(`${base}${pathname}`, options);
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      return res;
    } catch (e) {
      lastError = e;
    }
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
};
