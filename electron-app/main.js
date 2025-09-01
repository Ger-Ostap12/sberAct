const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const isDev = require('electron-is-dev');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;

function resolvePythonEntry() {
  if (isDev) {
    return path.join(__dirname, '../python-backend/app/main.py');
  }
  // В проде python-backend должен быть распакован из asar
  const resourcesPath = process.resourcesPath;
  // структура: resources/app.asar.unpacked/python-backend/app/main.py
  return path.join(resourcesPath, 'app.asar.unpacked', 'python-backend', 'app', 'main.py');
}

function resolvePythonExecutable() {
  if (isDev) {
    // В режиме разработки используем виртуальное окружение
    const venvPython = path.join(__dirname, '../python-backend/venv/bin/python');
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }
    // Если venv нет, используем системный python3
    return 'python3';
  }
  // В проде используем системный python3
  return 'python3';
}

function resolveIcon() {
  const candidate = path.join(__dirname, 'public', 'icon.png');
  if (fs.existsSync(candidate)) {
    return candidate;
  }
  return undefined;
}

function createWindow() {
  // Создаем окно браузера
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    icon: resolveIcon(),
    titleBarStyle: 'default',
    show: false,
  });

  // Загружаем приложение
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, 'build/index.html'));
  }

  // Показываем окно когда готово
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Обработка закрытия окна
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Запуск Python backend
function startPythonBackend() {
  const pythonPath = resolvePythonEntry();
  const pythonExecutable = resolvePythonExecutable();

  console.log(`Запуск Python backend: ${pythonExecutable} ${pythonPath}`);

  pythonProcess = spawn(pythonExecutable, [pythonPath], {
    stdio: ['pipe', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONPATH: path.join(__dirname, '../python-backend')
    }
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log('Python Backend:', data.toString());
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error('Python Backend Error:', data.toString());
  });

  pythonProcess.on('close', (code) => {
    console.log('Python Backend exited with code:', code);
  });

  pythonProcess.on('error', (error) => {
    console.error('Python Backend spawn error:', error);
  });
}

// Остановка Python backend
function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill();
  }
}

// IPC обработчики
ipcMain.handle('select-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [{ name: 'Word Documents', extensions: ['docx', 'doc'] }],
  });

  if (!result.canceled) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('save-file', async (event, defaultPath) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultPath,
    filters: [
      { name: 'Word Documents', extensions: ['docx'] },
      { name: 'PDF Documents', extensions: ['pdf'] },
    ],
  });

  if (!result.canceled) {
    return result.filePath;
  }
  return null;
});

// События приложения
app.whenReady().then(() => {
  createWindow();
  startPythonBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopPythonBackend();
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  stopPythonBackend();
});
