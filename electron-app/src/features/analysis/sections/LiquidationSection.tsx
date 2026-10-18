import { FieldInput } from '../components/FieldInput';
import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';
import { maskDate } from '../../../shared/lib/dates';

interface LiquidationSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

/** Номер заявления — только цифры. */
const sanitizeNumber = (raw: string): string => raw.replace(/\D/g, '');

/** Секция «Объявление о ликвидации» — видна при статусе должника «Ликвидируемый».
 *  Наименование ликвидатора авто-заполняется backend (liquidatorName); номер заявления
 *  (только цифры) и дата ликвидации (маска дд.мм.гггг) вводятся пользователем. */
const LiquidationSection: React.FC<LiquidationSectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Объявление о ликвидации
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Наименование ликвидатора:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.liquidatorName || ''}
            multiline
            onChange={(значение) => onFieldChange('liquidatorName', значение)}
            size="small"
            margin="dense"
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер заявления:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.liquidationApplicationNumber || ''}
            onChange={(значение) => onFieldChange('liquidationApplicationNumber', sanitizeNumber(значение))}
            size="small"
            margin="dense"
            inputProps={{ inputMode: 'numeric' }}
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ликвидации:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.liquidationDate || ''}
            onChange={(значение) => onFieldChange('liquidationDate', maskDate(значение))}
            size="small"
            margin="dense"
            placeholder="дд.мм.гггг"
            inputProps={{ inputMode: 'numeric' }}
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

export default LiquidationSection;
