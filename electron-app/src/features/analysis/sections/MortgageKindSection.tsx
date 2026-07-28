// Блок «Вид ипотеки» (режим «Ипотека»): гражданская ипотека (всё как обычно) или
// военная ипотека (меняется блок «Финансовые данные» на поля по ЦЖЗ).
import React from 'react';
import { Box, Typography, RadioGroup, FormControlLabel, Radio } from '@mui/material';
import { MortgageKind } from '../../../types';
import { BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface MortgageKindSectionProps {
  mortgageKind: MortgageKind;
  onChange: (value: MortgageKind) => void;
}

const MortgageKindSection: React.FC<MortgageKindSectionProps> = ({ mortgageKind, onChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 1, color: 'primary.main' }}>
      Вид ипотеки
    </Typography>
    <RadioGroup
      row
      value={mortgageKind}
      onChange={(e) => onChange(e.target.value as MortgageKind)}
      sx={{ pl: 1 }}
    >
      <FormControlLabel value="civil" control={<Radio size="small" />} label="Ипотека" />
      <FormControlLabel value="military" control={<Radio size="small" />} label="Военная ипотека" />
      <FormControlLabel value="ddu" control={<Radio size="small" />} label="ДДУ" />
    </RadioGroup>
  </Box>
);

export default MortgageKindSection;
