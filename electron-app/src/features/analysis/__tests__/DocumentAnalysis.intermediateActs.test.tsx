import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Окно «Промежуточные»: упрощёнка только у РТК, возврат разделён на два акта.

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

const renderForm = () =>
  render(
    <DocumentAnalysis
      documentData={documentData}
      extractedData={makeData()}
      onAnalysisComplete={() => {}}
      onBack={() => {}}
    />,
  );

const box = (name: string) => screen.getByRole('checkbox', { name });
const вид = (name: string) => fireEvent.click(screen.getByRole('radio', { name }));
const самобанкрот = () => fireEvent.click(box('Самобанкрот'));

describe('акты упрощёнки идут за видом заявления', () => {
  it('при инициировании обе галки сняты', () => {
    renderForm();
    вид('Инициирование');
    expect(box('Продление упрощёнка')).not.toBeChecked();
    expect(box('Переход из упрощёнки в основное производство')).not.toBeChecked();
  });

  it('но поставить их руками можно: кнопки активны', () => {
    renderForm();
    вид('Инициирование');
    expect(box('Продление упрощёнка')).toBeEnabled();
    fireEvent.click(box('Продление упрощёнка'));
    expect(box('Продление упрощёнка')).toBeChecked();
  });

  it('при включении в РТК обе отмечены', () => {
    renderForm();
    вид('Включение в РТК');
    expect(box('Продление упрощёнка')).toBeChecked();
    expect(box('Переход из упрощёнки в основное производство')).toBeChecked();
  });

  it('у самобанкрота их тоже нет: это подвид инициирования', () => {
    renderForm();
    вид('Инициирование');
    самобанкрот();
    expect(box('Продление упрощёнка')).not.toBeChecked();
    expect(box('Переход из упрощёнки в основное производство')).not.toBeChecked();
  });

  it('возврат в РТК снова их отмечает', () => {
    renderForm();
    вид('Инициирование');
    вид('Включение в РТК');
    expect(box('Продление упрощёнка')).toBeChecked();
  });
});

describe('возврат разделён на два акта', () => {
  it('обе кнопки есть и отмечены по умолчанию', () => {
    renderForm();
    expect(box('Общий возврат')).toBeChecked();
    expect(box('Возврат нет ГП')).toBeChecked();
  });

  it('прежней общей кнопки «Возврат» больше нет', () => {
    renderForm();
    expect(screen.queryByRole('checkbox', { name: 'Возврат' })).not.toBeInTheDocument();
  });

  it('у самобанкрота «Возврат нет ГП» гаснет и снимается', () => {
    renderForm();
    вид('Инициирование');
    самобанкрот();
    expect(box('Возврат нет ГП')).toBeDisabled();
    expect(box('Возврат нет ГП')).not.toBeChecked();
    // Общий возврат самобанкроту положен.
    expect(box('Общий возврат')).toBeChecked();
    expect(box('Общий возврат')).toBeEnabled();
  });

  it('снятие самобанкротства возвращает кнопку и галку', () => {
    renderForm();
    вид('Инициирование');
    самобанкрот();
    самобанкрот();
    expect(box('Возврат нет ГП')).toBeEnabled();
    expect(box('Возврат нет ГП')).toBeChecked();
  });

  it('переход в РТК из самобанкротства тоже возвращает кнопку', () => {
    renderForm();
    вид('Инициирование');
    самобанкрот();
    вид('Включение в РТК');
    expect(box('Возврат нет ГП')).toBeEnabled();
    expect(box('Возврат нет ГП')).toBeChecked();
  });
});
