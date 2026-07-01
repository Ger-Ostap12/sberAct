import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Interaction-тесты на CRUD-логику формы (страхуют вынос секций/карточек).

const documentData: DocumentData = {
  filePath: 'test.docx',
  fileName: 'test.docx',
  fileSize: 1,
  uploadDate: new Date('2024-01-01T00:00:00Z'),
};

const makeData = (): ExtractedData => ({
  documentType: 'rtk_application',
  confidence: 1,
  entityType: 'legal',
  fields: { courtName: 'Арбитражный суд', caseNumber: 'A-1' },
  obligations: [
    { id: 'o1', contractNumber: '111', contractDate: '01.02.2024', obligationType: 'Кредитный договор' },
  ],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

const renderForm = () =>
  render(
    <DocumentAnalysis
      documentData={documentData}
      extractedData={makeData()}
      onAnalysisComplete={() => {}}
      onBack={() => {}}
    />
  );

describe('DocumentAnalysis — CRUD обязательств', () => {
  it('стартует с одним обязательством', () => {
    renderForm();
    expect(screen.getByText('Обязательство 1')).toBeInTheDocument();
    expect(screen.queryByText('Обязательство 2')).not.toBeInTheDocument();
  });

  it('«Добавить обязательство» добавляет карточку', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить обязательство' }));
    expect(screen.getByText('Обязательство 2')).toBeInTheDocument();
  });

  it('кнопка удаления убирает обязательство', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить обязательство' }));
    expect(screen.getByText('Обязательство 2')).toBeInTheDocument();

    const removeButtons = screen.getAllByLabelText('Удалить обязательство');
    fireEvent.click(removeButtons[0]);
    expect(screen.queryByText('Обязательство 2')).not.toBeInTheDocument();
    expect(screen.getByText('Обязательство 1')).toBeInTheDocument();
  });

  it('редактирование номера договора обновляет поле', () => {
    renderForm();
    const card = screen.getByText('Обязательство 1').closest('.MuiCard-root') as HTMLElement;
    const numberInput = within(card).getByDisplayValue('111');
    fireEvent.change(numberInput, { target: { value: '222' } });
    expect(within(card).getByDisplayValue('222')).toBeInTheDocument();
  });
});
