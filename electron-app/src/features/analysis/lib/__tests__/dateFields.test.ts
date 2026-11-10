import { dateFieldError, datesSectionError, displayDate, editDateSlots, storedDate } from '../dateFields';
import { isValidDateStr } from '../../../../shared/lib/dates';

it.each(['29.02.2024', '29.02.2000', '31.12.9999', '01.01.0001', '15.03.2222'])(
  'принимает существующую дату %s', value => expect(isValidDateStr(value)).toBe(true),
);
it.each(['33.13.2222', '31.04.2026', '29.02.2025', '29.02.1900', '00.01.2026', '10.00.2026', '01.01.0000', '1.01.2026'])(
  'отклоняет неверную дату %s', value => expect(isValidDateStr(value)).toBe(false),
);
it('ISO и однозначные день/месяц отображаются привычно, в модель уходят ISO или текстовый срок', () => {
  expect(displayDate('2026-04-10')).toBe('10.04.2026');
  expect(displayDate('1.2.2026')).toBe('01.02.2026');
  expect(displayDate('2026-04-10T14:35', true)).toBe('10.04.2026 14:35');
  expect(storedDate('10.04.2026')).toBe('2026-04-10');
  expect(storedDate('10.04.2026 14:35', true)).toBe('2026-04-10T14:35');
  expect(storedDate('10.04.2026', false, true)).toBe('10.04.2026');
});
it('удаляет и заменяет день без сдвига месяца и года', () => {
  expect(editDateSlots('25.04.2026', 0, 2, '10')).toEqual({ value: '10.04.2026', caret: 3 });
  expect(editDateSlots('25.04.2026', 2, 2, '', false, 'backward')).toEqual({ value: '2_.04.2026', caret: 1 });
  expect(editDateSlots('25.04.2026', 0, 2, '')).toEqual({ value: '__.04.2026', caret: 0 });
  expect(editDateSlots('25.04.2026', 0, 10, '')).toEqual({ value: '', caret: 0 });
});
it('проверяет время, частично введённую дату, текстовые сроки и скрытые поля ипотеки', () => {
  expect(dateFieldError('10.04.2026 23:59', true)).toBe('');
  expect(dateFieldError('10.04.2026 24:00', true)).not.toBe('');
  expect(dateFieldError('10.04.2026 12:60', true)).not.toBe('');
  expect(dateFieldError('10.04.20__')).not.toBe('');
  expect(datesSectionError({ objectionsDeadline18: 'в течение 30 дней' }, 'bankruptcy')).toBe(false);
  expect(datesSectionError({ objectionsDeadline18: '33.13.2222' }, 'bankruptcy')).toBe(true);
  expect(datesSectionError({ considerationDeadline19: '33.13.2222' }, 'mortgage')).toBe(false);
  expect(datesSectionError({ noticeDate: '33.13.2222' }, 'mortgage')).toBe(true);
});
