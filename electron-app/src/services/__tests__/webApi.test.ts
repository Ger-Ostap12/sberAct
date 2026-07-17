import { webApi, resetLiveBase } from '../webApi';

// Мокаем сеть и браузерные API скачивания.
const okJson = (body: unknown) =>
  ({ ok: true, status: 200, json: async () => body, text: async () => '' } as unknown as Response);
const okBlob = (headers: Record<string, string> = {}) =>
  ({
    ok: true,
    status: 200,
    blob: async () => new Blob(['data']),
    headers: { get: (k: string) => headers[k] || null },
  } as unknown as Response);

beforeEach(() => {
  (global as any).URL.createObjectURL = jest.fn(() => 'blob:mock');
  (global as any).URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  resetLiveBase(); // выбранный хост живёт в модуле — иначе тесты цепляются друг за друга
});
afterEach(() => jest.restoreAllMocks());

describe('webApi.analyzeDocument', () => {
  it('POST /analyze-document с FormData из File', async () => {
    const fetchMock = jest.fn(async () => okJson({ success: true, data: { x: 1 } }));
    (global as any).fetch = fetchMock;

    const res = await webApi.analyzeDocument(new File(['x'], 'zayavlenie.docx'));

    expect(res).toEqual({ success: true, data: { x: 1 } });
    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toContain('/analyze-document');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
  });

  it('строковый путь в браузере не поддержан', async () => {
    (global as any).fetch = jest.fn();
    await expect(webApi.analyzeDocument('C:/f.docx')).rejects.toThrow(/браузере/);
  });
});

describe('webApi.getBanks', () => {
  it('GET /banks возвращает список банков', async () => {
    const banks = [{ display: 'Сбербанк', inn: '1', ogrn: '2', address: 'a', aliases: ['сбербанк'] }];
    const fetchMock = jest.fn(async () => okJson(banks));
    (global as any).fetch = fetchMock;

    const res = await webApi.getBanks();

    expect(res).toEqual(banks);
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(String(url)).toContain('/banks');
  });
});

describe('webApi.generateDocument', () => {
  it('POST /generate-document с JSON', async () => {
    const fetchMock = jest.fn(async () => okJson({ success: true, document_id: 'd1' }));
    (global as any).fetch = fetchMock;

    const res = await webApi.generateDocument({ template_type: 't', data: {} });

    expect(res).toEqual({ success: true, document_id: 'd1' });
    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toContain('/generate-document');
    expect(opts.method).toBe('POST');
  });
});

describe('webApi.downloadAllDocuments', () => {
  it('скачивает ZIP как blob и возвращает success', async () => {
    (global as any).fetch = jest.fn(async () => okBlob());
    const res = await webApi.downloadAllDocuments({ document_ids: 'a,b', download_path: '' });
    expect(res.success).toBe(true);
    expect((global as any).URL.createObjectURL).toHaveBeenCalled();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
  });

  it('ошибка backend → success:false', async () => {
    (global as any).fetch = jest.fn(async () => ({
      ok: false,
      status: 500,
      text: async () => 'boom',
    }) as unknown as Response);
    const res = await webApi.downloadAllDocuments({ document_ids: 'a', download_path: '' });
    expect(res.success).toBe(false);
  });
});

describe('webApi — недоступные в браузере операции', () => {
  it('selectFile и getExtractedData возвращают null', async () => {
    await expect(webApi.selectFile()).resolves.toBeNull();
    await expect(webApi.getExtractedData()).resolves.toBeNull();
  });
});

describe('fetchBackend — выбор хоста', () => {
  const FIRST = 'http://127.0.0.1:8000';
  const SECOND = 'http://localhost:8000';
  const netFail = () => Promise.reject(new TypeError('Failed to fetch'));

  it('HTTP-ошибка живого хоста НЕ уводит перебор дальше', async () => {
    // Регрессия: 502 от 127.0.0.1 гнал запрос на localhost и wsl.localhost,
    // и наружу летела ошибка от последнего — настоящая причина терялась.
    const fetchMock = jest.fn(
      async () => ({ ok: false, status: 502, text: async () => 'Конвертер не запущен' }) as unknown as Response,
    );
    (global as any).fetch = fetchMock;

    await expect(webApi.getBanks()).rejects.toThrow(/502.*Конвертер не запущен/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(String(url)).toContain(FIRST);
  });

  it('протухшее keep-alive соединение: вторая попытка на ТОТ ЖЕ хост спасает', async () => {
    // Регрессия: после простоя браузер переиспользует закрытый сокет, POST падает
    // без ответа. Сам он неидемпотентные запросы не повторяет — повторяем мы.
    const fetchMock = jest
      .fn()
      .mockImplementationOnce(netFail) // протухший сокет
      .mockImplementationOnce(async () => okJson([{ display: 'Сбер' }]));
    (global as any).fetch = fetchMock;

    await expect(webApi.getBanks()).resolves.toEqual([{ display: 'Сбер' }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // Оба раза — в ПЕРВЫЙ хост, а не уход на соседний
    expect(String(fetchMock.mock.calls[0][0])).toContain(FIRST);
    expect(String(fetchMock.mock.calls[1][0])).toContain(FIRST);
  });

  it('хост молчит дважды — уходим на следующий', async () => {
    const fetchMock = jest
      .fn()
      .mockImplementationOnce(netFail)
      .mockImplementationOnce(netFail)
      .mockImplementationOnce(async () => okJson([{ display: 'Сбер' }]));
    (global as any).fetch = fetchMock;

    await expect(webApi.getBanks()).resolves.toEqual([{ display: 'Сбер' }]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[2][0])).toContain(SECOND);
  });

  it('живой хост запоминается: второй запрос идёт сразу в него', async () => {
    const fetchMock = jest
      .fn()
      .mockImplementationOnce(netFail) // 127.0.0.1 молчит
      .mockImplementationOnce(netFail) // и со второй попытки тоже
      .mockImplementation(async () => okJson([]));
    (global as any).fetch = fetchMock;

    await webApi.getBanks(); // 127.0.0.1 ×2 → localhost
    await webApi.getBanks(); // должен пойти сразу в localhost

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(String(fetchMock.mock.calls[3][0])).toContain(SECOND);
  });

  it('все хосты мертвы — наружу сетевая ошибка', async () => {
    const fetchMock = jest.fn(netFail);
    (global as any).fetch = fetchMock;

    await expect(webApi.getBanks()).rejects.toThrow(/Failed to fetch/);
    expect(fetchMock).toHaveBeenCalledTimes(6); // 3 базы × 2 попытки
  });
});
