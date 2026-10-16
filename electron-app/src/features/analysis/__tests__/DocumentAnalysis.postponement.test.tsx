import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Подсписок «Отложение»: родительская галка и два акта под ней.

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

const renderForm = (onDone: (d: ExtractedData) => void = () => {}) =>
  render(
    <DocumentAnalysis
      documentData={documentData}
      extractedData={makeData()}
      onAnalysisComplete={onDone}
      onBack={() => {}}
    />,
  );

const checkbox = (name: string) => screen.getByRole('checkbox', { name });

describe('подсписок «Отложение»', () => {
  it('показаны родитель и два акта', () => {
    renderForm();
    expect(checkbox('Отложение')).toBeInTheDocument();
    expect(checkbox('Общее отложение')).toBeInTheDocument();
    expect(checkbox('Отложение 3 лицо')).toBeInTheDocument();
  });

  it('оба акта отмечены сразу', () => {
    renderForm();
    expect(checkbox('Общее отложение')).toBeChecked();
    expect(checkbox('Отложение 3 лицо')).toBeChecked();
    expect(checkbox('Отложение')).toBeChecked();
  });

  it('родитель гасит оба акта', () => {
    renderForm();
    fireEvent.click(checkbox('Отложение'));
    expect(checkbox('Общее отложение')).not.toBeChecked();
    expect(checkbox('Отложение 3 лицо')).not.toBeChecked();
  });

  it('родитель включает оба обратно', () => {
    renderForm();
    fireEvent.click(checkbox('Отложение'));
    fireEvent.click(checkbox('Отложение'));
    expect(checkbox('Общее отложение')).toBeChecked();
    expect(checkbox('Отложение 3 лицо')).toBeChecked();
  });

  it('акты снимаются по отдельности', () => {
    renderForm();
    fireEvent.click(checkbox('Отложение 3 лицо'));
    expect(checkbox('Общее отложение')).toBeChecked();
    expect(checkbox('Отложение 3 лицо')).not.toBeChecked();
  });

  it('при одном снятом родитель в промежуточном состоянии', () => {
    renderForm();
    fireEvent.click(checkbox('Отложение 3 лицо'));
    expect(checkbox('Отложение')).toHaveAttribute('data-indeterminate', 'true');
  });

  it('клик по родителю из промежуточного состояния включает оба', () => {
    renderForm();
    fireEvent.click(checkbox('Отложение 3 лицо'));
    fireEvent.click(checkbox('Отложение'));
    expect(checkbox('Общее отложение')).toBeChecked();
    expect(checkbox('Отложение 3 лицо')).toBeChecked();
  });

  it('остальные промежуточные акты на месте и не задеты', () => {
    renderForm();
    fireEvent.click(checkbox('Отложение'));
    expect(checkbox('Общий возврат')).toBeChecked();
    expect(checkbox('Возврат нет ГП')).toBeChecked();
    expect(checkbox('Продление Б/Д')).toBeChecked();
  });
});

describe('оба отложения уезжают в бэкенд', () => {
  // Форма пускает дальше только после явного выбора лица.
  const продолжить = (onDone: jest.Mock) => {
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: /Продолжить|Перейти/ }));
    expect(onDone).toHaveBeenCalled();
    return String(onDone.mock.calls[0][0].fields?.selectedActsIds || '').split(',');
  };

  it('в списке актов есть оба id', () => {
    const onDone = jest.fn();
    renderForm(onDone);
    const ids = продолжить(onDone);
    expect(ids).toContain('intermediate_postponement');
    expect(ids).toContain('intermediate_postponement_third_party');
  });

  it('снятый акт не уезжает', () => {
    const onDone = jest.fn();
    renderForm(onDone);
    fireEvent.click(checkbox('Отложение 3 лицо'));
    const ids = продолжить(onDone);
    expect(ids).toContain('intermediate_postponement');
    expect(ids).not.toContain('intermediate_postponement_third_party');
  });
});
