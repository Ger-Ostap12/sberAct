import React from 'react';
import { render, screen } from '@testing-library/react';
import UpdateDialog from './UpdateDialog';
import { updateCheck, UpdateCheckResult } from '../../services/electronApi';

jest.mock('../../services/electronApi', () => ({
  updateCheck: jest.fn(),
  onUpdateProgress: () => () => {},
  onConverterProgress: () => () => {},
  onUpdateError: () => () => {},
}));

const base: UpdateCheckResult = {
  ok: true,
  app: { available: false, version: '2.1.2' },
  converter: { available: false },
};
function show(converter: UpdateCheckResult['converter']) {
  (updateCheck as jest.Mock).mockResolvedValue({ ...base, converter });
  render(<UpdateDialog open currentVersion="2.1.2" onClose={() => {}} />);
}
test('does not claim OCR is current when the package has no OCR update', async () => {
  show({ available: false, status: 'not_in_package', installed: true });
  expect(await screen.findByText('В комплекте нет обновления OCR. Установленный модуль будет сохранён.')).toBeInTheDocument();
  expect(screen.queryByText('Актуальная версия')).not.toBeInTheDocument();
});
test('reports matching files only after verification against the package', async () => {
  show({ available: false, status: 'matches_package', installed: true });
  expect(await screen.findByText('Установленные файлы OCR совпадают с комплектом.')).toBeInTheDocument();
});
test('explains that an app-only package will not install missing OCR', async () => {
  show({ available: false, status: 'not_in_package', installed: false });
  expect(await screen.findByText('В комплекте нет OCR. Модуль конвертации не будет установлен.')).toBeInTheDocument();
});

test('shows actual differences separately from the full replacement size', async () => {
  show({ available: true, status: 'update_available', filesMissing: 1, filesChanged: 2,
    filesDeleted: 3, bytes: 1024, replacementFiles: 33760, replacementBytes: 6167616397 });
  expect(await screen.findByText(/Добавить: 1, заменить: 2, удалить лишних: 3/)).toBeInTheDocument();
  expect(screen.getByText(/При установке модуль заменяется целиком: 33760 файлов/)).toBeInTheDocument();
});
