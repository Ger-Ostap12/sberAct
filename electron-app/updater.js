// Офлайн-обновление с флешки.
//
// Два независимых канала за одной кнопкой «Проверить обновления»:
//   1. app + backend — через electron-updater (NSIS-артефакт latest.yml + .exe).
//      electron-updater умеет только http(s), не file://, поэтому над выбранной
//      папкой на флешке поднимаем локальный статический HTTP-сервер (с Range —
//      апдейтер качает по диапазонам) и указываем feed на 127.0.0.1.
//   2. converter (~6 ГБ, вне NSIS-payload) — своя синхронизация по манифесту
//      SHA-256: копируем только изменённые/новые файлы, удаляем исчезнувшие.
//      Конвертер меняется редко — тогда папки converter/ на флешке просто нет,
//      и этот канал мгновенно «нет обновления».
//
// Всё работает офлайн: сеть не нужна, источник — папка SberAct-Update/ на флешке.

const { app, ipcMain, dialog } = require('electron');
const http = require('http');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

// Имя папки-источника на флешке и файлов внутри неё.
const UPDATE_DIR_NAME = 'SberAct-Update';
const CONVERTER_SUBDIR = 'converter';
const CONVERTER_MANIFEST = 'converter-manifest.json';

let deps = null; // { getMainWindow, converterDir, backendPort }
let sourceDir = null; // выбранная/найденная папка SberAct-Update
let feedServer = null; // http.Server над sourceDir
let feedBaseUrl = null;

function send(channel, payload) {
  const win = deps && deps.getMainWindow && deps.getMainWindow();
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

// --- Локальный статический сервер над папкой обновления (с поддержкой Range) ---
function startFeedServer(rootDir) {
  return new Promise((resolve, reject) => {
    const root = path.resolve(rootDir);
    const server = http.createServer((req, res) => {
      try {
        const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const filePath = path.join(root, urlPath);
        // Защита от выхода за пределы корня (path traversal). Сравнение по
        // относительному пути, а не startsWith: при корне C:\upd префиксная
        // проверка пропускала C:\update\... — сосед по имени считался «внутри».
        const rel = path.relative(root, filePath);
        if (rel.startsWith('..') || path.isAbsolute(rel)) {
          res.writeHead(403);
          res.end();
          return;
        }
        fs.stat(filePath, (err, st) => {
          if (err || !st.isFile()) {
            res.writeHead(404);
            res.end();
            return;
          }
          const range = req.headers.range;
          let stream;
          if (range) {
            const m = /bytes=(\d*)-(\d*)/.exec(range);
            let start = m && m[1] ? parseInt(m[1], 10) : 0;
            let end = m && m[2] ? parseInt(m[2], 10) : st.size - 1;
            if (Number.isNaN(start)) start = 0;
            if (Number.isNaN(end) || end >= st.size) end = st.size - 1;
            res.writeHead(206, {
              'Content-Range': `bytes ${start}-${end}/${st.size}`,
              'Accept-Ranges': 'bytes',
              'Content-Length': end - start + 1,
              'Content-Type': 'application/octet-stream'
            });
            stream = fs.createReadStream(filePath, { start, end });
          } else {
            res.writeHead(200, {
              'Content-Length': st.size,
              'Accept-Ranges': 'bytes',
              'Content-Type': 'application/octet-stream'
            });
            stream = fs.createReadStream(filePath);
          }
          // Источник обновления — СЪЁМНЫЙ носитель: чтение может оборваться на
          // любом байте (флешку выдернули, износ). Неперехваченный 'error' на
          // стриме — это uncaughtException, то есть падение main-процесса без
          // окна и без сообщения. Ровно тот сценарий, ради которого фича есть.
          stream.on('error', (streamErr) => {
            console.error('[updater] сбой чтения', filePath, streamErr);
            res.destroy();
          });
          // Клиент ушёл (отменил загрузку, закрылось окно) — иначе дескриптор
          // остаётся открытым и носитель не даёт себя безопасно извлечь.
          res.on('close', () => stream.destroy());
          stream.pipe(res);
        });
      } catch (_e) {
        res.writeHead(500);
        res.end();
      }
    });
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, port });
    });
  });
}

async function ensureFeed(dir) {
  // Пересоздаём сервер, если сменился источник.
  if (feedServer && sourceDir === dir) return;
  if (feedServer) {
    try { feedServer.closeAllConnections(); } catch (_e) { /* Node < 18.2 */ }
    try { feedServer.close(); } catch (_e) { /* уже закрыт */ }
    feedServer = null;
  }
  const { server, port } = await startFeedServer(dir);
  feedServer = server;
  feedBaseUrl = `http://127.0.0.1:${port}/`;
  sourceDir = dir;
}

// --- Автопоиск папки обновления на съёмных дисках ---
function autoDetectSource() {
  if (process.platform === 'win32') {
    // Перебираем буквы дисков; берём первый, где есть SberAct-Update/latest.yml.
    for (let c = 'D'.charCodeAt(0); c <= 'Z'.charCodeAt(0); c++) {
      const dir = path.join(`${String.fromCharCode(c)}:\\`, UPDATE_DIR_NAME);
      if (fs.existsSync(path.join(dir, 'latest.yml')) ||
          fs.existsSync(path.join(dir, CONVERTER_MANIFEST))) {
        return dir;
      }
    }
    return null;
  }
  // Linux: типовые точки монтирования флешек.
  const mounts = ['/media', '/run/media', '/mnt'];
  for (const base of mounts) {
    if (!fs.existsSync(base)) continue;
    const stack = [base];
    // Неглубокий обход: base/<user>/<label>/SberAct-Update
    for (let depth = 0; depth < 3 && stack.length; depth++) {
      const next = [];
      for (const d of stack) {
        let entries = [];
        try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch (_e) { continue; }
        for (const e of entries) {
          if (!e.isDirectory()) continue;
          const full = path.join(d, e.name);
          if (e.name === UPDATE_DIR_NAME &&
              (fs.existsSync(path.join(full, 'latest.yml')) ||
               fs.existsSync(path.join(full, CONVERTER_MANIFEST)))) {
            return full;
          }
          next.push(full);
        }
      }
      stack.length = 0;
      stack.push(...next);
    }
  }
  return null;
}

// --- converter-sync ---
function sha256File(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    const s = fs.createReadStream(file);
    s.on('error', reject);
    s.on('data', (d) => h.update(d));
    s.on('end', () => resolve(h.digest('hex')));
  });
}

function readManifest(file) {
  try {
    // PowerShell (Out-File -Encoding utf8) пишет BOM — JSON.parse на нём падает.
    const raw = fs.readFileSync(file, 'utf8').replace(/^﻿/, '');
    return JSON.parse(raw);
  } catch (_e) {
    return null;
  }
}

// Что именно надо докопировать/удалить. Чистая функция (никакого модульного
// состояния) — она же покрыта тестами scripts/tests/converter-sync.test.js.
//
// Манифесты сравниваем по path+sha, не хэшируя 6 ГБ на каждой проверке, НО
// дополнительно смотрим на файл на диске: installer.nsh копирует конвертер
// шелл-копией и обрыв копирования не замечает, а манифест (мелкий файл)
// доезжает всегда — установка выглядит целой, будучи наполовину пустой. Именно
// так приезжали сборки, где из 33 682 файлов доехало 19 163. statSync по
// ~37 тыс. путей занимает секунды, в отличие от хэширования.
function planConverterSync(flashManifest, installedManifest, converterDir, statFile) {
  const stat = statFile || ((p) => {
    try { return fs.statSync(p); } catch (_e) { return null; }
  });

  const installedByPath = new Map();
  if (installedManifest && Array.isArray(installedManifest.files)) {
    for (const f of installedManifest.files) installedByPath.set(f.path, f.sha256);
  }

  const toCopy = [];
  let bytes = 0;
  for (const f of flashManifest.files) {
    const known = installedByPath.get(f.path);
    if (known !== undefined && known !== f.sha256) {
      toCopy.push(f); // манифесты расходятся — файл точно изменился
      bytes += f.size || 0;
      continue;
    }
    const st = stat(path.join(converterDir, f.path));
    if (!st || (f.size != null && st.size !== f.size)) {
      toCopy.push(f);
      bytes += f.size || 0;
    }
  }

  // Файлы, исчезнувшие в новом манифесте — под удаление.
  const flashPaths = new Set(flashManifest.files.map((f) => f.path));
  const toDelete = [];
  for (const p of installedByPath.keys()) {
    if (!flashPaths.has(p)) toDelete.push(p);
  }

  return { toCopy, toDelete, bytes };
}

function diffConverter() {
  if (!sourceDir) return { available: false };
  const flashManifestPath = path.join(sourceDir, CONVERTER_MANIFEST);
  const flashManifest = readManifest(flashManifestPath);
  if (!flashManifest || !Array.isArray(flashManifest.files)) {
    return { available: false }; // на флешке нет обновления конвертера
  }
  const converterDir = deps.converterDir;
  const installedManifest = readManifest(path.join(converterDir, CONVERTER_MANIFEST));

  const { toCopy, toDelete, bytes } =
    planConverterSync(flashManifest, installedManifest, converterDir);

  const changed = toCopy.length > 0 || toDelete.length > 0;
  return {
    available: changed,
    version: flashManifest.version || null,
    installedVersion: installedManifest ? installedManifest.version || null : null,
    filesChanged: toCopy.length,
    filesDeleted: toDelete.length,
    bytes,
    _plan: { toCopy, toDelete, flashManifestPath }
  };
}

async function applyConverterSync(plan, flashManifestPath) {
  const converterDir = deps.converterDir;
  const srcRoot = path.join(sourceDir, CONVERTER_SUBDIR);
  const total = plan.toCopy.length + plan.toDelete.length;
  let done = 0;

  // Останавливаем конвертер, иначе его файлы под Windows заблокированы.
  try {
    await fetch(`http://127.0.0.1:${deps.backendPort}/converter/stop`, { method: 'POST' });
  } catch (_e) { /* не поднят — файлы и так свободны */ }

  for (const f of plan.toCopy) {
    const src = path.join(srcRoot, f.path);
    const dst = path.join(converterDir, f.path);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
    // Проверяем целостность копии по SHA — тихий сбой копирования недопустим.
    if (f.sha256) {
      const got = await sha256File(dst);
      if (got !== f.sha256) {
        throw new Error(`Контрольная сумма не сошлась после копии: ${f.path}`);
      }
    }
    done += 1;
    send('update:converter-progress', { done, total });
  }
  for (const rel of plan.toDelete) {
    try { fs.rmSync(path.join(converterDir, rel), { force: true }); } catch (_e) { /* уже нет */ }
    done += 1;
    send('update:converter-progress', { done, total });
  }
  // Обновляем установленный манифест (копией с флешки) — это новая «истина».
  try {
    fs.copyFileSync(flashManifestPath, path.join(converterDir, CONVERTER_MANIFEST));
  } catch (_e) { /* не критично для работы, но желательно */ }
}

// --- Инициализация и IPC ---
function initUpdater(dependencies) {
  deps = dependencies;

  // Ленивая загрузка: в dev-режиме electron-updater не нужен и кидает
  // «app is not packed». Грузим только во frozen.
  let autoUpdater = null;
  function getAutoUpdater() {
    if (!app.isPackaged) return null;
    if (!autoUpdater) {
      ({ autoUpdater } = require('electron-updater'));
      autoUpdater.autoDownload = false;
      autoUpdater.autoInstallOnAppQuit = false;
      autoUpdater.on('download-progress', (p) => send('update:progress', p));
      autoUpdater.on('error', (e) => send('update:error', String(e && e.message || e)));
    }
    return autoUpdater;
  }

  // Выбор источника вручную (диалог) или автопоиск.
  ipcMain.handle('update:pick-source', async () => {
    const win = deps.getMainWindow && deps.getMainWindow();
    const res = await dialog.showOpenDialog(win, {
      title: 'Выберите папку обновления (SberAct-Update) на флешке',
      properties: ['openDirectory']
    });
    if (res.canceled || !res.filePaths.length) return { ok: false };
    sourceDir = res.filePaths[0];
    return { ok: true, path: sourceDir };
  });

  ipcMain.handle('update:auto-detect', () => {
    const found = autoDetectSource();
    if (found) sourceDir = found;
    return { ok: !!found, path: found || null };
  });

  // Проверка обоих каналов. Возвращает состояние для UI.
  ipcMain.handle('update:check', async (_e, chosenPath) => {
    if (!app.isPackaged) {
      return { ok: false, error: 'Обновление доступно только в установленном приложении' };
    }
    const dir = chosenPath || sourceDir || autoDetectSource();
    if (!dir || !fs.existsSync(dir)) {
      return { ok: false, error: 'Папка обновления не найдена. Вставьте флешку или выберите папку вручную.' };
    }
    sourceDir = dir;

    const result = { ok: true, source: dir, app: { available: false }, converter: { available: false } };

    // Канал 1: app+backend через electron-updater (если на флешке есть latest.yml).
    if (fs.existsSync(path.join(dir, 'latest.yml'))) {
      try {
        await ensureFeed(dir);
        const au = getAutoUpdater();
        au.setFeedURL({ provider: 'generic', url: feedBaseUrl });
        const info = await au.checkForUpdates();
        const remote = info && info.updateInfo ? info.updateInfo.version : null;
        const isNewer = remote && remote !== app.getVersion();
        result.app = {
          available: !!isNewer,
          version: remote,
          currentVersion: app.getVersion()
        };
      } catch (err) {
        result.app = { available: false, error: String(err && err.message || err) };
      }
    }

    // Канал 2: converter-sync.
    const conv = diffConverter();
    result.converter = {
      available: conv.available,
      version: conv.version,
      installedVersion: conv.installedVersion,
      filesChanged: conv.filesChanged || 0,
      filesDeleted: conv.filesDeleted || 0,
      bytes: conv.bytes || 0
    };
    result._converterPlan = conv._plan || null;

    return result;
  });

  // Скачивание app-обновления (в staging electron-updater). Прогресс — событиями.
  ipcMain.handle('update:download', async () => {
    const au = getAutoUpdater();
    if (!au) return { ok: false, error: 'Недоступно в dev' };
    try {
      await au.downloadUpdate();
      return { ok: true };
    } catch (err) {
      return { ok: false, error: String(err && err.message || err) };
    }
  });

  // Применение: сначала converter-sync (если есть), затем перезапуск/установка.
  // appDownloaded — качали ли app-обновление; converterPlan — из update:check.
  ipcMain.handle('update:apply', async (_e, opts) => {
    const { appDownloaded, converterPlan } = opts || {};
    try {
      if (converterPlan && (converterPlan.toCopy.length || converterPlan.toDelete.length)) {
        await applyConverterSync(converterPlan, converterPlan.flashManifestPath);
      }
      if (appDownloaded) {
        const au = getAutoUpdater();
        // quitAndInstall сам гасит app (before-quit → killTree), ставит NSIS
        // тихо и перезапускает. Конвертер сохраняется (customRemoveFiles).
        setImmediate(() => au.quitAndInstall(false, true));
        return { ok: true, restarting: true };
      }
      // Обновился только конвертер — перезапускаем, чтобы бэкенд переинициализировал его.
      setImmediate(() => { app.relaunch(); app.exit(0); });
      return { ok: true, restarting: true };
    } catch (err) {
      return { ok: false, error: String(err && err.message || err) };
    }
  });
}

function shutdownUpdater() {
  if (feedServer) {
    // close() перестаёт принимать новые соединения, но ЖДЁТ закрытия открытых,
    // а electron-updater держит keep-alive — сервер бы не освободился, и выход
    // упёрся бы в трёхсекундный бюджет before-quit. Рвём соединения явно.
    try { feedServer.closeAllConnections(); } catch (_e) { /* Node < 18.2 */ }
    try { feedServer.close(); } catch (_e) { /* игнор */ }
    feedServer = null;
  }
}

// planConverterSync и startFeedServer экспортируются ради тестов
// (scripts/tests/converter-sync.test.js, scripts/tests/feed-server.test.js):
// CRA-jest видит только electron-app/src, до main-процесса он не достаёт.
module.exports = { initUpdater, shutdownUpdater, planConverterSync, startFeedServer };
