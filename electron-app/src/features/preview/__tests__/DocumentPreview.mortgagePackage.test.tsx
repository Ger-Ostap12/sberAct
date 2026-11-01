import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentPreview from '../DocumentPreview';
import { ALL_TEMPLATES } from '../../../templates';
import { ExtractedData } from '../../../types';
import { generateDocument } from '../../../services/electronApi';

jest.mock('../../../services/electronApi');
const generate = generateDocument as jest.MockedFunction<typeof generateDocument>;
afterEach(() => jest.clearAllMocks());

it.each([
  [6, 'Полное решение требует ручной правки для частичного удовлетворения.'],
  [5, 'Полное решение — файл шаблона не найден.'],
] as const)('результат из %s документов и замечание показаны без ложного сообщения', async (count, warning) => {
  const ids = ['mortgage_summons', 'mortgage_acceptance_short', 'mortgage_acceptance_long',
    'mortgage_notice', 'mortgage_decision', 'mortgage_full_decision'].slice(0, count);
  generate.mockResolvedValue({
    success: true, count, document_ids: ids,
    documents: Object.fromEntries(ids.map((id, index) => [id, {
      document_id: id, name: `Акт ${index + 1}`, file_path: `/out/${id}.docx`, order: index + 1,
    }])),
    warnings: [warning],
  });
  const data: ExtractedData = {
    documentType: 'mortgage_claim', confidence: 1, mortgageKind: 'military',
    fields: { documentCategory: 'mortgage', selectedMortgageKind: 'ddu' },
    obligations: [], rawText: '',
    metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
  };
  const template = ALL_TEMPLATES.find((item) => item.id === 'mortgage')!;
  render(<DocumentPreview extractedData={data} selectedTemplate={template}
    onDocumentGenerated={() => {}} onBack={() => {}} onNewDocument={() => {}} />);
  expect(screen.getByText('6. Решение (полный текст, ДДУ)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Сгенерировать документ/ }));
  expect(await screen.findByText(`${count} документов успешно сгенерированы!`)).toBeInTheDocument();
  expect(screen.getByText('Замечания к генерации:')).toBeInTheDocument();
  expect(screen.getByText(`• ${warning}`)).toBeInTheDocument();
  expect(screen.queryByText('Сгенерированы не все выбранные акты:')).not.toBeInTheDocument();
});
