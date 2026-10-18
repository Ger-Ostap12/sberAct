import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Замер отзывчивости ввода: сколько стоит один символ в поле формы.
// Порог намеренно щадящий — ловим деградацию, а не микросекунды.

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
  fields: { courtName: 'Арбитражный суд', caseNumber: 'A-1', creditorName: 'ПАО Сбербанк' },
  obligations: [],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

describe('отзывчивость ввода в поля анализа', () => {
  it('символ в поле «Номер дела» стоит разумного времени', () => {
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={makeData()}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );

    const поле = screen.getByDisplayValue('A-1');
    const слово = 'А53-12345/2026';
    const замеры: number[] = [];

    for (let i = 0; i < слово.length; i++) {
      const t = performance.now();
      fireEvent.change(поле, { target: { value: слово.slice(0, i + 1) } });
      замеры.push(performance.now() - t);
    }

    const всего = замеры.reduce((a, b) => a + b, 0);
    const среднее = всего / замеры.length;
    const худший = Math.max(...замеры);
    // eslint-disable-next-line no-console
    console.log(
      `ввод ${слово.length} символов: всего ${всего.toFixed(0)} мс, ` +
      `среднее ${среднее.toFixed(1)} мс/символ, худший ${худший.toFixed(0)} мс`,
    );

    // 100 мс на символ — уже видимый глазу лаг при быстрой печати.
    expect(среднее).toBeLessThan(100);
  });
});
