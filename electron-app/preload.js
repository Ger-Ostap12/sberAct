const { contextBridge, ipcRenderer } = require('electron');
const fs = require('fs');
console.log('[preload] loaded');

// Вспомогательная функция: пробуем несколько хостов (WSL/Windows)
async function fetchBackend(pathname, options) {
  const baseUrls = [
    'http://wsl.localhost:8000',  // WSL localhost
    'http://127.0.0.1:8000',
    'http://localhost:8000'
  ];
  let lastError;
  for (const base of baseUrls) {
    const url = `${base}${pathname}`;
    try {
      console.log(`[preload] fetch ${url}`);
      const res = await fetch(url, options);
      if (!res.ok) {
        let text = '';
        try { text = await res.text(); } catch (_) {}
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      return res;
    } catch (e) {
      lastError = e;
      console.warn('[preload] fetch failed for', url, e.message || e);
    }
  }
  throw lastError || new Error('All backend hosts failed');
}

console.log('[preload] Exposing electronAPI to renderer...');
try {
  contextBridge.exposeInMainWorld('electronAPI', {
  isReady: () => true,
  // Файловые операции
  selectFile: () => ipcRenderer.invoke('select-file'),
  saveFile: (defaultName) => ipcRenderer.invoke('save-file', defaultName),

  // Чтение файлов
  readFile: (filePath) => {
    try {
      const buffer = fs.readFileSync(filePath);
      return buffer;
    } catch (error) {
      console.error('Error reading file:', error);
      throw error;
    }
  },

  // API для работы с документами
  analyzeDocument: async (input) => {
    try {
      let blob;
      let fileName = 'document.docx';

      if (typeof input === 'string') {
        console.log('[preload] analyzeDocument(): reading file from path', input);
        const path = require('path');
        fileName = path.basename(input) || fileName;
        const ext = path.extname(fileName).toLowerCase();
        const mime = ext === '.pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
        const fileContent = fs.readFileSync(input);
        blob = new Blob([fileContent], { type: mime });
      } else if (input && typeof input.arrayBuffer === 'function') {
        console.log('[preload] analyzeDocument(): got File/Blob from renderer');
        fileName = input.name || fileName;
        const ext = fileName.toLowerCase().endsWith('.pdf') ? '.pdf' : '.docx';
        const mime = ext === '.pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
        const buffer = await input.arrayBuffer();
        blob = new Blob([new Uint8Array(buffer)], { type: mime });
      } else if (input instanceof Uint8Array) {
        console.log('[preload] analyzeDocument(): got Uint8Array');
        blob = new Blob([input], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
      } else {
        throw new Error('Unsupported input for analyzeDocument');
      }

      const formData = new FormData();
      formData.append('document', blob, fileName);

      console.log('[preload] POST /analyze-document');
      const response = await fetchBackend('/analyze-document', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        let bodyText = '';
        try { bodyText = await response.text(); } catch (e) {}
        console.error('[preload] analyzeDocument() error response:', response.status, bodyText);
        throw new Error(`HTTP ${response.status}: ${bodyText || 'Unknown error'}`);
      }

      const result = await response.json();
      console.log('[preload] analyzeDocument() OK');
      try {
        await ipcRenderer.invoke('set-extracted-data', result && result.data ? result.data : result);
      } catch (e) {
        // ignore
      }
      return result;
    } catch (error) {
      console.error('Error analyzing document:', error);
      throw error;
    }
  },

  generateDocument: async (requestData) => {
    try {
      console.log('[preload] generateDocument(): requestData:', requestData);
      console.log('[preload] generateDocument(): requestData.template_type:', requestData.template_type);
      console.log('[preload] generateDocument(): requestData.data:', requestData.data);

      if (!requestData.template_type || !requestData.data) {
        throw new Error('Missing template_type or data in requestData');
      }

      const response = await fetchBackend('/generate-document', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error generating document:', error);
      throw error;
    }
  },

  getTemplates: async () => {
    try {
      const response = await fetchBackend('/templates');

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error getting templates:', error);
      throw error;
    }
  },

  // Единый реестр банков-кредиторов с бэкенда (GET /banks)
  getBanks: async () => {
    try {
      const response = await fetchBackend('/banks');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error getting banks:', error);
      throw error;
    }
  },

  downloadDocument: async (documentId) => {
    try {
      console.log('[preload] downloadDocument(): downloading document with ID:', documentId);
      return await ipcRenderer.invoke('download-document', documentId);
    } catch (error) {
      console.error('Error downloading document:', error);
      return { success: false, error: error.message };
    }
  },

  downloadAllDocuments: async (data) => {
    try {
      console.log('[preload] ========== downloadAllDocuments() CALLED ==========');
      console.log('[preload] downloadAllDocuments(): called with data:', data);
      console.log('[preload] downloadAllDocuments(): invoking IPC download-all-documents...');
      const result = await ipcRenderer.invoke('download-all-documents', data);
      console.log('[preload] downloadAllDocuments(): IPC result:', result);
      return result;
    } catch (error) {
      console.error('[preload] ERROR in downloadAllDocuments:', error);
      return { success: false, error: error.message };
    }
  },

  getDownloadPaths: async () => {
    try {
      console.log('[preload] getDownloadPaths(): getting download paths');
      return await ipcRenderer.invoke('get-download-paths');
    } catch (error) {
      console.error('Error getting download paths:', error);
      return { success: false, error: error.message };
    }
  },

  getExtractedData: () => ipcRenderer.invoke('get-extracted-data'),

  // --- OCR-конвертер (sidecar-процесс, живёт только на convert-шаге) ---
  // true = процессом управляет Electron (в браузере конвертер запущен постоянно,
  // и webApi отдаёт false — UI прячет управление процессом)
  converterManaged: true,
  converterStart: () => ipcRenderer.invoke('converter:start'),
  converterStop: () => ipcRenderer.invoke('converter:stop'),
  converterStatus: () => ipcRenderer.invoke('converter:status'),

  // Convert-шаг: HTTP только на наш бэкенд (:8000) — прокси /convert/* сам
  // ходит на порт конвертера, рендер о нём не знает.
  analyzeText: async (text, pageCount) => {
    const response = await fetchBackend('/analyze-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, page_count: pageCount ?? null })
    });
    return await response.json();
  },

  convertAnalyze: async (file) => {
    const formData = new FormData();
    formData.append('file', file, file.name || 'document.pdf');
    const response = await fetchBackend('/convert/analyze', { method: 'POST', body: formData });
    return await response.json();
  },

  convertScan: async (file, flags) => {
    const formData = new FormData();
    formData.append('file', file, file.name || 'document.pdf');
    Object.entries(flags || {}).forEach(([key, value]) => {
      if (value !== undefined) formData.append(key, String(value));
    });
    const response = await fetchBackend('/convert/scan', { method: 'POST', body: formData });
    return await response.json();
  },

  convertNative: async (file) => {
    const formData = new FormData();
    formData.append('file', file, file.name || 'document.pdf');
    const response = await fetchBackend('/convert/native', { method: 'POST', body: formData });
    return await response.json();
  },

  convertStatus: async (jobId) => {
    const response = await fetchBackend(`/convert/status/${encodeURIComponent(jobId)}`);
    return await response.json();
  },

  convertDownload: async (jobId) => {
    const response = await fetchBackend(`/convert/download/${encodeURIComponent(jobId)}`);
    return await response.blob();
  },

  docxText: async (docx) => {
    const formData = new FormData();
    formData.append('document', docx, 'converted.docx');
    const response = await fetchBackend('/docx-text', { method: 'POST', body: formData });
    return await response.json();
  },

  docxApplyEdits: async (docx, editedText) => {
    const formData = new FormData();
    formData.append('document', docx, 'converted.docx');
    formData.append('edited_text', editedText);
    const response = await fetchBackend('/docx-apply-edits', { method: 'POST', body: formData });
    return await response.blob();
  },

  // Метод для открытия DevTools из рендерера
  toggleDevTools: () => ipcRenderer.invoke('toggle-devtools')
});

// Добавляем глобальную функцию для открытия DevTools через консоль
// Можно вызвать в консоли браузера: openDevTools()
contextBridge.exposeInMainWorld('openDevTools', () => {
  console.log('[preload] Opening DevTools via console command');
  ipcRenderer.invoke('toggle-devtools');
});

  console.log('[preload] electronAPI exposed successfully');
  console.log('[preload] electronAPI exposed with methods:', Object.keys({
    fetch: true,
    selectFile: true,
    saveFile: true,
    analyzeDocument: true,
    generateDocument: true,
    getTemplates: true,
    downloadDocument: true,
    downloadAllDocuments: true,
    getDownloadPaths: true,
    getExtractedData: true,
    toggleDevTools: true
  }));
  console.log('[preload] Global function available: openDevTools() - call this in console to open DevTools');
} catch (error) {
  console.error('[preload] ERROR exposing electronAPI:', error);
}
