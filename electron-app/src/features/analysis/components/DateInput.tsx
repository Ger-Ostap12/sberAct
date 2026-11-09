import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { IconButton, InputAdornment, TextField, Tooltip } from '@mui/material';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import { toInputDate } from '../../../shared/lib/dates';
import { dateFieldError, dateTemplate, displayDate, editDateSlots, isTextDeadline, storedDate } from '../lib/dateFields';

interface Props {
  value: string;
  onChange: (value: string) => void;
  label: string;
  withTime?: boolean;
  allowText?: boolean;
  calendarLabel?: string;
  delay?: number;
}

const DateInput: React.FC<Props> = ({ value, onChange, label, withTime = false, allowText = false, calendarLabel, delay = 300 }) => {
  const [draft, setDraft] = useState(() => displayDate(value, withTime));
  const [touched, setTouched] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const lastSent = useRef(value);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (pending.current) clearTimeout(pending.current); }, []);
  const caret = useRef<number | null>(null);
  useEffect(() => {
    if (value !== lastSent.current) {
      if (pending.current) clearTimeout(pending.current);
      pending.current = null;
      lastSent.current = value;
      setDraft(displayDate(value, withTime));
      setTouched(false);
    }
  }, [value, withTime]);
  useLayoutEffect(() => {
    if (caret.current !== null) {
      input.current?.setSelectionRange(caret.current, caret.current);
      caret.current = null;
    }
  });
  const change = (text: string, position?: number, immediate = false) => {
    caret.current = position ?? null;
    if (position !== undefined) input.current?.setSelectionRange(position, position);
    setDraft(text);
    const next = storedDate(text, withTime, allowText);
    lastSent.current = next;
    if (pending.current) clearTimeout(pending.current);
    pending.current = null;
    if (delay && !immediate) pending.current = setTimeout(() => {
      pending.current = null;
      onChange(next);
    }, delay);
    else onChange(next);
  };
  const edit = (digits: string, deletion?: 'backward' | 'forward') => {
    const node = input.current;
    const result = editDateSlots(draft, node?.selectionStart || 0, node?.selectionEnd || 0, digits, withTime, deletion);
    change(result.value, result.caret);
  };
  const error = dateFieldError(draft, withTime, allowText);
  const showError = !!error && (touched || !draft.includes('_'));
  const calendarTitle = calendarLabel || `Выбрать дату в календаре: ${label}`;
  const iso = withTime ? storedDate(draft, true) : toInputDate(draft);
  return (
    <TextField fullWidth size="small" margin="dense" type="text" inputRef={input}
      value={draft} placeholder={allowText ? 'ДД.ММ.ГГГГ или текст' : withTime ? 'ДД.ММ.ГГГГ ЧЧ:ММ' : 'ДД.ММ.ГГГГ'}
      error={showError} helperText={showError ? error : undefined}
      inputProps={{ 'aria-label': label, inputMode: allowText ? 'text' : 'numeric', autoComplete: 'off' }}
      onClick={() => { if (draft === dateTemplate(withTime)) input.current?.setSelectionRange(0, 0); }}
      onFocus={() => { if (!draft) { setDraft(dateTemplate(withTime)); caret.current = 0; } }}
      onBlur={() => {
        setTouched(true);
        const next = draft === dateTemplate(withTime) ? '' : draft;
        if (pending.current || next !== draft || storedDate(next, withTime, allowText) !== value) change(next, undefined, true);
      }}
      onKeyDown={event => {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (allowText && isTextDeadline(draft)) return;
        if (allowText && /^[a-zа-яё]$/i.test(event.key) && (!/\d/.test(draft)
          || (input.current?.selectionStart === 0 && input.current?.selectionEnd === draft.length))) {
          event.preventDefault(); change(event.key); return;
        }
        if (/^\d$/.test(event.key)) { event.preventDefault(); edit(event.key); }
        else if (event.key === 'Backspace' || event.key === 'Delete') {
          event.preventDefault(); edit('', event.key === 'Backspace' ? 'backward' : 'forward');
        } else if (['.', '/', '-', ':', ' '].includes(event.key)) {
          event.preventDefault();
          const position = input.current?.selectionStart || 0;
          if (position > 0 && /[. :]/.test(draft[position - 1])) return;
          const next = [...dateTemplate(withTime)].findIndex((char, index) => index >= position && /[. :]/.test(char));
          if (next >= 0) input.current?.setSelectionRange(next + 1, next + 1);
        } else if (event.key.length === 1 && !allowText) event.preventDefault();
      }}
      onChange={event => {
        const raw = event.target.value;
        if (allowText && isTextDeadline(raw)) { change(raw.replace(/_/g, '')); return; }
        const normalized = displayDate(raw, withTime);
        if (normalized !== raw || /[._: -]/.test(raw)) { change(normalized); return; }
        const template = dateTemplate(withTime);
        let index = 0;
        change([...template].map(char => char === '_' ? (raw.replace(/\D/g, '')[index++] || '_') : char).join(''));
      }}
      onPaste={event => {
        event.preventDefault();
        const raw = event.clipboardData.getData('text/plain').trim();
        if (allowText && isTextDeadline(raw)) { change(raw); return; }
        const normalized = displayDate(raw, withTime);
        if (/^\d{8}$/.test(raw) && !withTime) {
          change(`${raw.slice(0, 2)}.${raw.slice(2, 4)}.${raw.slice(4)}`); return;
        }
        if (normalized !== raw || /[.\/-]/.test(raw) || raw.length >= 8) { change(normalized); return; }
        if (/^\d+$/.test(raw)) edit(raw);
      }}
      onCut={event => {
        const node = input.current;
        if (!node || node.selectionStart === node.selectionEnd) return;
        event.preventDefault();
        event.clipboardData.setData('text/plain', draft.slice(node.selectionStart || 0, node.selectionEnd || 0));
        if (allowText && isTextDeadline(draft)) {
          change(draft.slice(0, node.selectionStart || 0) + draft.slice(node.selectionEnd || 0), node.selectionStart || 0);
        } else edit('');
      }}
      InputProps={{ endAdornment: <InputAdornment position="end">
        <Tooltip title={calendarTitle}>
          <IconButton size="small" edge="end" aria-label={calendarTitle} onClick={() => {
            const node = picker.current as (HTMLInputElement & { showPicker?: () => void }) | null;
            if (node?.showPicker) node.showPicker(); else node?.click();
          }}><CalendarTodayIcon fontSize="small" /></IconButton>
        </Tooltip>
        <input ref={picker} type={withTime ? 'datetime-local' : 'date'} aria-hidden="true" tabIndex={-1}
          data-calendar-for={label} value={error ? '' : iso} min={withTime ? '0001-01-01T00:00' : '0001-01-01'}
          max={withTime ? '9999-12-31T23:59' : '9999-12-31'}
          style={{ position: 'absolute', width: 0, height: 0, opacity: 0, pointerEvents: 'none' }}
          onChange={event => { if (!dateFieldError(event.target.value, withTime)) change(displayDate(event.target.value, withTime), undefined, true); }} />
      </InputAdornment> }}
    />
  );
};

export default DateInput;
