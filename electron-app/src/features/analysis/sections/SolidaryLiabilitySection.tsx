import React from 'react';
import { Box, FormControl, FormLabel, FormControlLabel, Radio, RadioGroup } from '@mui/material';
import { BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface SolidaryLiabilitySectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const SolidaryLiabilitySection: React.FC<SolidaryLiabilitySectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <FormControl required>
      <FormLabel id="mortgage-solidary-label">Солидарность</FormLabel>
      <RadioGroup aria-labelledby="mortgage-solidary-label" value={editedFields.solidaryLiability || ''}
        onChange={(event) => onFieldChange('solidaryLiability', event.target.value)}>
        <FormControlLabel value="true" control={<Radio size="small" />} label="Солидарное" />
        <FormControlLabel value="false" control={<Radio size="small" />} label="Несолидарное" />
      </RadioGroup>
    </FormControl>
  </Box>
);

export default SolidaryLiabilitySection;
