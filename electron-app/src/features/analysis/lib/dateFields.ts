import { fromInputDate, isValidDateStr, toInputDate } from '../../../shared/lib/dates';

export const dateTemplate = (withTime = false) => withTime ? '__.__.____ __:__' : '__.__.____';
export const dateSlots = (withTime = false) => [...dateTemplate(withTime)]
  .map((char, index) => char === '_' ? index : -1).filter(index => index >= 0);
export const isTextDeadline = (value: string) => /[a-zа-яё]/i.test(value);

export const displayDate = (value: string, withTime = false): string => {
  const iso = value.match(/^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?$/);
  if (iso) return fromInputDate(iso[1]) + (withTime && iso[2] ? ` ${iso[2]}` : '');
  const date = value.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})(.*)$/);
  if (date) return `${date[1].padStart(2, '0')}.${date[2].padStart(2, '0')}.${date[3]}${date[4]}`;
  return value;
};

export const dateFieldError = (value: string, withTime = false, allowText = false): string => {
  if (!value.trim()) return '';
  if (allowText && isTextDeadline(value)) return '';
  const display = displayDate(value.trim(), withTime);
  const match = display.match(withTime ? /^(\d{2}\.\d{2}\.\d{4}) (\d{2}):(\d{2})$/ : /^(\d{2}\.\d{2}\.\d{4})$/);
  if (!match || !isValidDateStr(match[1])) return 'Введите существующую дату в формате ДД.ММ.ГГГГ' + (withTime ? ' ЧЧ:ММ' : '');
  if (withTime && (Number(match[2]) > 23 || Number(match[3]) > 59)) return 'Время должно быть от 00:00 до 23:59';
  return '';
};

export const storedDate = (display: string, withTime = false, allowText = false): string => {
  if (!display || allowText || dateFieldError(display, withTime, allowText)) return display;
  return toInputDate(display.slice(0, 10)) + (withTime ? `T${display.slice(11)}` : '');
};

// Замена цифр в фиксированных позициях; удаление никогда не сдвигает соседние части.
export const editDateSlots = (value: string, start: number, end: number, digits: string, withTime = false,
  deletion?: 'backward' | 'forward'): { value: string; caret: number } => {
  const template = dateTemplate(withTime);
  const slots = dateSlots(withTime);
  const chars = [...template].map((char, index) => char === '_' && /\d/.test(value[index] || '') ? value[index] : char);
  if (start < end) slots.filter(index => index >= start && index < end).forEach(index => { chars[index] = '_'; });
  if (deletion && start === end) {
    const index = deletion === 'backward' ? [...slots].reverse().find(index => index < start) : slots.find(index => index >= start);
    if (index !== undefined) { chars[index] = '_'; start = index; }
  }
  let caret = start;
  for (const digit of digits.replace(/\D/g, '')) {
    const index = slots.find(index => index >= caret);
    if (index === undefined) break;
    chars[index] = digit;
    caret = slots.find(next => next > index) ?? template.length;
  }
  return { value: chars.some(char => /\d/.test(char)) ? chars.join('') : '', caret };
};

export const datesSectionError = (fields: Record<string, string>, mode: 'bankruptcy' | 'mortgage') => {
  const dates = ['date', 'courtSubmissionDate24', 'applicationReceiptDate23', ...(mode === 'mortgage' ? ['noticeDate'] : [])];
  const deadlines = ['objectionsDeadline18', ...(mode === 'bankruptcy' ? ['considerationDeadline19', 'withoutMovementDeadline20'] : [])];
  return dates.some(field => !!dateFieldError(fields[field] || ''))
    || !!dateFieldError(fields.courtHearingDateTime99 || '', true)
    || deadlines.some(field => !!dateFieldError(fields[field] || '', false, true));
};
