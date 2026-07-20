import React from 'react';
import { Alert, AlertTitle } from '@mui/material';
import { ExtractedData } from '../../../types';

/**
 * Предупреждение, когда второй независимый способ извлечения имени должника
 * (backend: NER-харвест кандидатов + ролевой якорь «Должник/Ответчик») не
 * согласился с основным regex-экстрактором `debtorName`.
 *
 * Зачем. Позиционный regex проверен на golden, но незнакомая вёрстка метки
 * («ООО Форте Пром ГМБХ» без кавычек уходит в ФИО; «Гражданин Российской
 * Федерации» вместо имени) даёт неверное имя — а от него зависит и тип лица
 * в акте. Ничего не меняется автоматически (риск ложного срабатывания второго
 * способа выше отработанного regex) — только адресный сигнал сверить имя.
 */

interface DebtorNameWarningProps {
  warning?: ExtractedData['debtorNameWarning'];
}

const DebtorNameWarning: React.FC<DebtorNameWarningProps> = ({ warning }) => {
  if (!warning) return null;

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <AlertTitle>Перепроверьте имя должника</AlertTitle>
      Автоматически извлечено «{warning.regexName}», но второй способ проверки
      нашёл «{warning.semanticName}». Сверьте ФИО/наименование должника с текстом
      документа вручную.
    </Alert>
  );
};

export default DebtorNameWarning;
