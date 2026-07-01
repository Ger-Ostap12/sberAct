import React from 'react';
import { TextField } from '@mui/material';
import LabeledField from './LabeledField';

interface LabeledTextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Многострочное поле (textarea). */
  multiline?: boolean;
  rows?: number;
  type?: string;
}

/**
 * Поле ввода с меткой поверх границы — самый частый паттерн формы анализа.
 * Соответствует связке `LabeledField + TextField(fullWidth, size="small", margin="dense")`,
 * которая в исходнике повторялась десятки раз.
 */
const LabeledTextField: React.FC<LabeledTextFieldProps> = ({
  label,
  value,
  onChange,
  placeholder,
  multiline,
  rows,
  type,
}) => (
  <LabeledField label={label}>
    <TextField
      fullWidth
      value={value}
      onChange={(e) => onChange(e.target.value)}
      size="small"
      margin="dense"
      placeholder={placeholder}
      multiline={multiline}
      rows={rows}
      type={type}
    />
  </LabeledField>
);

export default LabeledTextField;
