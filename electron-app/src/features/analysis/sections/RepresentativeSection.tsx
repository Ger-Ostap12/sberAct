// Секция «Представитель истца» (режим «Ипотека»): ФИО + срок доверенности (с/по).
// Плоские поля editedFields (representativeName / representativePoaFrom / …PoaTo).
import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { isValidFio } from '../../../shared/lib/validators';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface RepresentativeSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const RepresentativeSection: React.FC<RepresentativeSectionProps> = ({
  editedFields,
  onFieldChange,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Представитель истца
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО:</Typography>
          <TextField
            fullWidth
            value={editedFields.representativeName || ''}
            onChange={(e) => onFieldChange('representativeName', e.target.value)}
            size="small"
            margin="dense"
            error={!isValidFio(editedFields.representativeName)}
            helperText={!isValidFio(editedFields.representativeName) ? 'ФИО: Фамилия Имя Отчество или Фамилия И.О.' : undefined}
          />
        </Box>
      </Grid>
      <Grid item xs={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Доверенность с:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.representativePoaFrom)}
            onChange={(e) => onFieldChange('representativePoaFrom', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      <Grid item xs={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Доверенность по:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.representativePoaTo)}
            onChange={(e) => onFieldChange('representativePoaTo', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

export default RepresentativeSection;
