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
