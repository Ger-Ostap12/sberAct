// Тесты планировщика converter-sync (electron-app/updater.js).
//
// Зачем отдельный раннер: updater.js живёт в main-процессе Electron, а
// react-scripts test (CRA) видит только electron-app/src — до него он не
// достаёт. Здесь голый Node + подмена require('electron'), чтобы модуль
// вообще импортировался вне Electron.
//
// Запуск: node scripts/tests/converter-sync.test.js

const assert = require('assert');
const path = require('path');
const Module = require('module');

// --- Подмена electron: updater.js требует его на верхнем уровне ---
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'electron') {
    return { app: {}, ipcMain: { handle: () => {} }, dialog: {} };
  }
  return originalLoad.apply(this, arguments);
};

const { planConverterSync } = require(
  path.join(__dirname, '..', '..', 'electron-app', 'updater.js')
);

Module._load = originalLoad;

const CONVERTER_DIR = path.join('C:', 'app', 'resources', 'converter');

function manifest(files) {
  return { version: 'test', files };
}

// Файлы «есть на диске» описываем картой path -> size.
function statFrom(sizes) {
  return (fullPath) => {
    const rel = fullPath.substring(CONVERTER_DIR.length + 1).replace(/\\/g, '/');
    if (!(rel in sizes)) return null;
    return { size: sizes[rel] };
  };
}

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

// --- Главный регресс: манифест целый, файлы не доехали -----------------------
// Ровно этот случай пришёл с флешки: converter-manifest.json скопировался
// (9 МБ), а 14 521 файл на 5.36 ГБ — нет. Старая логика доверяла манифесту и
// показывала «обновлений нет», оставляя установку нерабочей.
test('манифесты совпадают, но файлов нет на диске -> копируем', () => {
  const files = [
    { path: 'pyruntime/python.exe', sha256: 'aaa', size: 100 },
    { path: 'docling_dev/api.py', sha256: 'bbb', size: 200 },
    { path: 'main.py', sha256: 'ccc', size: 300 }
  ];
  const plan = planConverterSync(
    manifest(files),
    manifest(files),           // установленный манифест идентичен
    CONVERTER_DIR,
    statFrom({ 'main.py': 300 }) // а физически лежит только main.py
  );
  assert.strictEqual(plan.toCopy.length, 2, 'должны попасть отсутствующие файлы');
  assert.deepStrictEqual(
    plan.toCopy.map((f) => f.path).sort(),
    ['docling_dev/api.py', 'pyruntime/python.exe']
  );
  assert.strictEqual(plan.bytes, 300);
  assert.strictEqual(plan.toDelete.length, 0);
});

test('всё на месте -> копировать нечего', () => {
  const files = [
    { path: 'main.py', sha256: 'ccc', size: 300 },
    { path: 'pyruntime/python.exe', sha256: 'aaa', size: 100 }
  ];
  const plan = planConverterSync(
    manifest(files),
    manifest(files),
    CONVERTER_DIR,
    statFrom({ 'main.py': 300, 'pyruntime/python.exe': 100 })
  );
  assert.strictEqual(plan.toCopy.length, 0);
  assert.strictEqual(plan.toDelete.length, 0);
  assert.strictEqual(plan.bytes, 0);
});

test('файл обрезан (размер не тот) -> перекопируем', () => {
  const files = [{ path: 'models/model.gguf', sha256: 'aaa', size: 1000 }];
  const plan = planConverterSync(
    manifest(files),
    manifest(files),
    CONVERTER_DIR,
    statFrom({ 'models/model.gguf': 512 }) // копирование оборвалось на середине
  );
  assert.strictEqual(plan.toCopy.length, 1);
  assert.strictEqual(plan.bytes, 1000);
});

test('sha разошлись -> копируем без обращения к диску', () => {
  const flash = [{ path: 'docling_dev/api.py', sha256: 'new', size: 200 }];
  const installed = [{ path: 'docling_dev/api.py', sha256: 'old', size: 150 }];
  let statCalls = 0;
  const plan = planConverterSync(
    manifest(flash),
    manifest(installed),
    CONVERTER_DIR,
    () => { statCalls += 1; return { size: 200 }; }
  );
  assert.strictEqual(plan.toCopy.length, 1);
  assert.strictEqual(statCalls, 0, 'при расхождении sha диск не нужен');
});

test('нет установленного манифеста -> сверка по диску (старые установки)', () => {
  const files = [
    { path: 'main.py', sha256: 'ccc', size: 300 },
    { path: 'vendor/tesseract/tesseract.exe', sha256: 'ddd', size: 400 }
  ];
  const plan = planConverterSync(
    manifest(files),
    null,
    CONVERTER_DIR,
    statFrom({ 'main.py': 300 })
  );
  assert.deepStrictEqual(plan.toCopy.map((f) => f.path), ['vendor/tesseract/tesseract.exe']);
});

test('файл исчез из нового манифеста -> под удаление', () => {
  const flash = [{ path: 'main.py', sha256: 'ccc', size: 300 }];
  const installed = [
    { path: 'main.py', sha256: 'ccc', size: 300 },
    { path: 'models/gemma-3-4b-it-Q4_K_M.gguf', sha256: 'eee', size: 999 }
  ];
  const plan = planConverterSync(
    manifest(flash),
    manifest(installed),
    CONVERTER_DIR,
    statFrom({ 'main.py': 300 })
  );
  assert.strictEqual(plan.toCopy.length, 0);
  assert.deepStrictEqual(plan.toDelete, ['models/gemma-3-4b-it-Q4_K_M.gguf']);
});

test('size отсутствует в манифесте -> хватает факта существования', () => {
  const files = [{ path: 'main.py', sha256: 'ccc' }];
  const plan = planConverterSync(
    manifest(files),
    manifest(files),
    CONVERTER_DIR,
    statFrom({ 'main.py': 12345 })
  );
  assert.strictEqual(plan.toCopy.length, 0);
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log('  ok   ' + name);
  } catch (e) {
    failed += 1;
    console.log('  FAIL ' + name);
    console.log('       ' + e.message);
  }
}
console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed === 0 ? 0 : 1);
