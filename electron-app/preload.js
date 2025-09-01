const { contextBridge, ipcRenderer } = require('electron');
const fs = require('fs');

// Экспортируем API для React приложения
contextBridge.exposeInMainWorld('electronAPI', {
  // Файловые операции
  selectFile: () => ipcRenderer.invoke('select-file'),
  saveFile: (defaultPath) => ipcRenderer.invoke('save-file', defaultPath),

  // API для работы с Python backend
  analyzeDocument: async (filePath) => {
    const fileBuffer = fs.readFileSync(filePath);
    const blob = new Blob([fileBuffer]);
    const formData = new FormData();
    formData.append('file', blob, 'document.docx');

    const response = await fetch('http://localhost:8000/analyze-document', {
      method: 'POST',
      body: formData,
    });

    return response.json();
  },

  generateDocument: async (templateType, extractedData, outputFormat) => {
    const response = await fetch('http://localhost:8000/generate-document', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        template_type: templateType,
        extracted_data: extractedData,
        output_format: outputFormat,
      }),
    });

    return response.json();
  },

  getDocumentTypes: async () => {
    const response = await fetch('http://localhost:8000/document-types');
    return response.json();
  },
});
