import { renderHook, act } from '@testing-library/react';
import { useDownloadDocument } from '../useDownloadDocument';
import * as api from '../../../../services/electronApi';

jest.mock('../../../../services/electronApi');
const mockedHas = api.hasElectronAPI as jest.MockedFunction<typeof api.hasElectronAPI>;
const mockedOne = api.downloadDocument as jest.MockedFunction<typeof api.downloadDocument>;
const mockedAll = api.downloadAllDocuments as jest.MockedFunction<
  typeof api.downloadAllDocuments
>;

beforeEach(() => {
  mockedHas.mockReturnValue(true);
  jest.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => jest.clearAllMocks());

describe('useDownloadDocument', () => {
  it('пакет: зовёт downloadAllDocuments и показывает путь сохранения', async () => {
    mockedAll.mockResolvedValue({ success: true, filePath: 'C:/downloads' });
    const { result } = renderHook(() => useDownloadDocument());

    await act(async () => {
      await result.current.download({ success: true, documentIds: ['a', 'b'] });
    });

    expect(mockedAll).toHaveBeenCalledWith({ document_ids: 'a,b', download_path: '' });
    expect(result.current.downloadMessage).toEqual({
      type: 'success',
      text: 'Документы успешно сохранены в: C:/downloads',
    });
  });

  it('один документ: зовёт downloadDocument', async () => {
    mockedOne.mockResolvedValue({ success: true, filePath: 'C:/act.docx' });
    const { result } = renderHook(() => useDownloadDocument());

    await act(async () => {
      await result.current.download({ success: true, documentId: 'doc1' });
    });

    expect(mockedOne).toHaveBeenCalledWith('doc1');
    expect(result.current.downloadMessage?.type).toBe('success');
  });

  it('нет документов → сообщение об ошибке', async () => {
    const { result } = renderHook(() => useDownloadDocument());

    await act(async () => {
      await result.current.download({ success: true });
    });

    expect(result.current.downloadMessage).toEqual({
      type: 'error',
      text: 'Нет доступных документов для скачивания',
    });
  });

  it('нет Electron API → понятная ошибка', async () => {
    mockedHas.mockReturnValue(false);
    const { result } = renderHook(() => useDownloadDocument());

    await act(async () => {
      await result.current.download({ success: true, documentIds: ['a'] });
    });

    expect(result.current.downloadMessage?.type).toBe('error');
    expect(result.current.downloadMessage?.text).toMatch(/Electron API не доступен/);
  });

  it('backend вернул success:false → ошибка из error', async () => {
    mockedAll.mockResolvedValue({ success: false, error: 'disk full' });
    const { result } = renderHook(() => useDownloadDocument());

    await act(async () => {
      await result.current.download({ success: true, documentIds: ['a'] });
    });

    expect(result.current.downloadMessage).toEqual({ type: 'error', text: 'disk full' });
  });
});
