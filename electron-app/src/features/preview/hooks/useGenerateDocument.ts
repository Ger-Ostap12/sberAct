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

      // Ипотечный шаблон выбран пользователем в первом окне — фиксируем
      // sourceDocumentType='mortgage_claim', иначе бэкенд не включит ипотечную
      // ветку (is_mortgage_document) для документа, доклассифицированного как банкротный.
      const isMortgageTemplate = selectedTemplate.id === 'mortgage';
      const generationData = {
        ...extractedData.fields,
        // sourceDocumentType из полей анализа приоритетнее, чтобы не терять классификацию
        sourceDocumentType: isMortgageTemplate
          ? 'mortgage_claim'
          : extractedData.fields.sourceDocumentType || extractedData.documentType,
        // Ипотека — фиксированный пакет из 5 актов. Выбранные акты (банкротный блок)
        // не применяем: их наличие уводит бэкенд в ветку «выбранных актов» и
        // ипотечный пакет не собирается. Гасим ключи только для ипотеки.
        ...(isMortgageTemplate ? { selectedActsIds: undefined, selectedActsData: undefined } : {}),
        obligations: extractedData.obligations || [],
        // Заинтересованные лица = наследники = третьи лица (единая категория, маркеры
        // [25.x]/[52.x]/[54.x]). Оба массива — top-level поля ExtractedData, в fields их
        // нет, поэтому без явного проброса до генерации они не доезжали вообще.
        heirs: extractedData.heirs || [],
        thirdParties: extractedData.thirdParties || [],
        // Ипотека: ответчики и предмет залога — top-level массивы ExtractedData, в
        // fields их нет. Без явного проброса до бэкенда не доезжают слоты ответчиков
        // ([1400.x] «Копия: <ответчик>» в извещении), склейка нескольких должников
        // и маркеры предмета ([1226]-[1234]).
        debtors: extractedData.debtors || [],
        mortgageProperties: extractedData.mortgageProperties || [],
        coborrowers: extractedData.coborrowers || [],
        guarantors: extractedData.guarantors || [],
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
            warnings: result.warnings,
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
