const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const isDev = require('electron-is-dev');
let mainWindow;
let pythonProcess;

function resolvePythonEntry() {
  if (isDev) {
    // В dev вычисляем от каталога приложения, а не от cwd
    const appRoot = app.getAppPath();
    return path.join(appRoot, 'python-backend', 'app', 'main.py');
  } else {
    return path.join(__dirname, '../app.asar.unpacked/python-backend/app/main.py');
  }}

function resolvePythonExecutable() {
  if (isDev) {
    // Для Windows используем Scripts/python.exe, для Unix - bin/python
    const isWindows = process.platform === 'win32';
    const pythonDir = isWindows ? 'Scripts' : 'bin';
    const pythonExe = isWindows ? 'python.exe' : 'python';
    const venvPath = path.join(__dirname, '../python-backend/venv', pythonDir, pythonExe);

    if (fs.existsSync(venvPath)) {
      return venvPath;
    }
    return isWindows ? 'python' : 'python3';
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function resolveIcon() {
  const iconPath = path.join(__dirname, 'assets/icon.png');
  if (fs.existsSync(iconPath)) {
    return iconPath;
  }
  return undefined;
}

async function startPythonBackend() {
  try {
    // В режиме разработки всегда используем внешний backend (WSL)
    if (isDev) {
      console.log('Dev mode: using external backend; skipping Python spawn');
      return;
    }

    // Если USE_EXTERNAL_BACKEND=1, не запускаем локальный процесс
    if (process.env.USE_EXTERNAL_BACKEND === '1') {
      console.log('Skipping Python backend start: USE_EXTERNAL_BACKEND=1');
      return;
    }

    // Проверяем, не запущен ли уже backend (например, в WSL)
    const healthUrl = 'http://127.0.0.1:8000/health';
    try {
      const res = await fetch(healthUrl, { method: 'GET' });
      if (res.ok) {
        console.log('Detected running backend at 127.0.0.1:8000, skipping spawn');
        return;
      }
    } catch (_) {
      // Недоступен — запускаем локально
    }
    const pythonPath = resolvePythonEntry();
    const pythonExecutable = resolvePythonExecutable();

    console.log(`Starting Python backend with: ${pythonExecutable} ${pythonPath}`);

    pythonProcess = spawn(pythonExecutable, [pythonPath], {
      cwd: isDev ? path.join(app.getAppPath(), 'python-backend', 'app') : undefined,
      env: {
        ...process.env,
        PYTHONPATH: path.join(__dirname, '../python-backend'),
        PATH: process.env.PATH + (process.platform === 'win32' ? ';' : ':') + path.join(process.env.HOME || process.env.USERPROFILE, '.local/bin')
      }
    });

    pythonProcess.stdout.on('data', (data) => {
      console.log(`Python stdout: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`Python stderr: ${data}`);
    });

    pythonProcess.on('error', (error) => {
      console.error('Failed to start Python backend:', error);
    });

    pythonProcess.on('close', (code) => {
      console.log(`Python backend exited with code ${code}`);
    });
  } catch (error) {
    console.error('Unexpected error in startPythonBackend:', error);
  }
}

function createWindow() {
  const preloadPath = isDev
    ? path.join(app.getAppPath(), 'electron-app', 'preload.js')
    : path.join(__dirname, 'preload.js');
  console.log('Using preload:', preloadPath);
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      preload: preloadPath,
      webSecurity: false  // Отключаем web security для локальной разработки
    },
    icon: resolveIcon(),
    title: 'SberAct Document Generator'
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
    // Не открываем DevTools автоматически, чтобы избежать спама сообщениями Autofill
  } else {
    mainWindow.loadFile(path.join(__dirname, 'build/index.html'));
  }
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  startPythonBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});

// IPC handlers
ipcMain.handle('select-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'Word Documents', extensions: ['docx'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (!result.canceled) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('save-file', async (event, defaultName) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultName,
    filters: [
      { name: 'Word Documents', extensions: ['docx'] }
    ]
  });

  if (!result.canceled) {
    return result.filePath;
  }
  return null;
});

ipcMain.handle('get-extracted-data', () => {
  return global.extractedData || null;
});

ipcMain.handle('set-extracted-data', (event, data) => {
  global.extractedData = data;
  return true;
});

// API для генерации документов
ipcMain.handle('generate-document', async (event, data) => {
  try {
    const response = await fetch('http://localhost:8000/generate-document', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Error generating document:', error);
    return { success: false, error: error.message };
  }
});

// API для скачивания одного документа
ipcMain.handle('download-document', async (event, documentId) => {
  try {
    const response = await fetch(`http://localhost:8000/download-document/${documentId}`);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // Получаем файл как blob
    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // Показываем диалог сохранения
    const result = await dialog.showSaveDialog(mainWindow, {
      defaultPath: `document_${documentId}.docx`,
      filters: [
        { name: 'Word Documents', extensions: ['docx'] }
      ]
    });

    if (!result.canceled) {
      fs.writeFileSync(result.filePath, buffer);
      return { success: true, filePath: result.filePath };
    }

    return { success: false, error: 'Сохранение отменено' };
  } catch (error) {
    console.error('Error downloading document:', error);
    return { success: false, error: error.message };
  }
});

// API для скачивания всех документов
ipcMain.handle('download-all-documents', async (event, data) => {
  try {
    const response = await fetch('http://localhost:8000/download-all-documents', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // Если указан путь для сохранения, возвращаем информацию
    if (data.download_path) {
      const result = await response.json();
      return result;
    } else {
      // Иначе скачиваем файл
      const blob = await response.blob();
      const arrayBuffer = await blob.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);

      // Показываем диалог сохранения
      const result = await dialog.showSaveDialog(mainWindow, {
        defaultPath: 'generated_documents.zip',
        filters: [
          { name: 'ZIP Archives', extensions: ['zip'] }
        ]
      });

      if (!result.canceled) {
        fs.writeFileSync(result.filePath, buffer);
        return { success: true, filePath: result.filePath };
      }

      return { success: false, error: 'Сохранение отменено' };
    }
  } catch (error) {
    console.error('Error downloading all documents:', error);
    return { success: false, error: error.message };
  }
});

// API для получения путей скачивания
ipcMain.handle('get-download-paths', async () => {
  try {
    const response = await fetch('http://localhost:8000/download-paths');

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Error getting download paths:', error);
    return { success: false, error: error.message };
  }
});
