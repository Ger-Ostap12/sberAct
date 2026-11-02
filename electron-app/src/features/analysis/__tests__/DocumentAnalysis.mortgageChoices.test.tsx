import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData, MortgageKind } from '../../../types';
import { mortgageChoicesError, resetMortgageChoices } from '../lib/mortgageChoices';

jest.setTimeout(30000);

const document = (name: string): DocumentData => ({
  filePath: name, fileName: name, fileSize: 1, uploadDate: new Date('2026-11-02T00:00:00Z'),
});
const data = (kind: MortgageKind): ExtractedData => ({
  documentType: 'mortgage_claim', confidence: 1, entityType: 'individual', mortgageKind: kind,
  fields: { solidaryLiability: 'true', claimResolution: 'full', creditorName: 'ПАО Сбербанк',
    principalDebt: '1000', interest: '200', forfeit: '50', stateDuty16: '10' },
  recommendedActs: { entityType: 'individual', collateralOption: 'no_collateral', recommendedActIds: ['acceptance_definition'] },
  mortgageProperties: [{ id: 'property-1', description: 'Жилой дом', area: '84', cadastralNumber: '20:06:1234567:111' }],
  obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

it.each(['civil', 'ddu', 'military'] as const)('требует оба выбора для каждого нового заявления %s', async (kind) => {
  const complete = jest.fn();
  const { rerender } = render(<DocumentAnalysis documentData={document('first.docx')} extractedData={data(kind)}
    mode="mortgage" onAnalysisComplete={complete} onBack={() => {}} />);
  const next = await screen.findByRole('button', { name: 'Продолжить' });
  expect(next).toBeDisabled();
  expect(screen.getByRole('radio', { name: 'Солидарное' })).not.toBeChecked();
  expect(screen.getByRole('radio', { name: 'Удовлетворить полностью' })).not.toBeChecked();
  fireEvent.click(screen.getByRole('radio', { name: 'Солидарное' }));
  expect(next).toBeDisabled();
  fireEvent.click(next);
  expect(complete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить полностью' }));
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  expect(complete.mock.calls[0][0].fields).toMatchObject({ solidaryLiability: 'true', claimResolution: 'full' });
  expect(complete.mock.calls[0][0].mortgageProperties[0].area).toBe('84');
  rerender(<DocumentAnalysis documentData={document('second.docx')} extractedData={data(kind)}
    mode="mortgage" onAnalysisComplete={complete} onBack={() => {}} />);
  await waitFor(() => expect(next).toBeDisabled());
  expect(screen.getByRole('radio', { name: 'Солидарное' })).not.toBeChecked();
  expect(screen.getByRole('radio', { name: 'Удовлетворить полностью' })).not.toBeChecked();
  fireEvent.click(screen.getByRole('radio', { name: 'Несолидарное' }));
  expect(next).toBeDisabled();
  fireEvent.click(screen.getByRole('radio', { name: 'Отказать в удовлетворении' }));
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  expect(complete.mock.calls[1][0].fields).toMatchObject({ solidaryLiability: 'false', claimResolution: 'deny' });
});

it('сохраняет площадь при ручной правке и не подмешивает старую карточку при пустом массиве', async () => {
  const source = data('civil');
  const complete = jest.fn();
  const { rerender } = render(<DocumentAnalysis documentData={document('area.docx')} extractedData={source}
    mode="mortgage" onAnalysisComplete={complete} onBack={() => {}} />);
  const area = await screen.findByLabelText('Общая площадь (кв. м.)');
  expect(area).toHaveValue('84');
  fireEvent.change(area, { target: { value: '85' } });
  fireEvent.blur(area);
  fireEvent.click(screen.getByRole('radio', { name: 'Несолидарное' }));
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить полностью' }));
  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
  expect(complete.mock.calls[0][0].mortgageProperties[0].area).toBe('85');
  const empty = { ...data('civil'), mortgageProperties: [], fields: { mortgageCollateralDescription1221: 'Старый ошибочный текст' } };
  rerender(<DocumentAnalysis documentData={document('empty.docx')} extractedData={empty}
    mode="mortgage" onAnalysisComplete={complete} onBack={() => {}} />);
  await waitFor(() => expect(screen.queryByDisplayValue('Старый ошибочный текст')).not.toBeInTheDocument());
});

it('сброс не меняет исходные данные и сохраняет остальные поля', () => {
  const fields = { solidaryLiability: 'true', claimResolution: 'deny', creditorName: 'Банк' };
  expect(resetMortgageChoices(fields)).toEqual({ creditorName: 'Банк' });
  expect(fields.claimResolution).toBe('deny');
  expect(mortgageChoicesError({})).toMatch(/солидарное/);
  expect(mortgageChoicesError({ solidaryLiability: 'false' })).toMatch(/исход/);
  expect(mortgageChoicesError({ solidaryLiability: 'false', claimResolution: 'deny' })).toBeNull();
});
