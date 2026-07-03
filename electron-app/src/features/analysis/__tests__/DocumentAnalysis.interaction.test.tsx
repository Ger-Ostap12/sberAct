import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
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
  // Карточки — сворачиваемые (Accordion), в шапке «Обязательство N [— № …]».
  it('стартует с одним обязательством', () => {
    renderForm();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
    expect(screen.queryByText(/Обязательство 2/)).not.toBeInTheDocument();
  });

  it('«Добавить обязательство» добавляет карточку', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить обязательство' }));
    expect(screen.getByText(/Обязательство 2/)).toBeInTheDocument();
  });

  it('кнопка удаления убирает обязательство', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить обязательство' }));
    expect(screen.getByText(/Обязательство 2/)).toBeInTheDocument();

    const removeButtons = screen.getAllByLabelText('Удалить обязательство');
    fireEvent.click(removeButtons[0]);
    expect(screen.queryByText(/Обязательство 2/)).not.toBeInTheDocument();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
  });

  it('редактирование номера договора обновляет поле (даже в свёрнутой карточке)', () => {
    renderForm();
    // Поля свёрнутой карточки остаются в DOM (MUI Collapse не размонтирует контент).
    const numberInput = screen.getByDisplayValue('111');
    fireEvent.change(numberInput, { target: { value: '222' } });
    expect(screen.getByDisplayValue('222')).toBeInTheDocument();
  });
});

describe('DocumentAnalysis — раскладка ФНС', () => {
  const renderWith = (creditorName?: string) => {
    const data = makeData();
    data.fields = { ...data.fields, creditorName: creditorName || '' };
    return render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
  };

  it('для обычного кредитора блоки «Залог», «Обязательства», «Третьи лица» показаны', () => {
    renderWith('ПАО Сбербанк');
    expect(screen.getByText('Залог')).toBeInTheDocument();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
    expect(screen.getByText('Третьи лица')).toBeInTheDocument();
  });

  it('для кредитора-ФНС блоки «Залог», «Обязательства», «Третьи лица» скрыты, финансы — по очередям', () => {
    renderWith('ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области');
    expect(screen.queryByText('Залог')).not.toBeInTheDocument();
    expect(screen.queryByText(/Обязательство 1/)).not.toBeInTheDocument();
    expect(screen.queryByText('Третьи лица')).not.toBeInTheDocument();
    expect(screen.getByText('Первая очередь')).toBeInTheDocument();
  });
});
