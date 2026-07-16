import { toInputDate, fromInputDate, maskDate, isValidDateStr } from '../dates';

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

describe('maskDate', () => {
  it('расставляет точки по мере ввода цифр', () => {
    expect(maskDate('2')).toBe('2');
    expect(maskDate('2504')).toBe('25.04');
    expect(maskDate('25042024')).toBe('25.04.2024');
  });

  it('выбрасывает нецифры и лишние цифры сверх восьми', () => {
    expect(maskDate('25a04/2024')).toBe('25.04.2024');
    expect(maskDate('250420249999')).toBe('25.04.2024');
  });
});

describe('isValidDateStr', () => {
  it('пустое значение валидно (поле необязательное)', () => {
    expect(isValidDateStr('')).toBe(true);
    expect(isValidDateStr(undefined)).toBe(true);
  });

  it('принимает существующие даты, включая високосное 29 февраля', () => {
    expect(isValidDateStr('25.04.2024')).toBe(true);
    expect(isValidDateStr('29.02.2024')).toBe(true);
  });

  it('отвергает несуществующие даты и неполный ввод', () => {
    expect(isValidDateStr('31.02.2025')).toBe(false);  // Date молча перенёс бы на 3 марта
    expect(isValidDateStr('29.02.2025')).toBe(false);  // 2025 не високосный
    expect(isValidDateStr('00.01.2025')).toBe(false);
    expect(isValidDateStr('25.13.2025')).toBe(false);
    expect(isValidDateStr('25.04')).toBe(false);
  });
});
