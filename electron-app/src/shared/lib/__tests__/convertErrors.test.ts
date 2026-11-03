import { backendError, OFFLINE_TEXT, parseBackendError } from '../convertErrors';

// Формы входа сняты с живого конвертера (проверка 29.10): структурный detail
// у отказов конвертации, строковый detail у 404, отсутствие detail на 500.

describe('parseBackendError — структурный detail из текста ошибки preload', () => {
  const body = JSON.stringify({
    detail: {
      code: 'NOT_A_PDF',
      message: 'Файл не является PDF-документом.',
      hint: 'Проверьте, что выбран именно PDF.',
      detail: "нет заголовка %PDF: b'this is '",
    },
  });

  it('достаёт message, hint, code и техническую подробность', () => {
    const f = parseBackendError(new Error(`HTTP 400: ${body}`));
    expect(f.message).toBe('Файл не является PDF-документом.');
    expect(f.hint).toBe('Проверьте, что выбран именно PDF.');
    expect(f.code).toBe('NOT_A_PDF');
    expect(f.raw).toBe("нет заголовка %PDF: b'this is '");
    expect(f.status).toBe(400);
    expect(f.kind).toBe('http');
  });

  it('не отдаёт «[object Object]» — именно от этого всё и затевалось', () => {
    const f = parseBackendError(new Error(`HTTP 400: ${body}`));
    expect(f.message).not.toContain('[object Object]');
    expect(f.message).not.toMatch(/^HTTP /);
  });
});

describe('parseBackendError — остальные формы ответа', () => {
  it('строковый detail (404 отмены несуществующей задачи)', () => {
    const f = parseBackendError(new Error('HTTP 404: {"detail": "Задача не найдена."}'));
    expect(f.message).toBe('Задача не найдена.');
    expect(f.kind).toBe('notfound');
    expect(f.status).toBe(404);
  });

  it('410: результат уже удалён', () => {
    const f = parseBackendError(new Error('HTTP 410: {"detail": "Файл удалён."}'));
    expect(f.kind).toBe('gone');
  });

  it('500 без detail — подпись запроса плюс код, тело уходит в raw', () => {
    const f = parseBackendError(new Error('HTTP 500: <html>Internal Error</html>'), 'Конвертация не удалась');
    expect(f.message).toContain('Конвертация не удалась');
    expect(f.message).not.toContain('500');
    expect(f.status).toBe(500);
    expect(f.kind).toBe('server');
    expect(f.raw).toContain('Internal Error');
  });

  it('отказ с пустым телом', () => {
    const f = parseBackendError(new Error('HTTP 413: '), 'Файл не принят');
    expect(f.message).toContain('Файл слишком большой');
    expect(f.status).toBe(413);
    expect(f.kind).toBe('http');
  });

  it('короткий текст вместо JSON — это объяснение бэкенда, его не теряем', () => {
    // Регрессия: прокси отвечает 502 с текстом «Конвертер не запущен», и это
    // единственный след причины.
    const f = parseBackendError(new Error('HTTP 502: Конвертер не запущен'), 'Запрос /banks не удался');
    expect(f.message).not.toContain('502');
    expect(f.status).toBe(502);
    expect(f.message).toContain('Конвертер не запущен');
  });

  it('HTML от прокси наружу не показывается', () => {
    const f = parseBackendError(new Error('HTTP 500: <html><body>nginx</body></html>'), 'Запрос не удался');
    expect(f.message).not.toContain('<html>');
    expect(f.hint).toContain('Подробности');
  });

  it('битый JSON в теле не ломает разбор', () => {
    const f = parseBackendError(new Error('HTTP 400: {не json'), 'Запрос не удался');
    expect(f.message).toBe('Запрос не удался');
    expect(f.status).toBe(400);
  });
});

describe('parseBackendError — сетевые сбои', () => {
  it.each([
    ['Failed to fetch', 'браузерный fetch'],
    ['All backend hosts failed', 'preload перебрал хосты'],
    ['Backend недоступен', 'webApi'],
    ['NetworkError when attempting to fetch resource.', 'firefox'],
    ['net::ERR_CONNECTION_REFUSED', 'chromium'],
  ])('«%s» заменяется на внятный текст (%s)', (message) => {
    const f = parseBackendError(new TypeError(message));
    expect(f.message).toBe(OFFLINE_TEXT);
    expect(f.kind).toBe('offline');
    expect(f.raw).toBe(message);
  });
});

describe('parseBackendError — вход не от сети', () => {
  it('обычная ошибка проходит как есть', () => {
    const f = parseBackendError(new Error('Конвертер не установлен'));
    expect(f.message).toBe('Конвертер не установлен');
    expect(f.kind).toBe('unknown');
  });

  it('строка (ошибка из IPC) проходит как есть', () => {
    const f = parseBackendError('Конвертер недоступен');
    expect(f.message).toBe('Конвертер недоступен');
  });

  it('undefined и пустая строка дают fallback', () => {
    expect(parseBackendError(undefined, 'Ошибка конвертации').message).toBe('Ошибка конвертации');
    expect(parseBackendError('', 'Ошибка конвертации').message).toBe('Ошибка конвертации');
  });

  it('уже разобранный отказ не разбирается второй раз', () => {
    const once = backendError(400, JSON.stringify({ detail: { code: 'PDF_ENCRYPTED', message: 'PDF защищён паролем.', hint: 'Снимите пароль.' } }));
    const twice = parseBackendError(once);
    expect(twice.message).toBe('PDF защищён паролем.');
    expect(twice.hint).toBe('Снимите пароль.');
    expect(twice.code).toBe('PDF_ENCRYPTED');
  });
});

describe('backendError — сторона, которая держит ответ в руках', () => {
  it('Error.message — текст для пользователя, поля разобраны', () => {
    const e = backendError(
      400,
      JSON.stringify({ detail: { code: 'PDF_CORRUPTED', message: 'PDF повреждён.', hint: 'Откройте файл в Acrobat.' } })
    ) as Error & { code?: string; hint?: string };
    expect(e).toBeInstanceOf(Error);
    expect(e.message).toBe('PDF повреждён.');
    expect(e.code).toBe('PDF_CORRUPTED');
    expect(e.hint).toBe('Откройте файл в Acrobat.');
  });
});

describe('единый формат диагностики', () => {
  it('сохраняет номер сбоя и подсказку сервера', () => {
    const failure = parseBackendError(new Error('HTTP 422: ' + JSON.stringify({ detail: {
      code: 'TEMPLATES_UNAVAILABLE', message: 'Нет шаблона определения о принятии.',
      hint: 'Добавьте шаблон.', incidentId: 'case-12345678',
    } })));
    expect(failure.message).toBe('Нет шаблона определения о принятии.');
    expect(failure.hint).toBe('Добавьте шаблон.');
    expect(failure.incidentId).toBe('case-12345678');
  });
  it('старый формат IPC не показывает HTTP пользователю', () => {
    const failure = parseBackendError(new Error('HTTP error! status: 500'));
    expect(failure.message).not.toContain('HTTP');
    expect(failure.status).toBe(500);
  });
  it('не выдумывает причину неизвестного сбоя', () => {
    const failure = parseBackendError(new Error('TypeError: internal secret'), 'Не удалось сохранить документ.');
    expect(failure.message).toBe('Не удалось сохранить документ.');
    expect(failure.raw).toContain('internal secret');
  });
});


it('технический текст HTTP из preload остаётся в диагностике, а не в сообщении', () => {
  const error = parseBackendError(new Error('HTTP 500: {"detail":"Internal Server Error"}'), 'Не удалось сформировать документы.');
  expect(error.message).toBe('Не удалось сформировать документы.');
  expect(error.raw).toBe('Internal Server Error');
});
