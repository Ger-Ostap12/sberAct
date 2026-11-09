const { app, ipcMain, dialog } = require('electron');
const http = require('http');
const path = require('path');
const fs = require('fs');
const semver = require('semver');
const { inspectPackage, compareConverter, recordConverterManifest, readJson } = require('./update-package');
const converterUpdate = require('./converter-update');

// Имя папки-источника на флешке и файлов внутри неё.
const UPDATE_DIR_NAME = 'SberAct-Update';
const CONVERTER_MANIFEST = 'converter-manifest.json';

let deps = null; // { getMainWindow, converterDir, backendPort }
let sourceDir = null; // выбранная/найденная папка SberAct-Update
let feedServer = null; // http.Server над sourceDir
let feedBaseUrl = null;
let feedRoot = null;

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
  if (feedServer && feedRoot === dir) return;
  if (feedServer) {
    try { feedServer.closeAllConnections(); } catch (_e) { /* Node < 18.2 */ }
    try { feedServer.close(); } catch (_e) { /* уже закрыт */ }
    feedServer = null;
  }
  const { server, port } = await startFeedServer(dir);
  feedServer = server;
  feedRoot = dir;
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


function initUpdater(dependencies) {
  deps = dependencies;
  let autoUpdater = null;
  let checked = null;
  let downloaded = false;
  let busy = false;
  function getAutoUpdater() {
    if (!app.isPackaged) return null;
    if (!autoUpdater) {
      ({ autoUpdater } = require('electron-updater'));
      autoUpdater.autoDownload = false;
      autoUpdater.autoInstallOnAppQuit = false;
      autoUpdater.disableDifferentialDownload = true;
      autoUpdater.on('download-progress', p => send('update:progress', p));
      autoUpdater.on('error', error => send('update:error', String(error.message || error)));
    }
    return autoUpdater;
  }
  function invalidate() { checked = null; downloaded = false; }
  ipcMain.handle('update:pick-source', async () => {
    if (busy) return {ok:false};
    const response = await dialog.showOpenDialog(deps.getMainWindow && deps.getMainWindow(), {
      title:'Выберите папку обновления (SberAct-Update) на флешке', properties:['openDirectory']
    });
    if (response.canceled || !response.filePaths.length) return {ok:false};
    sourceDir=response.filePaths[0]; invalidate();
    return {ok:true,path:sourceDir};
  });
  ipcMain.handle('update:auto-detect', () => {
    if (busy) return {ok:false,path:null};
    const found=autoDetectSource();
    if (found) { sourceDir=found; invalidate(); }
    return {ok:!!found,path:found || null};
  });
  async function verifyChecked() {
    if (!checked) throw new Error('Сначала проверьте комплект обновления.');
    const current=await inspectPackage(checked.package.root);
    if (current.identity!==checked.package.identity) throw new Error('Комплект изменился после проверки. Проверьте его заново.');
    return current;
  }
  ipcMain.handle('update:check', async (_event,chosenPath) => {
    if (!app.isPackaged) return {ok:false,error:'Обновление доступно только в установленном приложении'};
    if (busy) return {ok:false,error:'Дождитесь завершения текущей операции обновления.'};
    busy=true;
    invalidate();
    try {
      const pending=await converterUpdate.state(deps.converterDir);
      if (pending) throw new Error('Предыдущее обновление конвертера ещё проверяется. Дождитесь проверки или перезапустите приложение.');
      const dir=chosenPath || sourceDir || autoDetectSource();
      if (!dir || !fs.existsSync(dir)) throw new Error('Папка обновления не найдена. Вставьте флешку или выберите папку вручную.');
      const pkg=await inspectPackage(dir);
      if (semver.lt(pkg.version,app.getVersion())) throw new Error('На носителе более старая версия приложения. Выберите актуальный комплект.');
      const appAvailable=semver.gt(pkg.version,app.getVersion());
      const comparison=pkg.converter ? await compareConverter(deps.converterDir,pkg.converter.manifestData) : null;
      const converterAvailable=!!comparison && !comparison.matches;
      let manifestRecorded=false,warning=null;
      if(comparison && comparison.matches) {
        try {recordConverterManifest(deps.converterDir,pkg.converter.manifestData,comparison);manifestRecorded=true;}
        catch(error){console.error('[updater] record manifest',error);warning="\u0424\u0430\u0439\u043b\u044b OCR \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u044e\u0442, \u043d\u043e \u0441\u0432\u0435\u0434\u0435\u043d\u0438\u044f \u043e \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0435 \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c.";}
      }
      sourceDir=dir;
      if (appAvailable) {
        await ensureFeed(dir);
        const updater=getAutoUpdater();
        updater.setFeedURL({provider:'generic',url:feedBaseUrl});
        await updater.checkForUpdates();
      }
      const converterInstalled=fs.existsSync(path.join(deps.converterDir,'main.py')) &&
        fs.existsSync(path.join(deps.converterDir,'pyruntime','python.exe'));
      let installedVersion=null;
      try { installedVersion=readJson(path.join(deps.converterDir,'converter-manifest.json')).version || null; } catch (_) {}
      checked={package:pkg,appAvailable,converterAvailable};
      return {
        ok:true,source:dir,
        app:{available:appAvailable,version:pkg.version,currentVersion:app.getVersion()},
        converter:{
          available:converterAvailable,installed:converterInstalled,installedVersion,
          status:!pkg.converter ? 'not_in_package' : converterAvailable ? 'update_available' : 'matches_package',
          version:pkg.converter ? pkg.converter.version : null,
          filesChanged:comparison ? comparison.changedFiles : 0,
          filesMissing:comparison ? comparison.missingFiles : 0,
          filesDeleted:comparison ? comparison.extraFiles : 0,
          bytes:comparison ? comparison.changedBytes+comparison.missingBytes : 0,
          removedBytes:comparison ? comparison.extraBytes : 0,
          replacementFiles:pkg.converter ? pkg.converter.manifestData.files.length : 0,
          replacementBytes:pkg.converter ? pkg.converter.unpackedBytes : 0,
          manifestRecorded,warning
        }
      };
    } catch(error) { return {ok:false,error:String(error.message || error)}; }
    finally { busy=false; }
  });
  ipcMain.handle('update:download', async () => {
    if (busy) return {ok:false,error:'Дождитесь завершения текущей операции обновления.'};
    busy=true;
    try {
      if (!checked || !checked.appAvailable) throw new Error('Нет проверенного обновления приложения.');
      await verifyChecked();
      await getAutoUpdater().downloadUpdate();
      downloaded=true;
      return {ok:true};
    } catch(error) { return {ok:false,error:String(error.message || error)}; }
    finally { busy=false; }
  });
  ipcMain.handle('update:apply', async (_event,options) => {
    if (busy) return {ok:false,error:'Дождитесь завершения текущей операции обновления.'};
    busy=true;
    try {
      const pkg=await verifyChecked();
      if (checked.appAvailable && (!downloaded || !options || !options.appDownloaded)) {
        throw new Error('Сначала загрузите проверенный установщик приложения.');
      }
      if (!checked.appAvailable && !checked.converterAvailable) throw new Error('Нет обновления для установки.');
      if (checked.converterAvailable) {
        send('update:converter-progress',{done:0,total:3});
        const prepareOutput=await converterUpdate.transaction('Prepare',deps.converterDir,{
          zip:path.join(pkg.root,pkg.converter.archive),manifest:path.join(pkg.root,pkg.converter.manifest)
        });
        const prepared=JSON.parse(prepareOutput.trim().split(/\r?\n/).pop());
        send('update:converter-progress',{done:1,total:3});
        if (prepared.prepared) {
          await converterUpdate.stopConverter(deps.backendPort);
          await converterUpdate.transaction('Activate',deps.converterDir);
        }
        send('update:converter-progress',{done:3,total:3});
      }
      if (checked.appAvailable) {
        const updater=getAutoUpdater();
        setImmediate(()=>updater.quitAndInstall(false,true));
      } else {
        setImmediate(()=>{app.relaunch();app.quit();});
      }
      return {ok:true,restarting:true};
    } catch(error) {
      try {
        const pending=await converterUpdate.state(deps.converterDir);
        if (pending && ['prepared','preparing'].includes(pending.phase)) {
          await converterUpdate.transaction('Recover',deps.converterDir);
        }
      } catch(recoveryError) { console.error('[updater] recovery',recoveryError); }
      return {ok:false,error:String(error.message || error)};
    } finally { busy=false; }
  });
}
function shutdownUpdater() {
  if (feedServer) {
    try { feedServer.closeAllConnections(); } catch (_) { /* Older Node. */ }
    feedServer.close();
    feedServer=null;feedRoot=null;
  }
}
module.exports={initUpdater,shutdownUpdater,planConverterSync,startFeedServer};
