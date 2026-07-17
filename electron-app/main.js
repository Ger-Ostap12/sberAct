const { app, BrowserWindow, ipcMain, dialog, globalShortcut, Menu } = require('electron');

// Отключаем аппаратное ускорение: на некоторых Windows-конфигурациях
// GPU-процесс падает ("GPU process isn't usable. Goodbye.") и окно не открывается.
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.commandLine.appendSwitch('in-process-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('no-sandbox');

const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const isDev = require('electron-is-dev');
let mainWindow;
let pythonProcess;

// ---------------------------------------------------------------------------
// Менеджер локального сервиса-процесса (используется для OCR-конвертера).
// Конвертер тяжёлый (torch + LLM), поэтому живёт отдельным процессом и
// запускается ТОЛЬКО на время convert-шага: spawn при выборе PDF, kill после
// «Далее» — так память возвращается ОС целиком (см. docs/converter_integration_plan.md).
// ---------------------------------------------------------------------------
class ManagedService {
  constructor({ name, resolveCommand, healthUrl, startTimeoutMs = 60000, healthIntervalMs = 1000 }) {
    this.name = name;
    this.resolveCommand = resolveCommand; // () => { command, args, cwd, env } | null
    this.healthUrl = healthUrl;
    this.startTimeoutMs = startTimeoutMs;
    this.healthIntervalMs = healthIntervalMs;
    this.process = null;
    this.external = false; // сервис уже был запущен снаружи — не наш процесс, не убиваем
    this.starting = null;  // промис текущего запуска (защита от параллельных start)
  }

  async isHealthy() {
    try {
      const res = await fetch(this.healthUrl, { method: 'GET' });
      return res.ok;
    } catch (_) {
      return false;
    }
  }

  isRunning() {
    return this.external || (this.process !== null && this.process.exitCode === null);
  }

  async start() {
    if (this.starting) return this.starting;
    this.starting = this._start();
    try {
      return await this.starting;
    } finally {
      this.starting = null;
    }
  }

  async _start() {
    // Уже отвечает (наш процесс или внешний запуск для отладки) — не спавним второй
    if (await this.isHealthy()) {
      if (!this.process) this.external = true;
      console.log(`[${this.name}] already healthy at ${this.healthUrl}`);
      return { ok: true, external: this.external };
    }

    const cmd = this.resolveCommand();
    if (!cmd) {
      return { ok: false, error: `${this.name}: не найдена команда запуска (сервис не установлен?)` };
    }

    console.log(`[${this.name}] starting: ${cmd.command} ${(cmd.args || []).join(' ')}`);
    this.external = false;
    this.process = spawn(cmd.command, cmd.args || [], {
      cwd: cmd.cwd,
      env: { ...process.env, ...(cmd.env || {}) }
    });
    this.process.stdout.on('data', (d) => console.log(`[${this.name}] ${d}`));
    this.process.stderr.on('data', (d) => console.error(`[${this.name}] ${d}`));
    this.process.on('error', (e) => console.error(`[${this.name}] spawn error:`, e));
    this.process.on('close', (code) => {
      console.log(`[${this.name}] exited with code ${code}`);
      this.process = null;
    });

    // Ждём готовности health-циклом: холодный старт конвертера (загрузка LLM)
    // занимает десятки секунд — без ожидания фронт получал бы connection refused.
    const deadline = Date.now() + this.startTimeoutMs;
    while (Date.now() < deadline) {
      if (this.process === null) {
        return { ok: false, error: `${this.name}: процесс завершился до готовности` };
      }
      if (await this.isHealthy()) {
        console.log(`[${this.name}] healthy`);
        return { ok: true, external: false };
      }
      await new Promise((r) => setTimeout(r, this.healthIntervalMs));
    }
    this.stop();
    return { ok: false, error: `${this.name}: не поднялся за ${Math.round(this.startTimeoutMs / 1000)} с` };
  }

  stop() {
    // Внешний (не наш) процесс не трогаем — мы его не запускали
    if (this.process) {
      console.log(`[${this.name}] stopping`);
      this.process.kill();
      this.process = null;
    }
  }
}

// --- OCR-конвертер (sidecar): папка converter/ в корне проекта, свой venv ---
const CONVERTER_PORT = process.env.CONVERTER_PORT || '8008';

function resolveConverterCommand() {
  // CONVERTER_DIR — на случай, если конвертер пришлось поставить в ASCII-путь
  // (tesseract/llama-cpp бывают нетерпимы к кириллице в путях).
  const projectRoot = isDev ? app.getAppPath() : path.join(__dirname, '../app.asar.unpacked');
  const converterDir = process.env.CONVERTER_DIR || path.join(projectRoot, 'converter');
  const isWindows = process.platform === 'win32';
  const pyRel = path.join(isWindows ? 'Scripts' : 'bin', isWindows ? 'python.exe' : 'python');
  // install_offline.bat конвертера создаёт `.venv`; `venv` — фолбэк на ручную установку
  const venvPython = [path.join(converterDir, '.venv', pyRel), path.join(converterDir, 'venv', pyRel)]
    .find((p) => fs.existsSync(p));
  const entry = path.join(converterDir, 'main.py');
  // Запускаем через лаунчер sberAct (порт у upstream захардкожен на 8000,
  // run_converter.py поднимает то же приложение на CONVERTER_PORT без правок
  // кода конвертера).
  const launcher = path.join(projectRoot, 'python-backend', 'app', 'run_converter.py');
  if (!venvPython || !fs.existsSync(entry)) {
    console.warn(`[converter] not installed at ${converterDir}`);
    return null;
  }
  return {
    command: venvPython,
    args: [launcher],
    cwd: converterDir,
    env: { CONVERTER_PORT, CONVERTER_DIR: converterDir }
  };
}

const converterService = new ManagedService({
  name: 'converter',
  resolveCommand: resolveConverterCommand,
  healthUrl: `http://127.0.0.1:${CONVERTER_PORT}/health`,
  // Холодный старт с LLM — с запасом
  startTimeoutMs: 180000
});

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
    // ВАЖНО: Автоматически открываем DevTools в production для отладки
    // Можно закомментировать эту строку после исправления проблем
    mainWindow.webContents.openDevTools();
  }

  // Добавляем горячие клавиши для открытия DevTools
  // Используем несколько методов для надежности

  // Функция для переключения DevTools
  const toggleDevTools = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.closeDevTools();
      } else {
        mainWindow.webContents.openDevTools();
      }
    }
  };

  // Метод 1: Обработчик событий клавиатуры в окне (основной метод)
  mainWindow.webContents.on('before-input-event', (event, input) => {
    // F12 для открытия/закрытия DevTools
    if (input.key === 'F12' || input.code === 'F12') {
      event.preventDefault();
      toggleDevTools();
      return;
    }
    // Ctrl+Shift+I для открытия DevTools
    if (input.control && input.shift && (input.key === 'I' || input.key === 'i')) {
      event.preventDefault();
      if (!mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.openDevTools();
      }
      return;
    }
    // Ctrl+Shift+J для открытия DevTools (альтернатива)
    if (input.control && input.shift && (input.key === 'J' || input.key === 'j')) {
      event.preventDefault();
      if (!mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.openDevTools();
      }
      return;
    }
  });

  // Метод 2: IPC обработчик для открытия DevTools из рендерера
  ipcMain.handle('toggle-devtools', () => {
    toggleDevTools();
    return { opened: mainWindow && !mainWindow.isDestroyed() && mainWindow.webContents.isDevToolsOpened() };
  });

  // Метод 3: Создаем меню с опцией открытия DevTools
  const template = [
    {
      label: 'Вид',
      submenu: [
        {
          label: 'Открыть консоль разработчика',
          accelerator: 'F12',
          click: () => {
            toggleDevTools();
          }
        },
        {
          label: 'Перезагрузить',
          accelerator: 'Ctrl+R',
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.reload();
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Выход',
          accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.quit();
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);

  // Метод 4: Добавляем обработчик на уровне приложения (для отладки)
  console.log('[main] DevTools shortcuts registered: F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+Shift+D');
  console.log('[main] DevTools menu added: View -> Open DevTools');
  mainWindow.on('closed', () => {
    // Отменяем регистрацию глобальных шорткатов при закрытии окна
    globalShortcut.unregisterAll();
    // Не обнуляем mainWindow сразу, чтобы диалоги могли работать
    // mainWindow = null;
  });
}

app.whenReady().then(() => {
  startPythonBackend();
  createWindow();

  // Регистрируем глобальные шорткаты после создания окна
  // Используем альтернативные комбинации (F12 не работает как глобальный шорткат)
  const registerGlobalShortcuts = () => {
    const windows = BrowserWindow.getAllWindows();
    if (windows.length === 0) return;
    const win = windows[0];

    // Ctrl+Shift+D для переключения DevTools
    globalShortcut.register('CommandOrControl+Shift+D', () => {
      if (win && !win.isDestroyed()) {
        if (win.webContents.isDevToolsOpened()) {
          win.webContents.closeDevTools();
        } else {
          win.webContents.openDevTools();
        }
      }
    });

    console.log('[main] Global shortcuts registered: Ctrl+Shift+D');
  };

  // Регистрируем после небольшой задержки, чтобы окно точно было создано
  setTimeout(registerGlobalShortcuts, 500);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      setTimeout(registerGlobalShortcuts, 500);
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Конвертером владеет backend (единый жизненный цикл на десктоп и браузер, см.
// services/electronApi.ts). Поэтому просто убить pythonProcess нельзя: на Windows
// kill() — это TerminateProcess, хук shutdown у uvicorn не отработает, и sidecar
// осиротеет с ~3.5 ГБ. Сначала просим backend погасить его, потом гасим backend.
let _quitCleanupDone = false;
app.on('before-quit', (event) => {
  if (_quitCleanupDone) return;
  event.preventDefault();

  const finish = () => {
    if (_quitCleanupDone) return; // таймер и ответ backend'а гонятся — пускаем одного
    _quitCleanupDone = true;
    if (pythonProcess) pythonProcess.kill();
    converterService.stop(); // на случай внешнего/легаси-запуска через ManagedService
    app.quit();
  };

  // Ждём недолго: выход не должен зависеть от отзывчивости backend'а.
  const timer = setTimeout(finish, 3000);
  fetch('http://127.0.0.1:8000/converter/stop', { method: 'POST' })
    .catch(() => undefined)
    .finally(() => {
      clearTimeout(timer);
      finish();
    });
});

// --- Управление процессом OCR-конвертера из рендера (convert-шаг) ---
ipcMain.handle('converter:start', async () => {
  try {
    return await converterService.start();
  } catch (error) {
    console.error('[converter] start error:', error);
    return { ok: false, error: error.message || 'Не удалось запустить конвертер' };
  }
});

ipcMain.handle('converter:stop', () => {
  converterService.stop();
  return { ok: true };
});

ipcMain.handle('converter:status', async () => {
  return {
    running: converterService.isRunning(),
    healthy: await converterService.isHealthy()
  };
});

// IPC handlers
ipcMain.handle('select-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'Заявления (Word и PDF)', extensions: ['docx', 'pdf'] },
      { name: 'Word Documents', extensions: ['docx'] },
      { name: 'PDF', extensions: ['pdf'] },
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
    console.log(`[main] download-document: Starting download for document ID: ${documentId}`);

    const response = await fetch(`http://localhost:8000/download-document/${documentId}`);

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      console.error(`[main] download-document: HTTP error ${response.status}: ${errorText}`);
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    console.log(`[main] download-document: Response received, content-type: ${response.headers.get('content-type')}`);

    // Получаем файл как blob
    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    console.log(`[main] download-document: File loaded, size: ${buffer.length} bytes`);

    // Показываем диалог сохранения
    if (!mainWindow) {
      console.error('[main] download-document: mainWindow is null!');
      const windows = BrowserWindow.getAllWindows();
      if (windows.length > 0) {
        mainWindow = windows[0];
        console.log('[main] download-document: Using first available window');
      } else {
        throw new Error('Main window не доступен для показа диалога');
      }
    }

    console.log('[main] download-document: Showing save dialog...');
    // Убеждаемся, что окно видимо и в фокусе
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.focus();

    // Принудительно показываем окно поверх всех окон
    mainWindow.setAlwaysOnTop(true);
    mainWindow.show();

    console.log('[main] download-document: Calling dialog.showSaveDialog...');

    // Используем асинхронный вызов диалога
    const result = await dialog.showSaveDialog(mainWindow, {
      title: 'Сохранить документ',
      defaultPath: `Судебный_акт_${documentId}.docx`,
      filters: [
        { name: 'Word Documents', extensions: ['docx'] },
        { name: 'All Files', extensions: ['*'] }
      ],
      properties: ['showOverwriteConfirmation']
    });

    // Убираем alwaysOnTop после показа диалога
    mainWindow.setAlwaysOnTop(false);

    console.log('[main] download-document: Dialog result:', result);

    if (result && !result.canceled && result.filePath) {
      const filePath = result.filePath;
      console.log(`[main] download-document: Saving to: ${filePath}`);
      fs.writeFileSync(filePath, buffer);
      console.log(`[main] download-document: File saved successfully`);
      return { success: true, filePath: filePath };
    }

    console.log(`[main] download-document: Save dialog canceled`);
    return { success: false, error: 'Сохранение отменено пользователем' };
  } catch (error) {
    console.error('[main] download-document: Error:', error);
    return { success: false, error: error.message || 'Ошибка при скачивании документа' };
  }
});

// API для скачивания всех документов
ipcMain.handle('download-all-documents', async (event, data) => {
  try {
    console.log(`[main] ========== download-all-documents IPC HANDLER CALLED ==========`);
    console.log(`[main] download-all-documents: Starting download with data:`, data);

    // ВСЕГДА показываем диалог сохранения, даже если указан download_path
    // Пользователь должен выбрать место сохранения через проводник
    const documentIds = data.document_ids || '';
    const ids = documentIds.split(',').filter(id => id.trim());

    if (!ids || ids.length === 0) {
      throw new Error('Не указаны ID документов для скачивания');
    }

    console.log(`[main] download-all-documents: Document IDs: ${ids.join(', ')}`);

    // Получаем ZIP файл с сервера
    const response = await fetch('http://localhost:8000/download-all-documents', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        document_ids: documentIds,
        download_path: '' // Всегда пустой, чтобы получить файл для диалога
      })
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      console.error(`[main] download-all-documents: HTTP error ${response.status}: ${errorText}`);
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    // Скачиваем файл
    console.log(`[main] download-all-documents: Response received, downloading ZIP`);
    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    console.log(`[main] download-all-documents: ZIP loaded, size: ${buffer.length} bytes`);

    // ВСЕГДА показываем диалог сохранения
    if (!mainWindow) {
      console.error('[main] download-all-documents: mainWindow is null!');
      // Пытаемся получить активное окно
      const windows = BrowserWindow.getAllWindows();
      if (windows.length > 0) {
        mainWindow = windows[0];
        console.log('[main] download-all-documents: Using first available window');
      } else {
        throw new Error('Main window не доступен для показа диалога');
      }
    }

    console.log('[main] ========== SHOWING SAVE DIALOG ==========');
    console.log('[main] download-all-documents: Showing save dialog...');
    console.log('[main] download-all-documents: mainWindow exists:', !!mainWindow);
    console.log('[main] download-all-documents: mainWindow.isDestroyed():', mainWindow ? mainWindow.isDestroyed() : 'N/A');

    // КРИТИЧЕСКИ ВАЖНО: Убеждаемся, что окно видимо перед показом диалога
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore();
      }
      mainWindow.show();
      mainWindow.focus();
      mainWindow.setAlwaysOnTop(true);
      console.log('[main] Window prepared for dialog');
    }

    console.log('[main] download-all-documents: Calling dialog.showSaveDialog...');

    // Используем асинхронный вызов диалога
    const result = await dialog.showSaveDialog(mainWindow, {
      title: 'Сохранить документы',
      defaultPath: 'generated_documents.zip',
      filters: [
        { name: 'ZIP Archives', extensions: ['zip'] },
        { name: 'All Files', extensions: ['*'] }
      ],
      properties: ['showOverwriteConfirmation']
    });

    // Убираем alwaysOnTop после показа диалога
    mainWindow.setAlwaysOnTop(false);

    console.log('[main] ========== DIALOG RESULT ==========');
    console.log('[main] download-all-documents: Dialog result:', JSON.stringify(result, null, 2));

    if (result && !result.canceled && result.filePath) {
      const filePath = result.filePath;
      console.log(`[main] download-all-documents: Saving to: ${filePath}`);
      fs.writeFileSync(filePath, buffer);
      console.log(`[main] download-all-documents: ZIP saved successfully to: ${filePath}`);
      return { success: true, filePath: filePath };
    }

    console.log(`[main] download-all-documents: Save dialog canceled by user`);
    return { success: false, error: 'Сохранение отменено пользователем' };
  } catch (error) {
    console.error('[main] download-all-documents: Error:', error);
    return { success: false, error: error.message || 'Ошибка при скачивании документов' };
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
