import { renderHook, waitFor } from '@testing-library/react';
import { useBanks } from '../useBanks';
import * as api from '../../../../services/electronApi';

jest.mock('../../../../services/electronApi');
const mockedGetBanks = api.getBanks as jest.MockedFunction<typeof api.getBanks>;

afterEach(() => jest.clearAllMocks());

describe('useBanks', () => {
  it('загружает банки с бэкенда и отдаёт список', async () => {
    const banks = [
      { display: 'Сбербанк', inn: '1', ogrn: '2', address: 'a', aliases: ['сбербанк'] },
    ];
    mockedGetBanks.mockResolvedValue(banks);

    const { result } = renderHook(() => useBanks());

    expect(result.current).toEqual([]); // до загрузки — пусто
    await waitFor(() => expect(result.current).toEqual(banks));
  });

  it('при ошибке бэкенда остаётся пустой список', async () => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
    mockedGetBanks.mockRejectedValue(new Error('backend down'));

    const { result } = renderHook(() => useBanks());

    await waitFor(() => expect(mockedGetBanks).toHaveBeenCalled());
    expect(result.current).toEqual([]);
  });
});
