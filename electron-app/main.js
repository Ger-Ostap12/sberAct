const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');

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
const { initUpdater, shutdownUpdater } = require('./updater');

// Linux: Chromium SUID-песочница требует setuid-root chrome-sandbox, а Ubuntu 24.04
// по умолчанию режет и unprivileged-namespace-песочницу. Из AppImage приложение
// без этого падает ещё до окна (FATAL: chrome-sandbox ... mode 4755). Для оффлайн-
// инструмента песочница рендерера некритична — отключаем на Linux, чтобы AppImage
// запускался обычным двойным кликом без флагов.
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('no-sandbox');
}

let mainWindow;
let pythonProcess;

// Убиваем процесс ВМЕСТЕ С ДЕРЕВОМ детей. Backend (SberAct.exe) сам спавнит
// конвертер (python.exe ~6 ГБ) дочерним процессом. На Windows proc.kill() —
// это TerminateProcess ТОЛЬКО родителя: конвертер осиротеет, продолжит держать
// файлы resources\converter (из-за чего uninstall не может их снести) и память.
// taskkill /T гасит всё дерево; на *nix шлём сигнал группе процессов.
//
// ВАЖНО: сигнал группе работает ТОЛЬКО если ребёнок запущен своей группой —
// см. SPAWN_DETACHED ниже. Без него ребёнок сидит в группе Electron, kill(-pid)
// даёт ESRCH, и всё сваливается в одиночный proc.kill() — то есть ровно в то
// поведение, ради обхода которого функция и написана. На Astra Linux (целевая
// платформа) это означало осиротевший конвертер.
function killTree(proc) {
  if (!proc || proc.killed || proc.pid == null) return;
  if (process.platform === 'win32') {
    try {
      spawn('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { stdio: 'ignore' });
    } catch {
      try { proc.kill(); } catch { /* уже мёртв */ }
    }
  } else {
    try { process.kill(-proc.pid, 'SIGTERM'); } catch { try { proc.kill(); } catch { /* уже мёртв */ } }
  }
}

// Общие опции spawn для наших сервисов: на *nix ребёнок получает СВОЮ группу
// процессов, чтобы killTree мог погасить его вместе с внуками. На Windows
// detached открыл бы отдельное консольное окно поверх интерфейса юриста —
// там дерево гасит taskkill /T, отдельная группа не нужна.
const SPAWN_DETACHED = process.platform !== 'win32';

// Переключение DevTools. Обработчик IPC регистрируется ОДИН раз на уровне
// модуля: внутри createWindow он падал с «Attempted to register a second
// handler», как только окно создавалось повторно (app.on('activate')).
function toggleDevTools() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.webContents.isDevToolsOpened()) {
    mainWindow.webContents.closeDevTools();
  } else {
    mainWindow.webContents.openDevTools();
  }
}

ipcMain.handle('toggle-devtools', () => {
  toggleDevTools();
  return {
    opened: Boolean(mainWindow && !mainWindow.isDestroyed()
      && mainWindow.webContents.isDevToolsOpened())
  };
});

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
      env: { ...process.env, ...(cmd.env || {}) },
      detached: SPAWN_DETACHED
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
      killTree(this.process);
      this.process = null;
    }
  }
}

// --- OCR-конвертер (sidecar): папка converter/ в корне проекта, свой venv ---
const CONVERTER_PORT = process.env.CONVERTER_PORT || '8008';

function resolveConverterCommand() {
  const isWindows = process.platform === 'win32';
  // CONVERTER_DIR — на случай, если конвертер пришлось поставить в ASCII-путь
  // (tesseract/llama-cpp бывают нетерпимы к кириллице в путях).
  // В проде конвертер лежит в resources/converter (extraResources).
  const converterDir = process.env.CONVERTER_DIR
    || (isDev ? path.join(app.getAppPath(), 'converter')
              : path.join(process.resourcesPath, 'converter'));
  const pyRel = path.join(isWindows ? 'Scripts' : 'bin', isWindows ? 'python.exe' : 'python');
  const entry = path.join(converterDir, 'main.py');
  // Лаунчер поднимает конвертер на CONVERTER_PORT без правок его кода (порт у
  // upstream захардкожен на 8000). В dev — из исходников бэкенда; в проде
  // исходников нет, копия лаунчера лежит рядом с конвертером (кладётся при сборке).
  const launcher = isDev
    ? path.join(app.getAppPath(), 'python-backend', 'app', 'run_converter.py')
    : path.join(converterDir, 'run_converter.py');

  let command;
  const extraEnv = {};
  if (isDev) {
    // install_offline.bat конвертера создаёт `.venv`; `venv` — фолбэк на ручную установку
    command = [path.join(converterDir, '.venv', pyRel), path.join(converterDir, 'venv', pyRel)]
      .find((p) => fs.existsSync(p));
  } else {
    // Прод: бандленный pyruntime (полноценный Python 3.12), зависимости
    // конвертера подключаем из .venv/site-packages через PYTHONPATH —
    // .venv сам по себе не самодостаточен (см. scripts/assemble-converter.ps1).
    const runtimePy = path.join(converterDir, 'pyruntime', isWindows ? 'python.exe' : path.join('bin', 'python'));
    command = fs.existsSync(runtimePy) ? runtimePy : undefined;
    const sitePkgs = [
      path.join(converterDir, '.venv', 'Lib', 'site-packages'),
      path.join(converterDir, '.venv', 'lib', 'python3.12', 'site-packages')
    ].find((p) => fs.existsSync(p));
    if (sitePkgs) extraEnv.PYTHONPATH = sitePkgs;
  }

  if (!command || !fs.existsSync(entry)) {
    console.warn(`[converter] not installed at ${converterDir}`);
    return null;
  }
  return {
    command,
    args: [launcher],
    cwd: converterDir,
    env: { CONVERTER_PORT, CONVERTER_DIR: converterDir, SBERACT_DATA_DIR: app.getPath('userData'), ...extraEnv }
  };
}

const converterService = new ManagedService({
  name: 'converter',
  resolveCommand: resolveConverterCommand,
  healthUrl: `http://127.0.0.1:${CONVERTER_PORT}/health`,
  // Холодный старт с LLM — с запасом
  startTimeoutMs: 180000
});

// Команда запуска бэкенда. В проде — собранный PyInstaller-бинарник (Python на
// машине пользователя не нужен). В dev — интерпретатор venv + main.py из исходников.
function resolveBackendCommand() {
  const isWindows = process.platform === 'win32';
  if (isDev) {
    const pythonDir = isWindows ? 'Scripts' : 'bin';
    const pythonExe = isWindows ? 'python.exe' : 'python';
    const venvPath = path.join(__dirname, '../python-backend/venv', pythonDir, pythonExe);
    const command = fs.existsSync(venvPath) ? venvPath : (isWindows ? 'python' : 'python3');
    const appRoot = app.getAppPath();
    return {
      command,
      args: [path.join(appRoot, 'python-backend', 'app', 'main.py')],
      cwd: path.join(appRoot, 'python-backend', 'app'),
      env: { PYTHONPATH: path.join(__dirname, '../python-backend') }
    };
  }
  // extraResources кладёт onedir-сборку бэкенда в resources/backend/
  const binName = isWindows ? 'SberAct.exe' : 'SberAct';
  const backendBin = path.join(process.resourcesPath, 'backend', binName);
  return { command: backendBin, args: [], cwd: path.dirname(backendBin), env: {} };
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
    const backend = resolveBackendCommand();

    console.log(`Starting Python backend with: ${backend.command} ${backend.args.join(' ')}`);

    // app.getPath('home') как последний рубеж: если HOME и USERPROFILE обе
    // пусты, path.join(undefined, …) бросает TypeError — ДО spawn. Бросок
    // съедался внешним catch, окно открывалось, каждый запрос падал, и в
    // интерфейсе не было ни намёка на причину.
    const homeDir = process.env.HOME || process.env.USERPROFILE || app.getPath('home');
    const pathSep = process.platform === 'win32' ? ';' : ':';

    pythonProcess = spawn(backend.command, backend.args, {
      cwd: backend.cwd,
      detached: SPAWN_DETACHED,
      env: {
        ...process.env,
        ...backend.env,
        // Записываемые данные (generated/, temp/) — вне папки установки, переживают обновление
        SBERACT_DATA_DIR: app.getPath('userData'),
        // Бэкенд владеет конвертером: в проде его дефолтный путь (от __file__) неверен
        // во frozen — явно указываем resources/converter (куда его кладёт установщик).
        ...(isDev ? {} : { CONVERTER_DIR: path.join(process.resourcesPath, 'converter'), CONVERTER_PORT }),
        PATH: (process.env.PATH || '') + pathSep + path.join(homeDir, '.local/bin')
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
    // DevTools в проде — только по требованию (SBERACT_DEVTOOLS=1) или горячей клавишей.
    if (process.env.SBERACT_DEVTOOLS === '1') {
      mainWindow.webContents.openDevTools();
    }
  }

  // Горячие клавиши DevTools: F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+Shift+D.
  // Все — на уровне ОКНА. Раньше Ctrl+Shift+D висел на globalShortcut: тот
  // перехватывает клавишу во всей системе (даже когда окно не в фокусе),
  // регистрировался по setTimeout и слетал на закрытии первого окна.
  // preventDefault на F12 подавляет акселератор меню — иначе переключение
  // сработало бы дважды и визуально ничего бы не произошло.
  mainWindow.webContents.on('before-input-event', (event, input) => {
    const key = (input.key || '').toLowerCase();
    // F12 и Ctrl+Shift+D переключают, Ctrl+Shift+I/J только открывают —
    // поведение сохранено ровно как было, менять его тут не место.
    if (input.key === 'F12' || input.code === 'F12') {
      event.preventDefault();
      toggleDevTools();
      return;
    }
    if (input.control && input.shift && key === 'd') {
      event.preventDefault();
      toggleDevTools();
      return;
    }
    if (input.control && input.shift && (key === 'i' || key === 'j')) {
      event.preventDefault();
      if (!mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.openDevTools();
      }
    }
  });

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

  console.log('[main] DevTools: F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+Shift+D, меню «Вид»');
}

app.whenReady().then(() => {
  startPythonBackend();
  createWindow();

  // Офлайн-обновление с флешки: конвертер лежит рядом с backend'ом в resources.
  initUpdater({
    getMainWindow: () => mainWindow,
    converterDir: isDev
      ? path.join(app.getAppPath(), 'converter')
      : path.join(process.resourcesPath, 'converter'),
    backendPort: 8000
  });

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
    // Дерево backend'а включает дочерний конвертер — гасим одним taskkill /T,
    // чтобы python.exe не осиротел (иначе живёт и блокирует uninstall).
    killTree(pythonProcess);
    converterService.stop(); // на случай внешнего/легаси-запуска через ManagedService
    shutdownUpdater(); // закрываем локальный feed-сервер обновления
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

// Версия приложения — единый источник: корневой package.json (его же берёт
// electron-builder для инсталлятора и latest.yml). Показывается в шапке фронта.
ipcMain.handle('app:get-version', () => app.getVersion());

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
