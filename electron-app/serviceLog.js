// Файловый лог сервисов (бэкенд и конвертер).
//
// Их stdout уходил в console.log Electron, которого на машине пользователя не
// достать. Если конвертер не поднялся вовсе, задачи ещё нет — значит нет и
// job.log конвертера, и причина сбоя не узнаётся никак (именно так закончилась
// диагностика на слабом ПК 18.10).
//
// Запись синхронная. Поток выглядел уместнее, но его буфер ломал и ротацию
// (Windows не переименовывает открытый файл), и сам смысл лога: при жёстком
// выходе терялись последние строки — ровно те, что объясняют сбой. Объём тут
// небольшой: сервисы печатают строку на стадию, не поток данных.
//
// Electron здесь не используется: папку передаёт вызывающий, поэтому модуль
// проверяется обычным node без запуска приложения.
const fs = require('fs');
const path = require('path');

const MAX_BYTES = 2 * 1024 * 1024;

/**
 * Лог одного сервиса: `<dir>/<name>.log`, при переполнении — ротация в
 * `<name>.1.log`. Любая ошибка файловой системы гасится: лог не может быть
 * причиной падения приложения.
 */
function createServiceLog(name, dir, maxBytes = MAX_BYTES) {
  const file = path.join(dir, `${name}.log`);
  const previous = path.join(dir, `${name}.1.log`);
  let size = 0;
  let ready = false;

  try {
    fs.mkdirSync(dir, { recursive: true });
    size = fs.existsSync(file) ? fs.statSync(file).size : 0;
    ready = true;
  } catch (_) {
    ready = false; // нет прав или пути — дальше пишем в пустоту, но не падаем
  }

  const rotate = () => {
    try {
      fs.rmSync(previous, { force: true });
      fs.renameSync(file, previous);
      size = 0;
    } catch (_) {
      /* не вышло — продолжаем в тот же файл, он просто подрастёт */
    }
  };

  const write = (text) => {
    if (!ready) return;
    const chunk = String(text);
    try {
      fs.appendFileSync(file, chunk);
      size += Buffer.byteLength(chunk);
      if (size >= maxBytes) rotate();
    } catch (_) {
      /* лог не должен ломать работу */
    }
  };

  return {
    file,
    /** Поток процесса как есть. */
    write,
    /** Событие с отметкой времени: запуск, код выхода, таймаут готовности. */
    line: (text) => write(`[${new Date().toISOString()}] ${text}\n`),
  };
}

// Readable.setEncoding keeps incomplete UTF-8 characters between data chunks.
function captureUtf8Output(stream, onText) {
  stream.setEncoding('utf8');
  stream.on('data', onText);
}

module.exports = { createServiceLog, captureUtf8Output, MAX_BYTES };
