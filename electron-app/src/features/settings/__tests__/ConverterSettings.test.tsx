import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConverterSettings from '../ConverterSettings';

// Настройки хранит сам конвертер, поэтому всё идёт по сети. Транспорт — моками.
jest.mock('../../../services/electronApi', () => ({
  convertSettings: jest.fn(),
  convertSaveSettings: jest.fn(),
  converterStart: jest.fn(),
}));

import {
  convertSaveSettings,
  convertSettings,
  converterStart,
} from '../../../services/electronApi';

const mockGet = convertSettings as jest.Mock;
const mockSave = convertSaveSettings as jest.Mock;
const mockStart = converterStart as jest.Mock;

// MUI-селектор — это combobox, а не button и не настоящий <select>.
const selector = () => screen.findByRole('combobox', { name: 'Режим использования ресурсов' });

const view = (over?: Record<string, unknown>) => ({
  auto: { profile: 'full', note: 'рабочая станция: больше 12 ГБ ОЗУ и больше 4 ядер' },
  override: { profile: null, llm_default: null },
  effective: { profile: 'full', llm_default: true },
  machine: { cores: 8, ram_gb: 31.3 },
  choices: ['auto', 'lean', 'balanced', 'full'],
  source: 'auto',
  locked_by_env: false,
  ...over,
});

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockResolvedValue(view());
});

describe('ConverterSettings', () => {
  it('показывает выбор режима и то, что определило железо', async () => {
    render(<ConverterSettings open />);

    // Пользователь ничего не выбирал — значит «Автоматически».
    expect(await selector()).toHaveTextContent('Автоматически');
    expect(screen.getByText(/Определено по компьютеру: Полный/)).toBeInTheDocument();
    expect(screen.getByText(/больше 12 ГБ ОЗУ/)).toBeInTheDocument();
  });

  it('выбор режима сохраняется и состояние берётся из ответа сервера', async () => {
    mockSave.mockResolvedValue(
      view({ override: { profile: 'lean', llm_default: null }, effective: { profile: 'lean', llm_default: false }, source: 'user' })
    );
    render(<ConverterSettings open />);

    await userEvent.click(await selector());
    await userEvent.click(await screen.findByRole('option', { name: 'Экономный' }));

    expect(mockSave).toHaveBeenCalledWith({ profile: 'lean' });
    await waitFor(async () => expect(await selector()).toHaveTextContent('Экономный'));
    expect(screen.getByText(/Меньше всего памяти/)).toBeInTheDocument();
  });

  it('locked_by_env: селектор заблокирован и причина названа', async () => {
    mockGet.mockResolvedValue(view({ locked_by_env: true, override: { profile: 'lean', llm_default: null } }));
    render(<ConverterSettings open />);

    expect(await screen.findByText(/задан при установке приложения/)).toBeInTheDocument();
    const field = await selector();
    expect(field).toHaveTextContent('Экономный');
    expect(field).toHaveAttribute('aria-disabled', 'true');
  });

  it('переключатель доочистки идёт из effective и сохраняется явно', async () => {
    mockSave.mockResolvedValue(
      view({ override: { profile: null, llm_default: false }, effective: { profile: 'full', llm_default: false } })
    );
    render(<ConverterSettings open />);

    const toggle = await screen.findByLabelText('Улучшать текст нейросетью по умолчанию');
    expect(toggle).toBeChecked();

    await userEvent.click(toggle);
    expect(mockSave).toHaveBeenCalledWith({ llm_default: false });
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it('свой выбор доочистки можно вернуть к значению режима', async () => {
    mockGet.mockResolvedValue(
      view({ override: { profile: null, llm_default: false }, effective: { profile: 'full', llm_default: false } })
    );
    mockSave.mockResolvedValue(view());
    render(<ConverterSettings open />);

    await userEvent.click(await screen.findByRole('button', { name: 'Вернуть как у режима' }));
    expect(mockSave).toHaveBeenCalledWith({ clear_llm_default: true });
  });

  it('кнопки возврата нет, пока пользователь ничего не выбирал', async () => {
    render(<ConverterSettings open />);
    await selector();

    expect(screen.queryByRole('button', { name: 'Вернуть как у режима' })).not.toBeInTheDocument();
  });

  it('конвертер не запущен: объяснение и кнопка запуска вместо настроек', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 502: Конвертер не запущен'));
    mockStart.mockResolvedValue({ ok: true });
    render(<ConverterSettings open />);

    expect(await screen.findByText(/запускается на шаге конвертации/)).toBeInTheDocument();
    expect(
      screen.queryByRole('combobox', { name: 'Режим использования ресурсов' })
    ).not.toBeInTheDocument();

    mockGet.mockResolvedValue(view());
    await userEvent.click(screen.getByRole('button', { name: 'Запустить конвертер' }));

    expect(await selector()).toBeInTheDocument();
    expect(mockStart).toHaveBeenCalled();
  });

  it('отказ сохранения показывается, настройки остаются на экране', async () => {
    mockSave.mockRejectedValue(
      new Error('HTTP 400: {"detail": {"code": "INVALID_SETTINGS", "message": "Неизвестное значение настройки."}}')
    );
    render(<ConverterSettings open />);

    await userEvent.click(await selector());
    await userEvent.click(await screen.findByRole('option', { name: 'Полный' }));

    expect(await screen.findByText('Неизвестное значение настройки.')).toBeInTheDocument();
    expect(await selector()).toBeInTheDocument();
  });

  it('закрытый диалог настройки не запрашивает', () => {
    render(<ConverterSettings open={false} />);
    expect(mockGet).not.toHaveBeenCalled();
  });
});
