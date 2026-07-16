import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';
import { maskDate, isValidDateStr } from '../../../shared/lib/dates';

interface AbsentDebtorSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

/** Поля блока: подпись → ключ в editedFields. Все три вводит пользователь —
 *  в заявлении этих дат нет, они берутся из материалов дела. */
const FIELDS: ReadonlyArray<[label: string, key: string]> = [
  ['Дата последней налоговой отчётности:', 'lastTaxReportDate'],
  ['Дата последней бухгалтерской отчётности:', 'lastAccountingReportDate'],
  ['Последняя операция по расчётным счетам:', 'lastAccountOperationDate'],
];

/** Секция «Информация по счетам» — видна при статусе должника «Отсутствующий».
 *  Признак отсутствующего должника (ст. 227, 230 Закона о банкротстве) — прекращение
 *  деятельности: год нет отчётности и операций по счетам. Даты вводятся вручную,
 *  маска дд.мм.гггг + проверка существования даты; генерацию ошибка не блокирует. */
const AbsentDebtorSection: React.FC<AbsentDebtorSectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Информация по счетам
    </Typography>
    <Grid container spacing={2}>
      {FIELDS.map(([label, key]) => {
        const value = editedFields[key] || '';
        const invalid = !isValidDateStr(value);
        return (
          <Grid item xs={12} key={key}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{label}</Typography>
              <TextField
                fullWidth
                value={value}
                onChange={(e) => onFieldChange(key, maskDate(e.target.value))}
                size="small"
                margin="dense"
                placeholder="дд.мм.гггг"
                inputProps={{ inputMode: 'numeric' }}
                error={invalid}
                helperText={invalid ? 'Введите существующую дату в формате дд.мм.гггг' : ''}
              />
            </Box>
          </Grid>
        );
      })}
    </Grid>
  </Box>
);

export default AbsentDebtorSection;
