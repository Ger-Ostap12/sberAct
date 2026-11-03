// Общий журнал Electron и вывода сервисов; не зависит от окна приложения.
const { createServiceLog } = require('./serviceLog');
const crypto = require('crypto');
const fs = require('fs');
const { StringDecoder } = require('string_decoder');

function redact(value) {
  let text = String(value);
  text = text.split('\n').map(line =>
    /requestData\s*:|(?:debtorName|applicantName|rawText|passportNumber|edited_text)["']?\s*[:=]|Данные для замены|Очищенные данные|Полученные данные/i.test(line)
      ? '[содержимое заявления скрыто]' : line).join('\n');
  text = text.replace(/([\\/]Users[\\/])[^\\/\s]+/gi, '$1[пользователь]')
    .replace(/\b\d{10,19}\b/g, '[реквизит скрыт]')
    .replace(/(^|[^А-ЯЁа-яё])[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?=[^А-ЯЁа-яё]|$)/g, '$1[ФИО скрыто]');
  return text.length > 12000 ? text.slice(0, 2000) + '\n[часть журнала сокращена]\n' + text.slice(-9000) : text;
}
function sanitize(value, key = '') {
  if (typeof value === 'string') return key === 'incidentId' || key === 'time' ? value : redact(value);
  if (Array.isArray(value)) return value.slice(-500).map(item => sanitize(item));
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.entries(value).map(([name, item]) => [name, sanitize(item, name)]));
  return value;
}
function fileFailure(error, fallback) {
  const errors = {
    EACCES: ['ACCESS_DENIED', 'Нет доступа к файлу или папке.', 'Проверьте права доступа или выберите другую папку.'],
    EPERM: ['ACCESS_DENIED', 'Система запретила доступ к файлу.', 'Закройте документ в Word и проверьте права доступа.'],
    EBUSY: ['FILE_LOCKED', 'Файл занят другой программой.', 'Закройте файл и повторите сохранение.'],
    ENOENT: ['FILE_NOT_FOUND', 'Не найден необходимый файл или папка.', 'Проверьте выбранный путь.'],
    ENOSPC: ['DISK_FULL', 'Недостаточно свободного места на диске.', 'Освободите место или выберите другой диск.'],
    REPORT_TOO_LARGE: ['REPORT_TOO_LARGE', 'Диагностический отчёт слишком большой.', 'Скопируйте отдельную ошибку из журнала.'],
  };
  const [code, message, hint] = errors[error && error.code] ||
    ['UNEXPECTED_ERROR', fallback, 'Откройте «Подробности» и сохраните отчёт.'];
  return { code, message, hint };
}
function reportedFailure(error, fallback, record) {
  if (/^HTTP(?: error!| \d{3})/.test(error.message || ''))
    return { success: false, error: error.message };
  const failure = fileFailure(error, fallback || 'Не удалось выполнить операцию.');
  const entry = record({ component: 'electron', level: 'error',
    message: error.stack || String(error), code: failure.code, operation: fallback });
  return { success: false, error: failure.message, ...failure, incidentId: entry.incidentId };
}
function createDiagnostics(dir, publish = () => {}) {
  const log = createServiceLog('diagnostics', dir);
  const events = [];
  // Последний сбой доступен после перезапуска, даже если прежнее окно завершилось аварийно.
  for (const file of [log.file.replace(/\.log$/, '.1.log'), log.file]) {
    let fd;
    try {
      fd = fs.openSync(file, 'r');
      const size = fs.fstatSync(fd).size;
      const length = Math.min(size, 256 * 1024);
      const bytes = Buffer.alloc(length);
      fs.readSync(fd, bytes, 0, length, size - length);
      for (const line of bytes.toString('utf8').split('\n')) {
        try {
          const entry = JSON.parse(line);
          if (typeof entry.message === 'string' && typeof entry.time === 'string') events.push(sanitize(entry));
        } catch (_) { /* Неполная первая или последняя строка. */ }
      }
    } catch (_) { /* Первый запуск или журнал недоступен. */ }
    finally { if (fd !== undefined) fs.closeSync(fd); }
  }
  if (events.length > 500) events.splice(0, events.length - 500);
  const buffers = new Map();
  const decoders = new Map();
  function record(input) {
    const event = sanitize({
      time: input.time || new Date().toISOString(),
      component: String(input.component || 'electron').slice(0, 50),
      level: ['info', 'warning', 'error'].includes(input.level) ? input.level : 'error',
      message: String(input.message || ''),
      operation: String(input.operation || '').slice(0, 200),
      hint: String(input.hint || '').slice(0, 1000),
      code: String(input.code || '').slice(0, 80),
      incidentId: String(input.incidentId || crypto.randomUUID()).slice(0, 64),
    });
    if (events.some(e => e.time === event.time && e.message === event.message && e.incidentId === event.incidentId)) return event;
    events.push(event);
    if (events.length > 500) events.shift();
    log.write(JSON.stringify(event) + '\n');
    try { publish(event); } catch (_) { /* Закрытое окно не мешает работе сервиса. */ }
    return event;
  }
  function ingest(component, chunk) {
    if (!decoders.has(component)) decoders.set(component, new StringDecoder('utf8'));
    const decoded = Buffer.isBuffer(chunk) ? decoders.get(component).write(chunk) : String(chunk);
    const combined = (buffers.get(component) || '') + decoded;
    const lines = combined.split(/\r?\n/);
    let pending = lines.pop() || '';
    if (pending.length > 32768) { lines.push(pending.slice(-32768)); pending = ''; }
    buffers.set(component, pending);
    for (const line of lines) {
      if (!line.trim()) continue;
      const start = line.indexOf('SBERACT_DIAGNOSTIC ');
      if (start >= 0) {
        try { record(JSON.parse(line.slice(start + 19))); continue; } catch (_) { /* Обрыв диагностической строки. */ }
      }
      record({ component, level: /error|exception|traceback|failed|ошиб/i.test(line) ? 'error' : 'info', message: line });
    }
  }
  function flush(component) {
    const pending = (buffers.get(component) || '') + (decoders.get(component)?.end() || '');
    decoders.delete(component);
    if (pending) { buffers.delete(component); ingest(component, pending + '\n'); }
  }
  return { record, ingest, flush, snapshot: () => ({ events: [...events] }) };
}
module.exports = { createDiagnostics, redact, sanitize, fileFailure, reportedFailure };
