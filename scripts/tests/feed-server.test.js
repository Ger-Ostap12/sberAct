// Тесты локального feed-сервера обновления (electron-app/updater.js).
//
// Проверяются два фикса из аудита §S.1.2:
//   №33 — защита от выхода за пределы корня. Прежняя проверка startsWith
//         пропускала соседа по имени: при корне C:\upd путь C:\update\...
//         считался «внутри».
//   №30 — обработчик error на файловом стриме. Источник обновления съёмный,
//         чтение может оборваться на любом байте, а неперехваченный error =
//         uncaughtException = падение main-процесса без окна и сообщения.
//
// Зачем отдельный раннер: updater.js живёт в main-процессе Electron, а
// react-scripts test (CRA) видит только electron-app/src.
//
// Запуск: node scripts/tests/feed-server.test.js

const assert = require('assert');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const Module = require('module');

// --- Подмена electron: updater.js требует его на верхнем уровне ---
const originalLoad = Module._load;
Module._load = function (request) {
  if (request === 'electron') {
    return { app: {}, ipcMain: { handle: () => {} }, dialog: {} };
  }
  return originalLoad.apply(this, arguments);
};

const { startFeedServer } = require(
  path.join(__dirname, '..', '..', 'electron-app', 'updater.js')
);

Module._load = originalLoad;

let passed = 0;
let failed = 0;

function ok(name) {
  passed += 1;
  console.log('  ok   ' + name);
}

function fail(name, err) {
  failed += 1;
  console.log('  FAIL ' + name + '\n       ' + (err && err.message ? err.message : err));
}

/** GET по пути, отдаёт { status, body }. Путь НЕ нормализуем — в этом весь смысл. */
function get(port, rawPath, extraHeaders) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: '127.0.0.1', port, path: rawPath, method: 'GET', headers: extraHeaders || {} },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks) }));
        res.on('error', reject);
      }
    );
    req.on('error', reject);
    req.end();
  });
}

async function main() {
  // Корень «C:\...\feedroot» и сосед «C:\...\feedrootX» — тот самый случай,
  // на котором ломалась префиксная проверка.
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'sberact-feed-'));
  const root = path.join(base, 'feedroot');
  const sibling = base + path.sep + 'feedrootX';
  fs.mkdirSync(root, { recursive: true });
  fs.mkdirSync(sibling, { recursive: true });

  fs.writeFileSync(path.join(root, 'update.bin'), Buffer.alloc(4096, 7));
  fs.writeFileSync(path.join(sibling, 'secret.txt'), 'нельзя отдавать');

  const { server, port } = await startFeedServer(root);

  try {
    // --- №33: обычный файл внутри корня отдаётся ---
    try {
      const res = await get(port, '/update.bin');
      assert.strictEqual(res.status, 200);
      assert.strictEqual(res.body.length, 4096);
      ok('файл внутри корня отдаётся целиком');
    } catch (e) { fail('файл внутри корня отдаётся целиком', e); }

    // --- №33: сосед по имени НЕ отдаётся ---
    // ВЕКТОР, установленный замером. Точки в пути (в т.ч. %2e) схлопывает сам
    // конструктор URL — до проверки они не доходят. А вот %2f он НЕ декодирует:
    // разделитель появляется только на decodeURIComponent, то есть УЖЕ ПОСЛЕ
    // нормализации. path.join уводит в соседнюю папку, чьё имя начинается с
    // имени корня, и прежняя проверка startsWith считала её «внутри».
    try {
      const res = await get(port, '/..%2ffeedrootX/secret.txt');
      assert.strictEqual(res.status, 403, `ожидали 403, получили ${res.status}`);
      ok('сосед по имени через %2f -> 403');
    } catch (e) { fail('сосед по имени через %2f -> 403', e); }

    // --- №33: то же самое с полностью закодированным сегментом ---
    try {
      const res = await get(port, '/%2e%2e%2ffeedrootX/secret.txt');
      assert.strictEqual(res.status, 403, `ожидали 403, получили ${res.status}`);
      ok('полностью закодированный выход -> 403');
    } catch (e) { fail('полностью закодированный выход -> 403', e); }

    // --- голый ../ безвреден (схлопывает URL), но чужого отдавать не должен ---
    try {
      const res = await get(port, '/../feedrootX/secret.txt');
      assert.ok(res.status === 403 || res.status === 404,
        `ожидали 403/404, получили ${res.status}`);
      ok('голый ../ чужого не отдаёт');
    } catch (e) { fail('голый ../ чужого не отдаёт', e); }

    // --- Range-запрос работает (electron-updater качает кусками) ---
    try {
      const res = await get(port, '/update.bin', { Range: 'bytes=0-1023' });
      assert.strictEqual(res.status, 206);
      assert.strictEqual(res.body.length, 1024);
      ok('Range-запрос отдаёт запрошенный кусок');
    } catch (e) { fail('Range-запрос отдаёт запрошенный кусок', e); }

    // --- Несуществующий файл -> 404, а не падение ---
    try {
      const res = await get(port, '/no-such-file.bin');
      assert.strictEqual(res.status, 404);
      ok('несуществующий файл -> 404');
    } catch (e) { fail('несуществующий файл -> 404', e); }

    // --- №30: сбой чтения НЕ роняет процесс ---
    // Подменяем createReadStream на стрим, который сразу эмитит error —
    // это имитация выдернутой флешки. Без обработчика 'error' здесь был бы
    // uncaughtException и смерть main-процесса.
    try {
      const { Readable } = require('stream');
      const realCreate = fs.createReadStream;
      fs.createReadStream = function () {
        const s = new Readable({ read() {} });
        setImmediate(() => s.emit('error', Object.assign(new Error('EIO'), { code: 'EIO' })));
        return s;
      };

      let crashed = null;
      const onUncaught = (e) => { crashed = e; };
      process.on('uncaughtException', onUncaught);

      try {
        await get(port, '/update.bin').catch(() => ({ status: 'оборвано' }));
        await new Promise((r) => setTimeout(r, 150)); // даём error всплыть
      } finally {
        process.removeListener('uncaughtException', onUncaught);
        fs.createReadStream = realCreate;
      }

      assert.strictEqual(crashed, null, 'сбой чтения дошёл до uncaughtException');
      ok('обрыв чтения носителя не роняет процесс');
    } catch (e) { fail('обрыв чтения носителя не роняет процесс', e); }

    // --- сервер жив после всего этого ---
    try {
      const res = await get(port, '/update.bin');
      assert.strictEqual(res.status, 200);
      ok('сервер продолжает обслуживать после сбоя');
    } catch (e) { fail('сервер продолжает обслуживать после сбоя', e); }
  } finally {
    try { server.closeAllConnections(); } catch (_e) { /* Node < 18.2 */ }
    server.close();
    fs.rmSync(base, { recursive: true, force: true });
  }

  console.log('\n' + passed + '/' + (passed + failed) + ' passed');
  if (failed > 0) process.exit(1);
}

main().catch((e) => {
  console.error('раннер упал:', e);
  process.exit(1);
});
