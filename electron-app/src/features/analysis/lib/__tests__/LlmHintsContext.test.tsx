import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { LlmHintsProvider, useLlmHints } from '../LlmHintsContext';

const mockStart = jest.fn();
jest.mock('../../../../services/electronApi', () => ({
  llmHintsStart: (...a: unknown[]) => mockStart(...a),
  llmHintsStatus: jest.fn(),
  llmHintsCancel: jest.fn(),
}));

let mockEnabled = true;
jest.mock('../../../settings/settingsStore', () => ({
  isLlmHintsEnabled: () => mockEnabled,
}));

const Probe: React.FC = () => {
  const { running } = useLlmHints();
  return <div data-testid="probe">{running ? 'идёт' : 'нет'}</div>;
};

const renderWith = (props: Partial<React.ComponentProps<typeof LlmHintsProvider>> = {}) =>
  render(
    <LlmHintsProvider rawText="текст заявления" regexValues={{}} enabled {...props}>
      <Probe />
    </LlmHintsProvider>,
  );

describe('LlmHintsProvider — когда слой вообще не запускается', () => {
  beforeEach(() => {
    mockStart.mockReset();
    mockStart.mockResolvedValue({ job_id: 'x' });
    mockEnabled = true;
  });

  it('выключенная настройка НЕ создаёт задачу: это выключатель нагрузки, а не показа', async () => {
    mockEnabled = false;
    renderWith();
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('нет'));
    expect(mockStart).not.toHaveBeenCalled();
  });

  it('не ипотека — задачи нет (на этой итерации поддержана только она)', async () => {
    renderWith({ enabled: false });
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('нет'));
    expect(mockStart).not.toHaveBeenCalled();
  });

  it('пустой текст документа — задачи нет', async () => {
    renderWith({ rawText: '' });
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('нет'));
    expect(mockStart).not.toHaveBeenCalled();
  });

  it('при включённой настройке и ипотеке задача создаётся', async () => {
    renderWith();
    await waitFor(() => expect(mockStart).toHaveBeenCalledTimes(1));
  });

  it('недоступный слой не ломает форму: ошибка старта проглатывается', async () => {
    mockStart.mockRejectedValue(new Error('503'));
    renderWith();
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('нет'));
  });
});
