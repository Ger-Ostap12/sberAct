import { useState, useCallback } from 'react';
import { ExtractedData, TemplateType } from '../../../types';
import { generateDocument } from '../../../services/electronApi';
import { GenerationState } from '../types';

interface UseGenerateDocument {
  isGenerating: boolean;
  generationResult: GenerationState | null;
  generate: () => Promise<void>;
}

/**
 * Генерация судебного акта через backend. Логика перенесена 1:1 из
 * DocumentPreview.handleGenerateDocument (валидация → сбор данных → вызов →
 * разбор ответа: один документ vs пакет).
 */
export const useGenerateDocument = (
  extractedData: ExtractedData,
  selectedTemplate: TemplateType,
  onDocumentGenerated: (documentPath: string) => void
): UseGenerateDocument => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationResult, setGenerationResult] = useState<GenerationState | null>(null);

  const generate = useCallback(async () => {
    try {
      setIsGenerating(true);
      setGenerationResult(null);

      if (!extractedData || !extractedData.fields) {
        throw new Error('Нет данных для генерации документа');
      }
      if (!selectedTemplate) {
        throw new Error('Не выбран шаблон документа');
      }

      const generationData = {
        ...extractedData.fields,
        // sourceDocumentType из полей анализа приоритетнее, чтобы не терять классификацию
        sourceDocumentType:
          extractedData.fields.sourceDocumentType || extractedData.documentType,
        obligations: extractedData.obligations || [],
      };

      const result = await generateDocument({
        template_type: selectedTemplate.id,
        data: generationData,
      });

      if (result.success) {
        if (result.documents && result.document_ids) {
          // Пакет документов
          setGenerationResult({
            success: true,
            documents: result.documents,
            documentIds: result.document_ids,
            count: result.count,
          });
        } else {
          // Один документ (старый формат)
          setGenerationResult({
            success: true,
            documentId: result.document_id,
            documentPath: result.file_path,
          });
          if (result.file_path) onDocumentGenerated(result.file_path);
        }
      } else {
        setGenerationResult({
          success: false,
          error: result.error || 'Ошибка при генерации документа',
        });
      }
    } catch (err) {
      const e = err as { message?: string; error?: string };
      console.error('Error generating document:', err);
      setGenerationResult({
        success: false,
        error: e?.message || e?.error || 'Ошибка при генерации документа',
      });
    } finally {
      setIsGenerating(false);
    }
  }, [extractedData, selectedTemplate, onDocumentGenerated]);

  return { isGenerating, generationResult, generate };
};
