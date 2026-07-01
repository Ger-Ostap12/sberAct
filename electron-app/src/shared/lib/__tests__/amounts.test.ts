import { formatAmount, parseAmount } from '../amounts';

// Нормализует любые пробельные разделители групп к обычному пробелу — как это
// делает сама formatAmount (Intl может использовать неразрывный пробел).
const norm = (s: string) => s.replace(/\s/g, ' ');

describe('formatAmount', () => {
  it('форматирует число с разделением тысяч и 2 знаками', () => {
    expect(norm(formatAmount(1000000))).toBe('1 000 000,00');
    expect(norm(formatAmount(1234.5))).toBe('1 234,50');
    expect(norm(formatAmount(0.99))).toBe('0,99');
  });

  it('принимает строковый вход с мусором и запятой-разделителем', () => {
    expect(norm(formatAmount('1234,56'))).toBe('1 234,56');
    expect(norm(formatAmount('1234.56'))).toBe('1 234,56');
    expect(norm(formatAmount('1 234,56 руб.'))).toBe('1 234,56');
  });

  it('пустой/нулевой/undefined → пустая строка', () => {
    expect(formatAmount('')).toBe('');
    expect(formatAmount(0)).toBe('');
    expect(formatAmount(undefined)).toBe('');
  });

  it('нечисловая строка возвращается как есть', () => {
    expect(formatAmount('abc')).toBe('abc');
  });
});

describe('parseAmount', () => {
  it('оставляет только цифры/точку/запятую и приводит запятую к точке', () => {
    expect(parseAmount('1234.56')).toBe('1234.56');
    expect(parseAmount('100000')).toBe('100000');
    expect(parseAmount('1 234,56')).toBe('1234.56');
  });

  it('QUIRK: точка из «руб.» сохраняется (regex не режет точки-разделители)', () => {
    // Характеризация текущего поведения: суффикс «руб.» оставляет хвостовую точку.
    expect(parseAmount('1 234,56 руб.')).toBe('1234.56.');
  });

  it('пустая строка → пустая строка', () => {
    expect(parseAmount('')).toBe('');
  });

  it('только первый разделитель важен (несколько запятых)', () => {
    // Поведение перенесено 1:1: replace(',', '.') меняет только первую запятую.
    expect(parseAmount('1,2,3')).toBe('1.2,3');
  });
});
