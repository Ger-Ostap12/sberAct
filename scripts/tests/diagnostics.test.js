const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const { EventEmitter } = require('events');
const { createDiagnostics, redact, sanitize, reportedFailure } = require('../../electron-app/diagnostics');

function removeFixture(dir) {
  const resolved = path.resolve(dir);
  assert(resolved.startsWith(path.resolve(os.tmpdir()) + path.sep));
  assert(path.basename(resolved).startsWith('sber-diag-'));
  fs.rmSync(resolved, { recursive: true, force: true });
}

test('journal preserves backend incident id across split UTF-8 and JSON chunks', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sber-diag-'));
  try {
    const published = [];
    const journal = createDiagnostics(dir, event => published.push(event));
    const event = { time: '2026-11-03T00:00:00Z', component: 'converter', level: 'error',
      incidentId: 'case-123456789012', code: 'FAILED', message: 'Не удалось загрузить модуль' };
    const bytes = Buffer.from('SBERACT_DIAGNOSTIC ' + JSON.stringify(event) + '\n');
    for (let n = 0; n < bytes.length; n++) journal.ingest('backend', bytes.subarray(n, n + 1));
    assert.equal(published.length, 1);
    assert.equal(published[0].incidentId, event.incidentId);
    assert.equal(published[0].message, event.message);
    assert(!published[0].message.includes('\ufffd'));
  } finally {
    removeFixture(dir);
  }
});

test('journal bounds memory, redacts private fields and keeps partial final output', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sber-diag-'));
  try {
    const journal = createDiagnostics(dir);
    for (let n = 0; n < 520; n++) journal.record({ message: 'Ошибка ' + n, component: 'test' });
    assert.equal(journal.snapshot().events.length, 500);
    journal.ingest('converter', 'last error');
    journal.flush('converter');
    assert.equal(journal.snapshot().events.at(-1).message, 'last error');
    assert(!redact('ИНН 123456789012; Ароян Ваче Рушани').includes('Ароян'));
    assert(!redact('ИНН 123456789012').includes('123456789012'));
    assert.equal(redact('requestData: full document'), '[содержимое заявления скрыто]');
    assert.equal(sanitize({ incidentId: '123456789012', message: 'ИНН 123456789012' }).incidentId, '123456789012');
  } finally {
    removeFixture(dir);
  }
});

function preload(fetch) {
  const exposed = {};
  const ipc = new EventEmitter();
  ipc.invoke = async () => ({ events: [] });
  const context = {
    require: name => name === 'electron' ? { contextBridge: {
      exposeInMainWorld: (name, value) => { exposed[name] = value; },
    }, ipcRenderer: ipc } : require(name),
    console: { log() {}, warn() {}, error() {} },
    fetch, Blob, FormData, Uint8Array, setTimeout, clearTimeout,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../electron-app/preload.js'), 'utf8'), context);
  return { api: exposed.electronAPI, ipc };
}

test('actual preload retains server reason and never repeats failed generation', async () => {
  let calls = 0;
  const { api } = preload(async () => {
    calls++;
    return { ok: false, status: 422, text: async () => JSON.stringify({
      detail: { message: 'Не найден шаблон определения.', code: 'TEMPLATES_UNAVAILABLE', incidentId: 'request-12345' },
    }) };
  });
  await assert.rejects(api.generateDocument({ template_type: 'x', data: { a: 1 } }),
    error => error.message.includes('Не найден шаблон определения.') && error.message.includes('request-12345'));
  assert.equal(calls, 1);
});

test('actual preload subscribes and unsubscribes from service diagnostic stream', async () => {
  const { api, ipc } = preload(async () => ({ ok: true }));
  const events = [];
  const stop = api.onDiagnostic(event => events.push(event));
  ipc.emit('diagnostic:event', {}, { message: 'Модуль не найден' });
  stop();
  ipc.emit('diagnostic:event', {}, { message: 'ignored' });
  await Promise.resolve();
  assert.equal(events.length, 1);
});

test('file failures distinguish full disk and access denied and correlate with native stack', () => {
  const entries = [];
  const record = event => { entries.push(event); return { incidentId: 'disk-12345' }; };
  const full = reportedFailure(Object.assign(new Error('native write failed'), { code: 'ENOSPC' }),
    'Не удалось сохранить документ.', record);
  assert.equal(full.code, 'DISK_FULL');
  assert.equal(full.incidentId, 'disk-12345');
  assert(entries[0].message.includes('native write failed'));
  const denied = reportedFailure(Object.assign(new Error('native denied'), { code: 'EACCES' }), '', record);
  assert.equal(denied.code, 'ACCESS_DENIED');
});
test('IPC reporting preserves HTTP body for frontend parsing instead of losing server reason', () => {
  const text = 'HTTP 422: {"detail":{"message":"Не найден шаблон","incidentId":"server-12345"}}';
  const result = reportedFailure(new Error(text), 'Не удалось выполнить операцию.', () => { throw new Error('not a local file failure'); });
  assert.equal(result.error, text);
});

test('last diagnostic cause remains available after process restart', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sber-diag-'));
  try {
    createDiagnostics(dir).record({ time: '2026-11-03T01:00:00Z', component: 'converter',
      level: 'error', message: 'ModuleNotFoundError: docling', incidentId: 'previous-session-12345' });
    const restored = createDiagnostics(dir).snapshot().events;
    assert(restored.some(event => event.incidentId === 'previous-session-12345' && event.message.includes('docling')));
  } finally { removeFixture(dir); }
});

test('privacy filtering keeps technical field names in exception causes', () => {
  const trace = "Traceback\nДанные для замены: debtorName: Иванов Иван Иванович\nKeyError: 'debtorName'";
  const safe = redact(trace);
  assert(!safe.includes('Иванов'));
  assert(safe.includes("KeyError: 'debtorName'"));
});
