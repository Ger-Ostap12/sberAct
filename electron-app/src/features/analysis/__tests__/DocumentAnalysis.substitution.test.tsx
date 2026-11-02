
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

jest.setTimeout(30000);
const document = (name: string): DocumentData => ({ fileName: name, filePath: name, fileSize: 1, uploadDate: new Date('2026-11-02') });
const data = (): ExtractedData => ({
  documentType: 'rtk_application', confidence: 1, entityType: 'individual',
  fields: { judge: 'Панова Кристина Олеговна', creditorName: 'ПАО Сбербанк' },
  recommendedActs: { entityType: 'individual', collateralOption: 'no_collateral', recommendedActIds: ['acceptance_definition'] },
  obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

it('блокирует продолжение до выбора замещающего судьи и сбрасывает режим для нового заявления', async () => {
  const done = jest.fn();
  const { rerender } = render(<DocumentAnalysis documentData={document('first.docx')} extractedData={data()}
    onAnalysisComplete={done} onBack={() => {}} />);
  const next = await screen.findByRole('button', { name: 'Продолжить' });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Взаимозамена' }));
  expect(next).toBeDisabled();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Судья по взаимозамене' }));
  fireEvent.click(screen.getByRole('option', { name: 'Тютюник П.Н.' }));
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  expect(done).toHaveBeenCalledTimes(1);
  expect(done.mock.calls[0][0].fields).toMatchObject({ judgeSubstitutionEnabled: 'true',
    judge: 'Панова К.О.', substituteJudge: 'Тютюник П.Н.' });
  rerender(<DocumentAnalysis documentData={document('second.docx')} extractedData={data()}
    onAnalysisComplete={done} onBack={() => {}} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Взаимозамена' })).toHaveAttribute('aria-pressed', 'false'));
  expect(screen.queryByRole('combobox', { name: 'Судья по взаимозамене' })).not.toBeInTheDocument();
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  expect(done.mock.calls[1][0].fields.substituteJudge).toBeUndefined();
});
