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
      const mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

      if (typeof input === 'string') {
        console.log('[preload] analyzeDocument(): reading file from path', input);
        const fileContent = fs.readFileSync(input);
        blob = new Blob([fileContent], { type: mime });
      } else if (input && typeof input.arrayBuffer === 'function') {
        console.log('[preload] analyzeDocument(): got File/Blob from renderer');
        const buffer = await input.arrayBuffer();
        blob = new Blob([new Uint8Array(buffer)], { type: mime });
      } else if (input instanceof Uint8Array) {
        console.log('[preload] analyzeDocument(): got Uint8Array');
        blob = new Blob([input], { type: mime });
      } else {
        throw new Error('Unsupported input for analyzeDocument');
      }

      const formData = new FormData();
      formData.append('document', blob, 'document.docx');

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
      console.log('[preload] downloadAllDocuments(): downloading documents with data:', data);
      return await ipcRenderer.invoke('download-all-documents', data);
    } catch (error) {
      console.error('Error downloading all documents:', error);
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

  getExtractedData: () => ipcRenderer.invoke('get-extracted-data')
});
