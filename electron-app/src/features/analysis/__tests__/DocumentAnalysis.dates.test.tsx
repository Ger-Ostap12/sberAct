import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

it('не передаёт неверную дату в генерацию, после исправления отправляет дату и время в прежнем ISO-формате', () => {
  const documentData: DocumentData = {
    filePath: 'dates.docx', fileName: 'dates.docx', fileSize: 1, uploadDate: new Date('2024-01-01'),
  };
  const data: ExtractedData = {
    documentType: 'rtk_application', confidence: 1, entityType: 'individual',
    fields: { creditorName: 'ПАО Сбербанк', courtName: 'Арбитражный суд', caseNumber: 'A-1',
      date: '2026-04-10', courtHearingDateTime99: '2026-04-12T14:30' },
    obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
    metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
  };
  const done = jest.fn();
  render(<DocumentAnalysis documentData={documentData} extractedData={data}
    onAnalysisComplete={done} onBack={() => {}} />);
  fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
  const next = screen.getByRole('button', { name: 'Продолжить' });
  expect(next).toBeEnabled();
  const input = screen.getByRole('textbox', { name: 'Дата принятия определения:' });
  fireEvent.change(input, { target: { value: '33.13.2222' } });
  fireEvent.blur(input);
  expect(next).toBeDisabled();
  fireEvent.click(next);
  expect(done).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '29.02.2024' } });
  fireEvent.blur(input);
  expect(next).toBeEnabled();
  const deadline = screen.getByRole('textbox', { name: 'Установка срока на предоставление возражений:' });
  fireEvent.change(deadline, { target: { value: '31.02.2026' } });
  fireEvent.blur(deadline);
  expect(next).toBeDisabled();
  fireEvent.change(deadline, { target: { value: 'в течение 30 дней' } });
  fireEvent.blur(deadline);
  expect(next).toBeEnabled();
  fireEvent.click(next);
  expect(done).toHaveBeenCalledTimes(1);
  expect(done.mock.calls[0][0].fields).toMatchObject({
    date: '2024-02-29', courtHearingDateTime99: '2026-04-12T14:30',
    objectionsDeadline18: 'в течение 30 дней',
  });
});
