import { renderHook, act } from '@testing-library/react';
import { useGenerateDocument } from '../useGenerateDocument';
import * as api from '../../../../services/electronApi';
import { ExtractedData, TemplateType } from '../../../../types';

jest.mock('../../../../services/electronApi');
const mockedGenerate = api.generateDocument as jest.MockedFunction<
  typeof api.generateDocument
>;

const baseData = (): ExtractedData => ({
  documentType: 'rtk_application',
  confidence: 1,
  fields: { applicantName: 'ООО Ромашка' },
  obligations: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

const template: TemplateType = {
  id: 'rtk_single_obligation',
  name: 'РТК',
  description: '',
  category: 'РТК',
  fields: [],
};

afterEach(() => jest.clearAllMocks());

describe('useGenerateDocument', () => {
  it('один документ: заполняет documentId/documentPath и зовёт onDocumentGenerated', async () => {
    mockedGenerate.mockResolvedValue({
      success: true,
      document_id: 'doc1',
      file_path: '/out/act.docx',
    });
    const onGenerated = jest.fn();
    const { result } = renderHook(() =>
      useGenerateDocument(baseData(), template, onGenerated)
    );

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.generationResult).toEqual({
      success: true,
      documentId: 'doc1',
      documentPath: '/out/act.docx',
    });
    expect(onGenerated).toHaveBeenCalledWith('/out/act.docx');
    expect(result.current.isGenerating).toBe(false);
  });

  it('пакет документов: заполняет documentIds/count, onDocumentGenerated не зовётся', async () => {
    mockedGenerate.mockResolvedValue({
      success: true,
      documents: { a: 1 },
      document_ids: ['a', 'b'],
      count: 2,
    });
    const onGenerated = jest.fn();
    const { result } = renderHook(() =>
      useGenerateDocument(baseData(), template, onGenerated)
    );

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.generationResult).toMatchObject({
      success: true,
      documentIds: ['a', 'b'],
      count: 2,
    });
    expect(onGenerated).not.toHaveBeenCalled();
  });

  it('передаёт sourceDocumentType из полей приоритетнее documentType', async () => {
    mockedGenerate.mockResolvedValue({ success: true, document_id: 'x', file_path: 'p' });
    const data = baseData();
    data.fields.sourceDocumentType = 'legal_collection';
    const { result } = renderHook(() => useGenerateDocument(data, template, jest.fn()));

    await act(async () => {
      await result.current.generate();
    });

    expect(mockedGenerate).toHaveBeenCalledWith({
      template_type: 'rtk_single_obligation',
      data: expect.objectContaining({ sourceDocumentType: 'legal_collection' }),
    });
  });

  it('передаёт заинтересованных лиц: heirs и thirdParties — top-level поля, в fields их нет', async () => {
    mockedGenerate.mockResolvedValue({ success: true, document_id: 'x', file_path: 'p' });
    const data = baseData();
    data.heirs = [{ id: 'h1', name: 'Иванова М.И.', address: 'г. Ростов-на-Дону' }];
    data.thirdParties = [{ id: 't1', name: 'Сидоров П.П.', birthDate: '05.05.1980' }];
    const { result } = renderHook(() => useGenerateDocument(data, template, jest.fn()));

    await act(async () => {
      await result.current.generate();
    });

    expect(mockedGenerate).toHaveBeenCalledWith({
      template_type: 'rtk_single_obligation',
      data: expect.objectContaining({
        heirs: [{ id: 'h1', name: 'Иванова М.И.', address: 'г. Ростов-на-Дону' }],
        thirdParties: [{ id: 't1', name: 'Сидоров П.П.', birthDate: '05.05.1980' }],
      }),
    });
  });

  it('заинтересованных лиц нет → уезжают пустые массивы, не undefined', async () => {
    mockedGenerate.mockResolvedValue({ success: true, document_id: 'x', file_path: 'p' });
    const { result } = renderHook(() => useGenerateDocument(baseData(), template, jest.fn()));

    await act(async () => {
      await result.current.generate();
    });

    expect(mockedGenerate).toHaveBeenCalledWith({
      template_type: 'rtk_single_obligation',
      data: expect.objectContaining({ heirs: [], thirdParties: [] }),
    });
  });

  it('пакет документов: warnings по несгенерированным актам доезжают до UI', async () => {
    mockedGenerate.mockResolvedValue({
      success: true,
      documents: { a: 1 },
      document_ids: ['a'],
      count: 1,
      warnings: ['«Определение ВКЛ в РТК (реализация)» — файл шаблона не найден: ртк.docx'],
    });
    const { result } = renderHook(() =>
      useGenerateDocument(baseData(), template, jest.fn())
    );

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.generationResult).toMatchObject({
      success: true,
      count: 1,
      warnings: ['«Определение ВКЛ в РТК (реализация)» — файл шаблона не найден: ртк.docx'],
    });
  });

  it('ипотека: sourceDocumentType=mortgage_claim, выбранные акты не уходят (иначе банкротная пара)', async () => {
    mockedGenerate.mockResolvedValue({ success: true, document_id: 'x', file_path: 'p' });
    const mortgageTpl: TemplateType = { id: 'mortgage', name: 'Ипотека', description: '', category: 'Ипотека', fields: [] };
    const data = baseData();
    data.documentType = 'mortgage_claim';
    data.fields.selectedActsIds = 'physical_realization_decision,acceptance';
    data.fields.selectedActsData = '[{"id":"physical_realization_decision"}]';
    const { result } = renderHook(() => useGenerateDocument(data, mortgageTpl, jest.fn()));

    await act(async () => {
      await result.current.generate();
    });

    const sent = mockedGenerate.mock.calls[0][0];
    expect(sent.template_type).toBe('mortgage');
    expect(sent.data.sourceDocumentType).toBe('mortgage_claim');
    expect(sent.data.selectedActsIds).toBeUndefined();
    expect(sent.data.selectedActsData).toBeUndefined();
  });

  it('ошибка backend → generationResult.error', async () => {
    mockedGenerate.mockResolvedValue({ success: false, error: 'boom' });
    const { result } = renderHook(() =>
      useGenerateDocument(baseData(), template, jest.fn())
    );

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.generationResult).toEqual({ success: false, error: 'boom' });
  });

  it('исключение → generationResult.error из message', async () => {
    mockedGenerate.mockRejectedValue(new Error('network down'));
    jest.spyOn(console, 'error').mockImplementation(() => {});
    const { result } = renderHook(() =>
      useGenerateDocument(baseData(), template, jest.fn())
    );

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.generationResult).toEqual({
      success: false,
      error: 'network down',
    });
  });
});
