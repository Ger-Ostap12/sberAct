import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

it('проверяет частичное удовлетворение перед продолжением и передаёт отдельные суммы', async () => {
  const document: DocumentData = {
    filePath: 'mortgage.docx', fileName: 'mortgage.docx', fileSize: 1,
    uploadDate: new Date('2026-11-01T00:00:00Z'),
  };
  const data: ExtractedData = {
    documentType: 'mortgage_claim', confidence: 1, entityType: 'individual', mortgageKind: 'civil',
    fields: { claimResolution: 'full', principalDebt: '1000', interest: '200',
      forfeit: '50', stateDuty16: '10', creditorName: 'ПАО Сбербанк' },
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
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить частично' }));
  for (const label of ['Расторгнуть кредитный договор', 'Взыскать задолженность',
    'Обратить взыскание на заложенное имущество']) {
    fireEvent.click(screen.getByRole('checkbox', { name: label }));
  }
  expect(next).toBeDisabled();
  fireEvent.click(next);
  expect(complete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Взыскать задолженность' }));
  fireEvent.change(screen.getByLabelText('Присуждённый основной долг'), { target: { value: '700' } });
  expect(next).toBeEnabled();
  fireEvent.click(next);
  expect(complete).toHaveBeenCalledTimes(1);
  expect(complete.mock.calls[0][0].fields).toMatchObject({
    claimResolution: 'partial', selectedMortgageKind: 'civil',
    mortgageAwardTermination: 'false', mortgageAwardDebt: 'true', mortgageAwardForeclosure: 'false',
    mortgageAwardPrincipal: '700', principalDebt: '1000',
  });
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить полностью' }));
  expect(screen.queryByRole('group', { name: 'Частичное удовлетворение' })).not.toBeInTheDocument();
  fireEvent.click(next);
  expect(complete.mock.calls[1][0].fields).toMatchObject({
    claimResolution: 'full', principalDebt: '1000',
  });
});
