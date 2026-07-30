// Блок «Удовлетворение иска» (режим «Ипотека»): исход по иску, выбирается
// юристом полностью вручную (автозаполнения из анализа нет).
import React from 'react';
import { Box, Typography, RadioGroup, FormControlLabel, Radio } from '@mui/material';
import { BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface ClaimResolutionSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const ClaimResolutionSection: React.FC<ClaimResolutionSectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 1, color: 'primary.main' }}>
      Удовлетворение иска
    </Typography>
    <RadioGroup
      value={editedFields.claimResolution || ''}
      onChange={(e) => onFieldChange('claimResolution', e.target.value)}
      sx={{ pl: 1 }}
    >
      <FormControlLabel value="full" control={<Radio size="small" />} label="Удовлетворить полностью" />
      <FormControlLabel value="partial" control={<Radio size="small" />} label="Удовлетворить частично" />
      <FormControlLabel value="deny" control={<Radio size="small" />} label="Отказать в удовлетворении" />
    </RadioGroup>
  </Box>
);

export default ClaimResolutionSection;
