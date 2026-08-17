// Блок «Солидарное» (режим «Ипотека»): взыскание с ответчиков солидарно.
// Влияет на то, какой акт генерировать, — вместе с наличием представителей
// истца и ответчика. Заполняется юристом вручную, из анализа не выводится.
import React from 'react';
import { Box, Typography, FormControlLabel, Checkbox } from '@mui/material';
import { BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface SolidaryLiabilitySectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const SolidaryLiabilitySection: React.FC<SolidaryLiabilitySectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 1, color: 'primary.main' }}>
      Солидарность
    </Typography>
    <FormControlLabel
      sx={{ pl: 1 }}
      control={
        <Checkbox
          size="small"
          checked={editedFields.solidaryLiability === 'true'}
          // Снятую галочку шлём пустой строкой, а не 'false': бэкенд считает
          // пустое поле незаполненным, и строка 'false' была бы «заполнено».
          onChange={(e) => onFieldChange('solidaryLiability', e.target.checked ? 'true' : '')}
        />
      }
      label="Солидарное"
    />
  </Box>
);

export default SolidaryLiabilitySection;
