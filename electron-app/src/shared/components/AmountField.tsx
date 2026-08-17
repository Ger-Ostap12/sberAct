import React from 'react';
import { TextField, TextFieldProps } from '@mui/material';
import { formatAmount, editableAmount, parseAmount } from '../lib/amount';

interface AmountFieldProps extends Omit<TextFieldProps, 'value' | 'onChange'> {
  /** Хранимое каноничное значение суммы (напр. «123456.78»). */
  value: string;
  /** Возвращает канон при правке (парсит ввод: пробелы/запятая/точка). */
  onValueChange: (canonical: string) => void;
}

/**
 * Денежное поле с форматированием ПО BLUR. При фокусе — редактируемый вид
 * («123456,78»), при потере фокуса — красивый («123 456,78»). Принимает запятую
 * и точку как десятичный разделитель.
 *
 * ⚠️ forwardRef + композиция onFocus/onBlur/onChange: поле вкладывается внутрь
 * BreakdownTip (Tooltip) и FieldQualityMark (cloneElement с ref/обработчиками) —
 * поэтому свои обработчики ВЫЗЫВАЕМ вместе с пришедшими, а не вместо них
 * (иначе тултип/подсветка молча ломаются — см. FieldQualityMark).
 */
const AmountField = React.forwardRef<HTMLDivElement, AmountFieldProps>(
  ({ value, onValueChange, onFocus, onBlur, ...rest }, ref) => {
    const [draft, setDraft] = React.useState<string | null>(null);
    const display = draft !== null ? draft : formatAmount(value);
    return (
      <TextField
        {...rest}
        ref={ref}
        value={display}
        onFocus={(e) => {
          setDraft(editableAmount(value));
          onFocus?.(e);
        }}
        onChange={(e) => {
          const text = e.target.value;
          setDraft(text);
          onValueChange(parseAmount(text));
        }}
        onBlur={(e) => {
          setDraft(null);
          onBlur?.(e);
        }}
      />
    );
  },
);

AmountField.displayName = 'AmountField';

export default AmountField;
