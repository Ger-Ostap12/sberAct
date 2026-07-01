import {
  getElectronAPI,
  hasElectronAPI,
  analyzeDocument,
  generateDocument,
  downloadAllDocuments,
  toggleDevTools,
} from '../electronApi';

const makeApi = () => ({
  isReady: jest.fn(() => true),
  selectFile: jest.fn(),
  saveFile: jest.fn(),
  readFile: jest.fn(),
  analyzeDocument: jest.fn(async () => ({ success: true } as any)),
  generateDocument: jest.fn(async () => ({ success: true, document_id: 'x' })),
  getTemplates: jest.fn(),
  downloadDocument: jest.fn(async () => ({ success: true })),
  downloadAllDocuments: jest.fn(async () => ({ success: true, filePath: '/tmp/a' })),
  getDownloadPaths: jest.fn(),
  getExtractedData: jest.fn(),
  toggleDevTools: jest.fn(),
});

afterEach(() => {
  delete (window as any).electronAPI;
  delete (window as any).openDevTools;
  jest.restoreAllMocks();
});

describe('hasElectronAPI', () => {
  it('false когда мост не инициализирован', () => {
    expect(hasElectronAPI()).toBe(false);
  });
  it('true когда electronAPI присутствует', () => {
    (window as any).electronAPI = makeApi();
    expect(hasElectronAPI()).toBe(true);
  });
});

describe('getElectronAPI', () => {
  it('кидает понятную ошибку без моста', () => {
    expect(() => getElectronAPI()).toThrow(/Electron API не доступен/);
  });
  it('возвращает объект API когда он есть', () => {
    const api = makeApi();
    (window as any).electronAPI = api;
    expect(getElectronAPI()).toBe(api);
  });
});

describe('обёртки делегируют в electronAPI', () => {
  it('analyzeDocument проксирует вход', async () => {
    const api = makeApi();
    (window as any).electronAPI = api;
    await analyzeDocument('C:/file.docx');
    expect(api.analyzeDocument).toHaveBeenCalledWith('C:/file.docx');
  });

  it('generateDocument проксирует запрос и возвращает результат', async () => {
    const api = makeApi();
    (window as any).electronAPI = api;
    const req = { template_type: 'rtk_single_obligation', data: {} };
    const res = await generateDocument(req);
    expect(api.generateDocument).toHaveBeenCalledWith(req);
    expect(res).toEqual({ success: true, document_id: 'x' });
  });

  it('downloadAllDocuments проксирует данные', async () => {
    const api = makeApi();
    (window as any).electronAPI = api;
    await downloadAllDocuments({ document_ids: '1,2', download_path: '' });
    expect(api.downloadAllDocuments).toHaveBeenCalledWith({
      document_ids: '1,2',
      download_path: '',
    });
  });

  it('обёртка кидает синхронно, если моста нет', () => {
    // getElectronAPI() бросает до создания промиса → throw синхронный.
    expect(() => analyzeDocument('x')).toThrow(/Electron API не доступен/);
  });
});

describe('toggleDevTools', () => {
  it('вызывает electronAPI.toggleDevTools когда доступен', () => {
    const api = makeApi();
    (window as any).electronAPI = api;
    toggleDevTools();
    expect(api.toggleDevTools).toHaveBeenCalled();
  });

  it('фолбэк на window.openDevTools', () => {
    const openDevTools = jest.fn();
    (window as any).openDevTools = openDevTools;
    toggleDevTools();
    expect(openDevTools).toHaveBeenCalled();
  });

  it('warn когда ничего не доступно', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    toggleDevTools();
    expect(warn).toHaveBeenCalled();
  });
});
