import { FieldInput } from '../components/FieldInput';
import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface PriorCollectionSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const rawAmount = (value: string) => value.replace(/[^\d.,]/g, '').replace(',', '.');

/**
 * Секция «Сведения о взыскании» (ранее вынесенное решение суда до банкротства):
 * суд, номер дела, сумма, дата, госпошлина. Перенесено из DocumentAnalysis 1:1.
 */
const PriorCollectionSection: React.FC<PriorCollectionSectionProps> = ({
  editedFields,
  onFieldChange,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Сведения о взыскании
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Кем взыскано:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.priorCourtName || ''}
            onChange={(значение) => onFieldChange('priorCourtName', значение)}
            size="small"
            margin="dense"
            placeholder="Ворошиловский районный суд г. Ростова-на-Дону"
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер дела:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.priorCaseNumber || ''}
            onChange={(значение) => onFieldChange('priorCaseNumber', значение)}
            size="small"
            margin="dense"
            placeholder="2-2523/2025"
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Взысканная сумма:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.priorAmount || ''}
            onChange={(значение) => onFieldChange('priorAmount', rawAmount(значение))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата решения:</Typography>
          <FieldInput
            fullWidth
            type="date"
            value={toInputDate(editedFields.priorDecisionDate)}
            onChange={(значение) => onFieldChange('priorDecisionDate', fromInputDate(значение))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Госпошлина:</Typography>
          <FieldInput
            fullWidth
            value={editedFields.priorStateDuty || ''}
            onChange={(значение) => onFieldChange('priorStateDuty', rawAmount(значение))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

export default PriorCollectionSection;
