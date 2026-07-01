import React from 'react';
import { Box, Typography } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX } from '../styles/formStyles';

interface LabeledFieldProps {
  /** Текст метки (обычно с двоеточием, как в макете). */
  label: string;
  children: React.ReactNode;
}

/**
 * Обёртка «метка, наложенная на границу поля». Внутрь кладётся любой контрол
 * (TextField, Select, FormControl). Заменяет 30+ повторов паттерна
 * `<Box sx={LABEL_OVERLAP_BOX}><Typography sx={LABEL_OVERLAP_SX}>…</Typography>…</Box>`
 * из DocumentAnalysis.
 */
const LabeledField: React.FC<LabeledFieldProps> = ({ label, children }) => (
  <Box sx={LABEL_OVERLAP_BOX}>
    <Typography variant="body2" sx={LABEL_OVERLAP_SX}>
      {label}
    </Typography>
    {children}
  </Box>
);

export default LabeledField;
