import { webApi } from '../webApi';

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
