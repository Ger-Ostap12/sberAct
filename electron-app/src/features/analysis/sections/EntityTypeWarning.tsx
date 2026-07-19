import React from 'react';
import { Alert, AlertTitle } from '@mui/material';
import { ExtractedData } from '../../../types';

/**
 * Предупреждение, когда тип лица должника, который ПОДРАЗУМЕВАЕТ regex-тип
 * документа (`classify_document`), не совпал с типом лица, определённым по
 * извлечённым реквизитам (`detect_entity_type`: ИНН/ОГРНИП формат, орг.-форма
 * в имени должника).
 *
 * Зачем. Оба сигнала уже вычисляет backend для других целей — сверка их между
 * собой не требует новой модели, но ловит расхождения вроде «в имени должника
 * прямо написано ИП, а тип документа — юрлицо» (реальные случаи на корпусе).
 */

const ENTITY_LABEL: Record<string, string> = {
  individual: 'физическое лицо',
  legal: 'юридическое лицо',
  ip: 'индивидуальный предприниматель',
};

const entityLabel = (key: string): string => ENTITY_LABEL[key] || key;

interface EntityTypeWarningProps {
  warning?: ExtractedData['entityTypeWarning'];
}

const EntityTypeWarning: React.FC<EntityTypeWarningProps> = ({ warning }) => {
  if (!warning) return null;

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <AlertTitle>Перепроверьте тип лица должника</AlertTitle>
      Тип документа предполагает «{entityLabel(warning.expectedEntityType)}», но по
      реквизитам (ИНН/ОГРНИП, наименование должника) похоже на «{entityLabel(warning.actualEntityType)}».
      Сверьте «Выбор лица» ниже с текстом документа вручную.
    </Alert>
  );
};

export default EntityTypeWarning;
