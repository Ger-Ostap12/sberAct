// Секция «Платёжные поручения»: даты ПП по депозиту и госпошлине (маркеры [80]/[81]).
// Отдельный блок, потому что у самобанкрота «Финансовые данные» скрыты, а эти две
// даты юристу нужны при любом заявителе.
import { FieldInput } from '../components/FieldInput';
import React from 'react';
import { Box, Typography, Grid } from '@mui/material';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface PaymentOrdersSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const PaymentOrdersSection: React.FC<PaymentOrdersSectionProps> = ({
  editedFields,
  onFieldChange,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Платёжные поручения
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ПП депозит:</Typography>
          <FieldInput
            fullWidth
            type="date"
            value={toInputDate(editedFields.ppDepositDate80)}
            onChange={(значение) => onFieldChange('ppDepositDate80', fromInputDate(значение))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ПП ГП:</Typography>
          <FieldInput
            fullWidth
            type="date"
            value={toInputDate(editedFields.ppStateDutyDate81)}
            onChange={(значение) => onFieldChange('ppStateDutyDate81', fromInputDate(значение))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

export default PaymentOrdersSection;
