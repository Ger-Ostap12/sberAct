import { toInputDate, fromInputDate } from '../dates';

describe('toInputDate', () => {
  it('конвертирует ДД.ММ.ГГГГ → ГГГГ-ММ-ДД', () => {
    expect(toInputDate('01.02.2024')).toBe('2024-02-01');
    expect(toInputDate('31.12.1999')).toBe('1999-12-31');
  });

  it('добивает нулями одноцифровые день/месяц', () => {
    expect(toInputDate('1.2.2024')).toBe('2024-02-01');
    expect(toInputDate('9.9.2024')).toBe('2024-09-09');
  });

  it('принимает разделители точка, слэш и дефис', () => {
    expect(toInputDate('01/02/2024')).toBe('2024-02-01');
    expect(toInputDate('01-02-2024')).toBe('2024-02-01');
  });

  it('возвращает ISO-дату как есть', () => {
    expect(toInputDate('2024-02-01')).toBe('2024-02-01');
  });

  it('возвращает пустую строку на пустом/undefined входе', () => {
    expect(toInputDate('')).toBe('');
    expect(toInputDate(undefined)).toBe('');
  });

  it('возвращает пустую строку на нераспознанном формате', () => {
    expect(toInputDate('какая-то дата')).toBe('');
    expect(toInputDate('2024')).toBe('');
    expect(toInputDate('01.02.24')).toBe(''); // двузначный год не поддерживается
    expect(toInputDate('2024-02-1')).toBe(''); // невалидный ISO
  });
});

describe('fromInputDate', () => {
  it('конвертирует ГГГГ-ММ-ДД → ДД.ММ.ГГГГ', () => {
    expect(fromInputDate('2024-02-01')).toBe('01.02.2024');
    expect(fromInputDate('1999-12-31')).toBe('31.12.1999');
  });

  it('возвращает пустую строку на пустом входе', () => {
    expect(fromInputDate('')).toBe('');
  });

  it('возвращает вход как есть, если это не ISO-дата', () => {
    expect(fromInputDate('01.02.2024')).toBe('01.02.2024');
    expect(fromInputDate('мусор')).toBe('мусор');
  });
});

describe('toInputDate ↔ fromInputDate round-trip', () => {
  it('туда-обратно сохраняет исходную русскую дату', () => {
    const original = '15.06.2023';
    expect(fromInputDate(toInputDate(original))).toBe(original);
  });
});
