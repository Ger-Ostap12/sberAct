import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface LiquidationSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

/** Номер заявления — только цифры. */
const sanitizeNumber = (raw: string): string => raw.replace(/\D/g, '');

/** Дата ликвидации — маска дд.мм.гггг: берём цифры (макс 8) и расставляем точки. */
const maskDate = (raw: string): string => {
  const d = raw.replace(/\D/g, '').slice(0, 8);
  const parts = [d.slice(0, 2), d.slice(2, 4), d.slice(4, 8)].filter(Boolean);
  return parts.join('.');
};

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
          <TextField
            fullWidth
            value={editedFields.liquidatorName || ''}
            multiline
            onChange={(e) => onFieldChange('liquidatorName', e.target.value)}
            size="small"
            margin="dense"
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер заявления:</Typography>
          <TextField
            fullWidth
            value={editedFields.liquidationApplicationNumber || ''}
            onChange={(e) => onFieldChange('liquidationApplicationNumber', sanitizeNumber(e.target.value))}
            size="small"
            margin="dense"
            inputProps={{ inputMode: 'numeric' }}
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ликвидации:</Typography>
          <TextField
            fullWidth
            value={editedFields.liquidationDate || ''}
            onChange={(e) => onFieldChange('liquidationDate', maskDate(e.target.value))}
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
