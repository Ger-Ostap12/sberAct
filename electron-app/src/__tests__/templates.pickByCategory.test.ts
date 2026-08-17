import { pickTemplate } from '../templates';
import { ExtractedData } from '../types';

const make = (sourceDocumentType: string, documentType?: string): ExtractedData =>
  ({
    documentType: documentType ?? sourceDocumentType,
    fields: { sourceDocumentType },
    collaterals: [],
  } as unknown as ExtractedData);

describe('pickTemplate — выбор категории «Ипотека» побеждает', () => {
  it('category=mortgage → шаблон mortgage даже если анализатор дал банкротный тип', () => {
    const data = make('physical_realization');
    expect(pickTemplate(data, 'mortgage').id).toBe('mortgage');
  });

  it('category=mortgage → mortgage даже при пустом sourceDocumentType', () => {
    const data = make('', '');
    expect(pickTemplate(data, 'mortgage').id).toBe('mortgage');
  });

  it('без категории: mortgage_claim из анализа по-прежнему даёт mortgage', () => {
    expect(pickTemplate(make('mortgage_claim')).id).toBe('mortgage');
  });

  it('category=bankruptcy не навязывает ипотеку банкротному документу', () => {
    expect(pickTemplate(make('physical_realization'), 'bankruptcy').id).not.toBe('mortgage');
  });
});
