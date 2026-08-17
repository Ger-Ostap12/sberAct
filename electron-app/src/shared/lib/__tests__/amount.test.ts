import { parseAmount, formatAmount, editableAmount } from '../amount';

describe('parseAmount', () => {
  it('принимает пробелы, запятую, точку → канон', () => {
    expect(parseAmount('123 456,78')).toBe('123456.78');
    expect(parseAmount('123456.78')).toBe('123456.78');
    expect(parseAmount('1 234 567')).toBe('1234567');
    expect(parseAmount('123 123,123')).toBe('123123.123');
  });
  it('чистит мусор и лишние точки', () => {
    expect(parseAmount('1a2b3')).toBe('123');
    expect(parseAmount('1.2.3')).toBe('1.23');
    expect(parseAmount('')).toBe('');
  });
});

describe('formatAmount', () => {
  it('группирует разряды и ставит запятую', () => {
    expect(formatAmount('123456.78')).toBe('123 456,78');
    expect(formatAmount('1234567')).toBe('1 234 567');
    expect(formatAmount('123 123,123')).toBe('123 123,123');
    expect(formatAmount('786.17')).toBe('786,17');
  });
  it('пустое/хвостовая точка', () => {
    expect(formatAmount('')).toBe('');
    expect(formatAmount('123.')).toBe('123');
  });
});

describe('editableAmount', () => {
  it('канон с запятой без группировки', () => {
    expect(editableAmount('123456.78')).toBe('123456,78');
    expect(editableAmount('123 456,78')).toBe('123456,78');
  });
});
