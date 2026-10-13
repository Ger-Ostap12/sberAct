import React from 'react';
import { render, screen } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// В банкротстве должник один: кнопки добавления нет, лишних не показываем.

const documentData: DocumentData = {
  filePath: 'test.docx',
  fileName: 'test.docx',
  fileSize: 1,
  uploadDate: new Date('2024-01-01T00:00:00Z'),
};

const makeData = (): ExtractedData => ({
  documentType: 'rtk_application',
  confidence: 1,
  entityType: 'individual',
  fields: { courtName: 'Арбитражный суд', caseNumber: 'A-1', creditorName: 'ПАО Сбербанк' },
  obligations: [],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

const двое = [
  { id: 'd1', name: 'Первый Должник', address: 'адрес1', inn: '111' },
  { id: 'd2', name: 'Второй Должник', address: 'адрес2', inn: '222' },
] as ExtractedData['debtors'];

const renderForm = (mutate?: (d: ExtractedData) => void, mode: 'bankruptcy' | 'mortgage' = 'bankruptcy') => {
  const data = makeData();
  if (mutate) mutate(data);
  return render(
    <DocumentAnalysis
      documentData={documentData}
      extractedData={data}
      onAnalysisComplete={() => {}}
      onBack={() => {}}
      mode={mode}
    />,
  );
};

describe('банкротство: должник один', () => {
  it('кнопки добавления лица нет вообще', () => {
    renderForm();
    expect(screen.queryByRole('button', { name: /Добавить (должника|ответчика)/ }))
      .not.toBeInTheDocument();
  });

  it('второй должник из разбора не показывается', () => {
    renderForm(d => { d.debtors = двое; });
    expect(screen.getByDisplayValue('Первый Должник')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('Второй Должник')).not.toBeInTheDocument();
  });

  it('про отброшенных должников юрист узнаёт из предупреждения', () => {
    renderForm(d => { d.debtors = двое; });
    const предупреждение = screen.getByText(/нашёл 2 должников/);
    expect(предупреждение).toBeInTheDocument();
    expect(предупреждение).toHaveTextContent('Оставлен первый: Первый Должник');
    expect(предупреждение).toHaveTextContent('Не показаны: Второй Должник');
  });

  it('при одном должнике предупреждения нет', () => {
    renderForm(d => { d.debtors = [двое![0]]; });
    expect(screen.queryByText(/должником?в/)).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('Первый Должник')).toBeInTheDocument();
  });
});

describe('ипотека: ответчиков может быть несколько', () => {
  it('кнопка «Добавить ответчика» на месте', () => {
    renderForm(undefined, 'mortgage');
    expect(screen.getByRole('button', { name: 'Добавить ответчика' })).toBeInTheDocument();
  });

  it('оба ответчика показаны и предупреждения нет', () => {
    renderForm(d => { d.debtors = двое; }, 'mortgage');
    expect(screen.getByDisplayValue('Первый Должник')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Второй Должник')).toBeInTheDocument();
    expect(screen.queryByText(/в банкротстве должник один/)).not.toBeInTheDocument();
  });
});
