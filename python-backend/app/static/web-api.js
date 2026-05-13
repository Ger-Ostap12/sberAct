(function() {
  // Если electronAPI уже существует из preload.js, НЕ переопределяем его
  // preload.js предоставляет правильные методы с диалогами через IPC
  if (window.electronAPI) {
    console.log('[web-api] Electron API already exists from preload.js, skipping web-api fallback');
    console.log('[web-api] Available methods:', Object.keys(window.electronAPI));
    // Проверяем, что методы download существуют
    if (window.electronAPI.downloadAllDocuments && window.electronAPI.downloadDocument) {
      console.log('[web-api] Electron API methods are available, using them');
      console.log('[web-api] downloadAllDocuments type:', typeof window.electronAPI.downloadAllDocuments);
      console.log('[web-api] downloadDocument type:', typeof window.electronAPI.downloadDocument);
      // ВАЖНО: Полностью выходим, не создаем никаких fallback методов
      // Electron API уже существует из preload.js, не создаем fallback
      return;
    } else {
      console.warn('[web-api] Electron API exists but download methods are missing!');
      console.warn('[web-api] downloadAllDocuments exists:', !!window.electronAPI.downloadAllDocuments);
      console.warn('[web-api] downloadDocument exists:', !!window.electronAPI.downloadDocument);
      // Если методы отсутствуют, все равно не создаем fallback, чтобы не переопределить существующий API
      // Вместо этого просто выходим
      return;
    }
  }

  // Если Electron API не существует, создаем fallback только для WebView
  console.log('[web-api] Electron API not found, creating fallback for WebView');
  console.log('[web-api] Electron API not found, creating fallback for WebView');
  var extractedData = null;
  window.electronAPI = {
    isReady: function() { return true; },
    selectFile: function() {
      return new Promise(function(resolve) {
        var input = document.createElement('input');
        input.type = 'file';
        input.accept = '.docx,.pdf';
        input.onchange = function() {
          if (input.files && input.files[0]) resolve(input.files[0]);
          else resolve(null);
        };
        input.click();
      });
    },
    saveFile: function(defaultName) {
      return Promise.resolve(defaultName);
    },
    analyzeDocument: async function(input) {
      var formData = new FormData();
      var fileName = 'document.docx';
      if (input && typeof input.arrayBuffer === 'function') {
        fileName = input.name || fileName;
        formData.append('document', input, fileName);
      } else if (input instanceof File) {
        formData.append('document', input, input.name || fileName);
      } else {
        throw new Error('Unsupported input');
      }
      var res = await fetch('/analyze-document', { method: 'POST', body: formData });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var result = await res.json();
      if (result && result.data) extractedData = result.data;
      return result;
    },
    generateDocument: async function(requestData) {
      var res = await fetch('/generate-document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    },
    getTemplates: async function() {
      var res = await fetch('/templates');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    },
    downloadDocument: async function(documentId) {
      // Fallback ТОЛЬКО для WebView без Electron
      // Если мы здесь, значит Electron API не существует (иначе мы бы вышли раньше)
      console.warn('[web-api] Using blob download fallback (Electron API not available)');
      var res = await fetch('/download-document/' + documentId);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var blob = await res.blob();
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'document_' + documentId + '.docx';
      a.click();
      URL.revokeObjectURL(a.href);
      return { success: true };
    },
    downloadAllDocuments: async function(data) {
      // Fallback ТОЛЬКО для WebView / EXE без Electron.
      // В этом режиме НЕТ нормального браузерного скачивания,
      // поэтому мы просто просим backend СОХРАНИТЬ ZIP на диск
      // и возвращаем путь к этому файлу.
      console.warn('[web-api] Using fallback SAVE (no Electron IPC)');
      var ids = (data && data.document_ids) ? data.document_ids : '';
      if (!ids) throw new Error('Не указаны ID документов');

      try {
        console.log('[web-api] Requesting backend to save ZIP for IDs:', ids);
        var response = await fetch('/download-zip-save', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ ids: ids })
        });

        if (!response.ok) {
          var errorText = await response.text().catch(function() { return 'Unknown error'; });
          console.error('[web-api] /download-zip-save error:', response.status, errorText);
          throw new Error('Ошибка сервера при сохранении ZIP: HTTP ' + response.status + ': ' + errorText);
        }

        var result = await response.json();
        console.log('[web-api] /download-zip-save result:', result);

        if (!result || !result.success) {
          throw new Error((result && result.detail) || (result && result.error) || 'Не удалось сохранить ZIP файл');
        }

        // Возвращаем тот же формат, что и Electron IPC:
        // { success: true, filePath: '...' }
        return {
          success: true,
          filePath: result.filePath || result.filepath || null
        };
      } catch (error) {
        console.error('[web-api] Download/save error:', error);
        throw error;
      }
    },
    getDownloadPaths: async function() {
      var res = await fetch('/download-paths');
      if (!res.ok) return { success: false };
      return res.json();
    },
    getExtractedData: function() {
      return Promise.resolve(extractedData);
    }
  };
})();
