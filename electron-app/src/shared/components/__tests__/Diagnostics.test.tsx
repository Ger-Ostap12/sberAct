import DiagnosticsBoundary from '../DiagnosticsBoundary';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ErrorNotice from '../ErrorNotice';
import { appendEvent, collectReport, diagnosticEntries, guarded, recordFailure, redact } from '../../lib/diagnostics';
import type { ElectronAPI } from '../../../services/electronApi';

jest.mock('../../../services/webApi', () => ({
  getBackendDiagnostics: jest.fn(async () => ({ events: [] })),
}));

afterEach(() => { delete window.electronAPI; });

it('показывает причину, подсказку, номер и сохраняет диагностический отчёт', async () => {
  const save = jest.fn(async (_text: string) => ({ saved: true }));
  const copy = jest.fn(async (_text: string) => undefined);
  window.electronAPI = {
    diagnosticsSnapshot: async () => ({ events: [{ time: '2026-11-03T01:00:00Z',
      component: 'converter', level: 'error', message: "No module named 'docling'", incidentId: 'startup-12345' }] }),
    diagnosticsSave: save, diagnosticsCopy: copy, getAppVersion: async () => '2.1.1',
  } as unknown as ElectronAPI;
  render(<ErrorNotice error={{ message: 'Не установлен компонент распознавания.',
    hint: 'Восстановите конвертер.', incidentId: 'startup-12345', kind: 'server' }} />);
  expect(screen.getByText('Не установлен компонент распознавания.')).toBeInTheDocument();
  expect(screen.getByText('Восстановите конвертер.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Подробности' }));
  await waitFor(() => expect(screen.getByText(/No module named/)).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'Копировать ошибку' }));
  await waitFor(() => expect(copy).toHaveBeenCalled());
  expect(JSON.parse(copy.mock.calls[0][0] as string).appVersion).toBe('2.1.1');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Сохранить отчёт' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить отчёт' }));
  await waitFor(() => expect(save).toHaveBeenCalled());
});

it('сетевая ошибка получает понятный текст и номер; POST выполняется один раз', async () => {
  const action = jest.fn(async () => { throw new TypeError('Failed to fetch'); });
  await expect(guarded('Не удалось начать конвертацию.', action)).rejects.toMatchObject({
    kind: 'offline', incidentId: expect.any(String),
  });
  expect(action).toHaveBeenCalledTimes(1);
});

it('результат ok:false сохраняет причину старта и не теряет подсказку', async () => {
  const result = await guarded('Не удалось запустить конвертер.', async () => ({
    ok: false, error: 'Не установлен компонент конвертации.', code: 'CONVERTER_DEPENDENCY_MISSING',
    hint: 'Восстановите конвертер.', incidentId: 'request-77777',
  }));
  expect(result.error).toBe('Не установлен компонент конвертации.');
  expect(result.incidentId).toBe('request-77777');
  expect(diagnosticEntries().some(e => e.incidentId === 'request-77777')).toBe(true);
});

it('отчёт ограничен и скрывает ФИО и идентификаторы документов', async () => {
  expect(redact('ИНН 123456789012, Ароян Ваче Рушани')).not.toContain('Ароян');
  expect(redact('ИНН 123456789012')).not.toContain('123456789012');
  recordFailure({ message: 'Ошибка проверки.', raw: 'debtorName: Иванов Иван Иванович', kind: 'unknown' });
  for (let n = 0; n < 520; n++) appendEvent({
    time: String(n), component: 'test', level: 'info', message: 'Проверка ' + n,
  }, false);
  expect(diagnosticEntries()).toHaveLength(500);
  const report = await collectReport();
  expect(report).not.toContain('Иванов Иван Иванович');
});


it('ошибка экрана не оставляет пустое окно, а её номер связан со стеком', async () => {
  const logging = jest.spyOn(console, 'error').mockImplementation(() => {});
  const Broken = (): React.ReactElement => { throw new Error('unique rendering failure'); };
  try {
    render(<DiagnosticsBoundary><Broken /></DiagnosticsBoundary>);
    expect(await screen.findByText('Не удалось отобразить экран.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Перезагрузить приложение' })).toBeInTheDocument();
    const cause = diagnosticEntries().find(e => e.message.includes('unique rendering failure'));
    expect(cause?.incidentId).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Номер сбоя: ' + cause?.incidentId)).toBeInTheDocument());
  } finally { logging.mockRestore(); }
});
