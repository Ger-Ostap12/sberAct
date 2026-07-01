import React from 'react';
import { render } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Снапшот-сеть на текущий render формы анализа ДО дробления файла.
// Фиксирует структуру формы, чтобы вынос секций/карточек/хуков не менял вывод.

const documentData: DocumentData = {
  filePath: 'test.docx',
  fileName: 'test.docx',
  fileSize: 12345,
  uploadDate: new Date('2024-01-01T00:00:00Z'),
};

const extractedData: ExtractedData = {
  documentType: 'rtk_application',
  confidence: 0.9,
  entityType: 'legal',
  fields: {
    applicantName: 'ООО «Ромашка»',
    applicantAddress: '344000, г. Ростов-на-Дону, ул. Ленина, д. 1',
    courtName: 'Арбитражный суд Ростовской области',
    caseNumber: 'А53-12345/2024',
    creditorName: 'ПАО Сбербанк',
    debtorName: 'Иванов Иван Иванович',
    principalDebt: '100000',
    interest: '5000',
    totalDebt: '108000',
  },
  obligations: [
    { id: 'o1', contractNumber: '123', contractDate: '01.02.2024', obligationType: 'Кредитный договор' },
  ],
  collaterals: [],
  thirdParties: [],
  debtors: [
    { id: 'd1', name: 'Иванов Иван Иванович', inn: '610000000000', address: 'г. Ростов' },
  ],
  rawText: 'Текст заявления',
  metadata: { pageCount: 1, wordCount: 2, language: 'ru' },
};

describe('DocumentAnalysis — снапшот формы', () => {
  it('рендерит форму с переданными данными', () => {
    const { container } = render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={extractedData}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />
    );
    expect(container).toMatchSnapshot();
  });
});
