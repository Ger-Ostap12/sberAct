import React from 'react';
import { Alert, AlertTitle } from '@mui/material';
import { ExtractedData } from '../../../types';

/**
 * Предупреждение, когда наличие залога, которое ПОДРАЗУМЕВАЕТ regex-тип
 * документа (суффикс *_collateral / mortgage_claim), не совпало с фактически
 * извлечённым списком collaterals[].
 *
 * Зачем. Оба сигнала уже вычисляет backend для других целей — сверка их между
 * собой не требует новой модели, но ловит расхождения вроде «тип документа
 * залоговый, а предметы залога не извлеклись» и наоборот.
 */

interface CollateralWarningProps {
  warning?: ExtractedData['collateralWarning'];
}

const CollateralWarning: React.FC<CollateralWarningProps> = ({ warning }) => {
  if (!warning) return null;

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <AlertTitle>Перепроверьте наличие залога</AlertTitle>
      Тип документа предполагает {warning.expectedCollateral ? 'наличие' : 'отсутствие'} залога,
      но по извлечённым данным залог {warning.actualCollateral ? 'обнаружен' : 'не найден'}.
      Сверьте блок «Залог» ниже с текстом документа вручную.
    </Alert>
  );
};

export default CollateralWarning;
