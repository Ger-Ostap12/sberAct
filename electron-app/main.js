const { app, BrowserWindow, ipcMain, dialog, Menu, clipboard } = require('electron');

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
const os = require('os');
const isDev = require('electron-is-dev');
const { initUpdater, shutdownUpdater } = require('./updater');
const converterUpdate = require('./converter-update');
const { createServiceLog, captureUtf8Output } = require('./serviceLog');
const { createDiagnostics, redact, sanitize, reportedFailure: reportFailure } = require('./diagnostics');

// Логи сервисов — по одному на сервис, создаются при первом обращении.
const serviceLogs = new Map();

/** Лог сервиса в папке логов приложения (её же показывает «Открыть логи»). */
function serviceLog(name) {
  if (!serviceLogs.has(name)) {
    let dir;
    try {
      dir = app.getPath('logs');
    } catch (_) {
      dir = path.join(app.getPath('userData'), 'logs');
    }
    const fileLog = createServiceLog(name, dir);
    serviceLogs.set(name, {
      file: fileLog.file,
      write: (data, channel) => { diagnostics().ingest(name, data, channel); fileLog.write(redact(data)); },
      flush: () => { diagnostics().flush(name, 'stdout'); diagnostics().flush(name, 'stderr'); },
      line: text => { diagnostics().record({ component: name, level: 'info', message: text }); fileLog.line(redact(text)); },
    });
  }
  return serviceLogs.get(name);
}

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
let diagnosticJournal;
function diagnostics() {
  if (!diagnosticJournal) {
    let dir;
    try { dir = app.getPath('logs'); } catch (_) { dir = path.join(app.getPath('userData'), 'logs'); }
    diagnosticJournal = createDiagnostics(dir, entry => {
      for (const window of BrowserWindow.getAllWindows()) {
        if (!window.isDestroyed()) window.webContents.send('diagnostic:event', entry);
      }
    });
  }
  return diagnosticJournal;
}
function reportedFailure(error, fallback = 'Не удалось выполнить операцию.') {
  return reportFailure(error, fallback, diagnostics().record);
}
for (const [method, level] of [['log', 'info'], ['warn', 'warning'], ['error', 'error']]) {
  const original = console[method].bind(console);
  console[method] = (...args) => {
    original(...args);
    try {
      if (/^Python (stdout|stderr):|^\\[(backend|converter)\\]/.test(String(args[0]))) return;
      diagnostics().record({ component: 'electron', level,
        message: args.map(item => item instanceof Error ? item.stack : typeof item === 'string' ? item : JSON.stringify(item)).join(' ') });
    } catch (_) { /* Журнал не мешает запуску. */ }
  };
}
process.on('uncaughtExceptionMonitor', error => {
  diagnostics().record({ component: 'electron', level: 'error', message: error.stack || String(error) });
});
process.on('unhandledRejection', error => {
  diagnostics().record({ component: 'electron', level: 'error', message: error && error.stack || String(error) });
});
ipcMain.handle('diagnostics:record', (_event, entry) => {
  if (entry && typeof entry.message === 'string') diagnostics().record(entry);
});
ipcMain.handle('diagnostics:snapshot', async () => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2000);
  let backend;
  try {
    const response = await fetch('http://127.0.0.1:8000/diagnostics', { signal: controller.signal });
    if (response.ok) {
      backend = await response.json();
      for (const entry of backend.events || []) diagnostics().record(entry);
    }
  } catch (_) { backend = { unavailable: true }; }
  finally { clearTimeout(timer); }
  return { ...diagnostics().snapshot(), appVersion: app.getVersion(),
    platform: process.platform, electronVersion: process.versions.electron,
    nodeVersion: process.versions.node, pythonVersion: backend?.pythonVersion,
    backendDiagnosticsAvailable: Array.isArray(backend?.events) };
});
function reportText(text) {
  if (typeof text !== 'string' || text.length > 8 * 1024 * 1024) throw Object.assign(new Error('Отчёт слишком большой.'), { code: 'REPORT_TOO_LARGE' });
  return JSON.stringify(sanitize(JSON.parse(text)), null, 2);
}
ipcMain.handle('diagnostics:copy', (_event, text) => {
  try { clipboard.writeText(reportText(text)); return { copied: true }; }
  catch (error) { return { copied: false, ...reportedFailure(error, 'Не удалось скопировать отчёт.') }; }
});
ipcMain.handle('diagnostics:save', async (_event, text) => {
  try {
    const report = reportText(text);
    const result = await dialog.showSaveDialog(mainWindow, {
      title: 'Сохранить отчёт об ошибке', defaultPath: 'SberAct-diagnostics.json',
      filters: [{ name: 'Отчёт диагностики', extensions: ['json'] }],
    });
    if (result.canceled || !result.filePath) return { saved: false };
    fs.writeFileSync(result.filePath, report, 'utf8');
    return { saved: true };
  } catch (error) {
    diagnostics().record({ component: 'electron', level: 'error', message: error.stack || String(error) });
    return { saved: false, ...reportedFailure(error, 'Не удалось сохранить отчёт.') };
  }
});


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

    const log = serviceLog(this.name);
    console.log(`[${this.name}] starting: ${cmd.command} ${(cmd.args || []).join(' ')}`);
    log.line(`starting: ${cmd.command} ${(cmd.args || []).join(' ')} (cwd ${cmd.cwd})`);
    this.external = false;
    this.process = spawn(cmd.command, cmd.args || [], {
      cwd: cmd.cwd,
      env: { ...process.env, ...(cmd.env || {}), PYTHONIOENCODING: 'utf-8:backslashreplace', PYTHONUTF8: '1' },
      detached: SPAWN_DETACHED
    });
    captureUtf8Output(this.process.stdout, (d) => { log.write(d, 'stdout'); console.log(`[${this.name}] ${d}`); });
    captureUtf8Output(this.process.stderr, (d) => { log.write(d, 'stderr'); console.error(`[${this.name}] ${d}`); });
    this.process.on('error', (e) => {
      log.line(`spawn error: ${e && e.message ? e.message : e}`);
      console.error(`[${this.name}] spawn error:`, e);
    });
    this.process.on('close', (code) => {
      log.flush();
      log.line(`exited with code ${code}`);
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
        log.line('healthy');
        console.log(`[${this.name}] healthy`);
        return { ok: true, external: false };
      }
      await new Promise((r) => setTimeout(r, this.healthIntervalMs));
    }
    // Именно этот случай и не удавалось разобрать на машине пользователя.
    log.line(`НЕ ПОДНЯЛСЯ за ${Math.round(this.startTimeoutMs / 1000)} с, ${this.healthUrl} молчит`);
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
        PYTHONIOENCODING: 'utf-8:backslashreplace',
        PYTHONUTF8: '1',
        // Записываемые данные (generated/, temp/) — вне папки установки, переживают обновление
        SBERACT_DATA_DIR: app.getPath('userData'),
        // Бэкенд владеет конвертером: в проде его дефолтный путь (от __file__) неверен
        // во frozen — явно указываем resources/converter (куда его кладёт установщик).
        ...(isDev ? {} : { CONVERTER_DIR: path.join(process.resourcesPath, 'converter'), CONVERTER_PORT }),
        PATH: (process.env.PATH || '') + pathSep + path.join(homeDir, '.local/bin')
      }
    });

    const log = serviceLog('backend');
    log.line(`starting: ${backend.command} ${(backend.args || []).join(' ')} (cwd ${backend.cwd})`);

    captureUtf8Output(pythonProcess.stdout, (data) => {
      log.write(data, 'stdout');
      console.log(`Python stdout: ${data}`);
    });

    captureUtf8Output(pythonProcess.stderr, (data) => {
      log.write(data, 'stderr');
      console.error(`Python stderr: ${data}`);
    });

    pythonProcess.on('error', (error) => {
      log.line(`spawn error: ${error && error.message ? error.message : error}`);
      console.error('Failed to start Python backend:', error);
    });

    pythonProcess.on('close', (code) => {
      log.flush();
      log.line(`exited with code ${code}`);
      console.log(`Python backend exited with code ${code}`);
    });
  } catch (error) {
    try {
      serviceLog('backend').line(`не удалось запустить: ${error && error.message ? error.message : error}`);
    } catch (_) {
      /* лог недоступен — остаётся консоль */
    }
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
      // ВНИМАНИЕ: выключено и в ПРОДЕ, а не только в разработке (как обещал
      // прежний комментарий). В десктопе запросы идут через preload/IPC, но
      // браузерный фолбэк (services/webApi.ts) ходит fetch'ем с file://-origin
      // на 127.0.0.1:8000 — это межисточниковый запрос, и включение флага
      // упрётся в CORS. Побочный вред: настоящие ошибки CORS в рендере не
      // видны, на чём уже терялось время (память false-cors-stale-keepalive).
      // Включать только вместе с проверкой на СОБРАННОМ установщике — см. §S.3.
      webSecurity: false
    },
    icon: resolveIcon(),
    title: 'SberAct Document Generator'
  });

  mainWindow.webContents.on('preload-error', (_event, _path, error) => {
    diagnostics().record({ component: 'preload', level: 'error', code: 'PRELOAD_FAILED',
      message: error.stack || String(error) });
  });
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    diagnostics().record({ component: 'interface', level: 'error', code: 'RENDERER_STOPPED',
      message: 'Процесс интерфейса завершился: ' + details.reason + '; exit=' + details.exitCode });
  });
  mainWindow.on('unresponsive', () => {
    diagnostics().record({ component: 'interface', level: 'error', code: 'WINDOW_UNRESPONSIVE',
      message: 'Окно приложения перестало отвечать.' });
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

// Конвертер весит ~3.5 ГБ, поэтому заранее греем его только там, где память
// не в обрез. На 8 ГБ он поднимется по входу в раздел конвертации, как раньше.
const WARM_CONVERTER_MIN_RAM_GB = 12;

async function warmConverterIfRoomy() {
  const ramGb = os.totalmem() / 1024 ** 3;
  if (ramGb < WARM_CONVERTER_MIN_RAM_GB) {
    console.log(`Конвертер не греем заранее: ОЗУ ${ramGb.toFixed(1)} ГБ`);
    return;
  }
  // Ждём сам backend: он поднимается секунды, а на слабой машине и дольше.
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const res = await fetch('http://127.0.0.1:8000/health');
      if (res.ok) break;
    } catch (_) { /* ещё не поднялся */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
  try {
    await fetch('http://127.0.0.1:8000/converter/start', { method: 'POST' });
    console.log('Конвертер прогрет заранее');
  } catch (e) {
    console.log('Прогрев конвертера не удался, поднимется по требованию:', e.message);
  }
}

app.whenReady().then(async () => {
  const updateConverterDir = process.env.CONVERTER_DIR || (isDev ? path.join(app.getAppPath(),'converter') : path.join(process.resourcesPath,'converter'));
  let pendingConverter = null;
  if (!isDev && process.platform === 'win32') {
    try {
      await converterUpdate.transaction('Recover',updateConverterDir);
      pendingConverter = await converterUpdate.state(updateConverterDir);
    } catch (error) {
      dialog.showErrorBox('Восстановление конвертера',String(error.message || error));
      app.quit();
      return;
    }
  }
  console.log(`[logs] ${path.dirname(serviceLog('backend').file)}`);
  startPythonBackend();
  createWindow();
  if (pendingConverter && pendingConverter.phase === 'pending') {
    converterUpdate.finishPendingUpdate({converterDir:updateConverterDir,backendPort:8000,currentVersion:app.getVersion()})
      .then(result => {
        if (result.rolledBack) dialog.showErrorBox('Обновление конвертера отменено',
          result.message + '\nВосстановлена предыдущая версия модуля конвертации.');
        if (result.failed) dialog.showErrorBox("\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0435\u0440\u0430 \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430", result.message + "\n\u041f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0435\u0439 \u0432\u0435\u0440\u0441\u0438\u0438 \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0435\u0440\u0430 \u043d\u0435 \u0431\u044b\u043b\u043e. \u0423\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u0438\u0441\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d\u044b\u0439 \u043a\u043e\u043c\u043f\u043b\u0435\u043a\u0442.");
      })
      .catch(error => dialog.showErrorBox('Проверка конвертера',String(error.message || error)));
  } else {
    warmConverterIfRoomy();
  }

  // Офлайн-обновление с флешки: конвертер лежит рядом с backend'ом в resources.
  initUpdater({
    getMainWindow: () => mainWindow,
    converterDir: updateConverterDir,
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
      throw new Error('HTTP ' + response.status + ': ' + await response.text());
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Error generating document:', error);
    return reportedFailure(error, 'Не удалось сформировать документы.');
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
    // Имя акта считает бэкенд (подпись шаблона) и кладёт в заголовок.
    const suggestedName = fileNameFromDisposition(
      response.headers.get('content-disposition'), `Судебный_акт_${documentId}.docx`);

    const result = await dialog.showSaveDialog(mainWindow, {
      title: 'Сохранить документ',
      defaultPath: suggestedName,
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
    return reportedFailure(error, 'Не удалось сохранить документ.');
  }
});

// API для скачивания всех документов
// Имя файла из заголовка ответа. filename* читаем первым: в нём кириллица,
// а в обычном filename — её ASCII-замена для старых клиентов.
function fileNameFromDisposition(header, fallback) {
  const cd = header || '';
  const utf8 = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch (e) {
      return fallback;
    }
  }
  const plain = cd.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1].trim() : fallback;
}

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

    // Имя архива считает бэкенд (ФИО должника + дата) и кладёт в заголовок.
    const suggestedName = fileNameFromDisposition(
      response.headers.get('content-disposition'), 'generated_documents.zip');

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
      defaultPath: suggestedName,
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
    return reportedFailure(error, 'Не удалось сохранить архив.');
  }
});

// API для получения путей скачивания
ipcMain.handle('get-download-paths', async () => {
  try {
    const response = await fetch('http://localhost:8000/download-paths');

    if (!response.ok) {
      throw new Error('HTTP ' + response.status + ': ' + await response.text());
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Error getting download paths:', error);
    return reportedFailure(error, 'Не удалось получить папки сохранения.');
  }
});
