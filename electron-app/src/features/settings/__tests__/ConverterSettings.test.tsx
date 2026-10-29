import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConverterSettings from '../ConverterSettings';
import { getConverterLlm, getConverterProfile } from '../settingsStore';

// Выбор хранится в настройках приложения, конвертер нужен лишь для пояснения
// про эту машину. Транспорт — моками.
jest.mock('../../../services/electronApi', () => ({
  convertSettings: jest.fn(),
  convertSaveSettings: jest.fn(),
}));

import { convertSaveSettings, convertSettings } from '../../../services/electronApi';

const mockGet = convertSettings as jest.Mock;
const mockSave = convertSaveSettings as jest.Mock;

const selectorByLabel = (label: string) => screen.findByRole('combobox', { name: label });
const profileSelector = () => selectorByLabel('Режим использования ресурсов');
const llmSelector = () => selectorByLabel('Улучшать текст нейросетью');

const view = (over?: Record<string, unknown>) => ({
  auto: { profile: 'full', note: 'рабочая станция: больше 12 ГБ ОЗУ и больше 4 ядер' },
  override: { profile: null, llm_default: null },
  effective: { profile: 'full', llm_default: true },
  choices: ['auto', 'lean', 'balanced', 'full'],
  source: 'auto',
  locked_by_env: false,
  ...over,
});

beforeEach(() => {
  window.localStorage.clear();
  jest.clearAllMocks();
  mockGet.mockResolvedValue(view());
  mockSave.mockResolvedValue(view());
});

describe('ConverterSettings', () => {
  it('по умолчанию «Автоматически» и «Как решит режим»', async () => {
    render(<ConverterSettings open />);

    expect(await profileSelector()).toHaveTextContent('Автоматически');
    expect(await llmSelector()).toHaveTextContent('Как решит режим');
  });

  it('выбор режима сохраняется в настройках приложения', async () => {
    render(<ConverterSettings open />);

    await userEvent.click(await profileSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Экономный' }));

    expect(getConverterProfile()).toBe('lean');
    expect(await profileSelector()).toHaveTextContent('Экономный');
    expect(screen.getByText(/Меньше всего памяти/)).toBeInTheDocument();
  });

  it('выбор доочистки сохраняется тремя значениями', async () => {
    render(<ConverterSettings open />);

    await userEvent.click(await llmSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Всегда выключать' }));
    expect(getConverterLlm()).toBe('off');

    await userEvent.click(await llmSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Как решит режим' }));
    expect(getConverterLlm()).toBe('auto');
  });

  it('сохранённый выбор показывается при следующем открытии', async () => {
    render(<ConverterSettings open />);
    await userEvent.click(await profileSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Полный' }));

    const again = render(<ConverterSettings open />);
    expect(
      await within(again.container).findByRole('combobox', { name: 'Режим использования ресурсов' })
    ).toHaveTextContent('Полный');
  });

  it('конвертер не запущен: выбор всё равно работает', async () => {
    // Сайдкара нет — молчат оба запроса, и чтение, и запись.
    mockGet.mockRejectedValue(new Error('HTTP 502: Конвертер не запущен'));
    mockSave.mockRejectedValue(new Error('HTTP 502: Конвертер не запущен'));
    render(<ConverterSettings open />);

    await userEvent.click(await profileSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Экономный' }));

    expect(getConverterProfile()).toBe('lean');
    // Строки про эту машину без конвертера нет, и это не ошибка.
    expect(screen.queryByText(/Определено по компьютеру/)).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('отказ записи в конвертер не ломает сохранение выбора', async () => {
    mockSave.mockRejectedValue(new TypeError('Failed to fetch'));
    render(<ConverterSettings open />);

    await userEvent.click(await profileSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Средний' }));

    expect(getConverterProfile()).toBe('balanced');
    expect(await profileSelector()).toHaveTextContent('Средний');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('конвертер на связи: показывается его вердикт о машине и выбор ему отдаётся', async () => {
    render(<ConverterSettings open />);

    expect(await screen.findByText(/Определено по компьютеру: Полный/)).toBeInTheDocument();
    expect(screen.getByText(/больше 12 ГБ ОЗУ/)).toBeInTheDocument();

    await userEvent.click(await profileSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Экономный' }));
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith({ profile: 'lean' }));

    await userEvent.click(await llmSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Всегда включать' }));
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith({ llm_default: true }));

    await userEvent.click(await llmSelector());
    await userEvent.click(await screen.findByRole('option', { name: 'Как решит режим' }));
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith({ clear_llm_default: true }));
  });

  it('locked_by_env: селектор режима заблокирован и причина названа', async () => {
    mockGet.mockResolvedValue(view({ locked_by_env: true }));
    render(<ConverterSettings open />);

    expect(await screen.findByText(/задан при установке приложения/)).toBeInTheDocument();
    expect(await profileSelector()).toHaveAttribute('aria-disabled', 'true');
  });

  it('закрытый диалог ничего не запрашивает', () => {
    render(<ConverterSettings open={false} />);
    expect(mockGet).not.toHaveBeenCalled();
  });
});
