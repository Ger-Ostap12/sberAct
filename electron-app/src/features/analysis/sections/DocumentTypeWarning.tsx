import React from 'react';
import { Alert, AlertTitle } from '@mui/material';
import { ExtractedData } from '../../../types';

/**
 * Предупреждение, когда второй независимый способ определения типа документа
 * (backend: эмбеддинги, presence-тест просительной части) не согласился с
 * основным regex-классификатором.
 *
 * Зачем. Regex-каскад `classify_document` проверен на golden-корпусе, но новый
 * банк/формулировка, под которую паттерн не писался, может привести к неверному
 * типу без единого явного сбоя — юрист узнает об этом только по неверному акту
 * на выходе. Ничего не меняется автоматически (риск ложного срабатывания
 * семантики выше, чем у отработанного regex) — только адресный сигнал
 * перепроверить «Вид заявления» самому.
 */

const FAMILY_LABEL: Record<'rtk' | 'initiation', string> = {
  rtk: 'включение в реестр требований кредиторов (без признания банкротом)',
  initiation: 'инициирование (признание банкротом + введение процедуры)',
};

interface DocumentTypeWarningProps {
  warning?: ExtractedData['documentTypeWarning'];
}

const DocumentTypeWarning: React.FC<DocumentTypeWarningProps> = ({ warning }) => {
  if (!warning) return null;

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <AlertTitle>Перепроверьте тип заявления</AlertTitle>
      Автоматическое определение решило, что это «{FAMILY_LABEL[warning.regexFamily]}»,
      но по смыслу просительной части документ больше похож на «{FAMILY_LABEL[warning.semanticFamily]}».
      Сверьте «Вид заявления» ниже с текстом документа вручную.
    </Alert>
  );
};

export default DocumentTypeWarning;
