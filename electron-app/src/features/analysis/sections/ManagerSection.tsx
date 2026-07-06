import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface ManagerSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  /** Показывать поле «Саморегулируемая организация» — только для инициирующих актов
   *  (реализация/конкурсное/реструктуризация/наблюдение), где СРО обязательна. */
  showSro?: boolean;
}

/** Секция «Арбитражный управляющий» (ФИО, адрес, при инициировании — СРО). */
const ManagerSection: React.FC<ManagerSectionProps> = ({ editedFields, onFieldChange, showSro }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Арбитражный управляющий
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
        <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО:</Typography>
        <TextField
          fullWidth
          value={editedFields.managerName || ''}
          onChange={(e) => onFieldChange('managerName', e.target.value)}
          size="small"
          margin="dense"
        />
      </Box>
      </Grid>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
        <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:</Typography>
        <TextField
          fullWidth
          value={editedFields.managerAddress || ''}
          multiline
          onChange={(e) => onFieldChange('managerAddress', e.target.value)}
          size="small"
          margin="dense"
        />
      </Box>
      </Grid>
      {showSro && (
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
        <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Саморегулируемая организация:</Typography>
        <TextField
          fullWidth
          value={editedFields.sroName || ''}
          multiline
          onChange={(e) => onFieldChange('sroName', e.target.value)}
          size="small"
          margin="dense"
        />
      </Box>
      </Grid>
      )}
    </Grid>
  </Box>
);

export default ManagerSection;
