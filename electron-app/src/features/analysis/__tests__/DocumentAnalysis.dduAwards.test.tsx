import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

it('в форме ДДУ передаёт выбор требований и обе присуждённые неустойки', async () => {
  const document: DocumentData = {
    filePath: 'ddu.docx', fileName: 'ddu.docx', fileSize: 1,
    uploadDate: new Date('2026-11-01T00:00:00Z'),
  };
  const data: ExtractedData = {
    documentType: 'mortgage_claim', confidence: 1, entityType: 'individual', mortgageKind: 'ddu',
    fields: { claimResolution: 'partial', principalDebt: '1000', interest: '200',
      forfeit: '50', forfeitInterest1362: '20', stateDuty16: '10', totalDebt: '1270',
      creditorName: 'ПАО Сбербанк' },
    recommendedActs: { entityType: 'individual', collateralOption: 'no_collateral',
      recommendedActIds: ['acceptance_definition'] },
    obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
    metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
  };
  const complete = jest.fn();
  render(<DocumentAnalysis documentData={document} extractedData={data} mode="mortgage"
    onAnalysisComplete={complete} onBack={() => {}} />);
  const next = await screen.findByRole('button', { name: 'Продолжить' });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Присуждённая неустойка за проценты'), { target: { value: '-1' } });
  expect(next).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Присуждённая неустойка за проценты'), { target: { value: '5' } });
  fireEvent.click(screen.getByRole('checkbox', { name: 'Расторгнуть кредитный договор' }));
  fireEvent.click(screen.getByRole('checkbox', { name: 'Обратить взыскание на заложенное имущество' }));
  fireEvent.click(next);
  expect(complete).toHaveBeenCalledTimes(1);
  expect(complete.mock.calls[0][0].fields).toMatchObject({
    selectedMortgageKind: 'ddu', mortgageAwardTermination: 'false',
    mortgageAwardDebt: 'true', mortgageAwardForeclosure: 'false',
    mortgageAwardInterestPenalty: '5', forfeitInterest1362: '20', totalDebt: '1270',
  });
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить полностью' }));
  expect(screen.queryByLabelText('Присуждённая неустойка за проценты')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Неустойка за просроченные проценты')).toBeInTheDocument();
});
