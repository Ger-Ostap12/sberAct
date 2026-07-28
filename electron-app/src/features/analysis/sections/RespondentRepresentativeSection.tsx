// Секция «Представитель ответчика» (режим «Ипотека»): только ФИО.
// Плоское поле editedFields.respondentRepresentativeName.
import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface RespondentRepresentativeSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const RespondentRepresentativeSection: React.FC<RespondentRepresentativeSectionProps> = ({
  editedFields,
  onFieldChange,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Представитель ответчика
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО:</Typography>
          <TextField
            fullWidth
            value={editedFields.respondentRepresentativeName || ''}
            onChange={(e) => onFieldChange('respondentRepresentativeName', e.target.value)}
            size="small"
            margin="dense"
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

export default RespondentRepresentativeSection;
