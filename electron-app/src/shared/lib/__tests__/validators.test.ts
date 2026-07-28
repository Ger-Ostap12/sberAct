import {
  isValidEmail,
  isValidUrl,
  isValidPassportSeries,
  isValidPassportNumber,
  isValidCaseNumber,
  isValidFio,
  digitsOnly,
} from '../validators';

describe('validators — пустая строка валидна', () => {
  it('все валидаторы принимают пустое/undefined', () => {
    expect(isValidEmail('')).toBe(true);
    expect(isValidEmail(undefined)).toBe(true);
    expect(isValidUrl('')).toBe(true);
    expect(isValidPassportSeries('')).toBe(true);
    expect(isValidPassportNumber(undefined)).toBe(true);
  });
});

describe('isValidEmail', () => {
  it('валидные', () => {
    expect(isValidEmail('voroshilovsky.ros@sudrf.ru')).toBe(true);
    expect(isValidEmail('a@b.co')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidEmail('нет-собаки.ru')).toBe(false);
    expect(isValidEmail('a@b')).toBe(false);
    expect(isValidEmail('a @b.ru')).toBe(false);
  });
});

describe('isValidUrl', () => {
  it('валидные http(s)', () => {
    expect(isValidUrl('https://voroshilovsky--ros.sudrf.ru/')).toBe(true);
    expect(isValidUrl('http://example.com')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidUrl('voroshilovsky--ros.sudrf.ru')).toBe(false);
    expect(isValidUrl('ftp://x.ru')).toBe(false);
    expect(isValidUrl('просто текст')).toBe(false);
  });
});

describe('паспорт', () => {
  it('серия — ровно 4 цифры', () => {
    expect(isValidPassportSeries('6018')).toBe(true);
    expect(isValidPassportSeries('601')).toBe(false);
    expect(isValidPassportSeries('60188')).toBe(false);
    expect(isValidPassportSeries('60a8')).toBe(false);
  });
  it('номер — ровно 6 цифр', () => {
    expect(isValidPassportNumber('123456')).toBe(true);
    expect(isValidPassportNumber('12345')).toBe(false);
    expect(isValidPassportNumber('1234567')).toBe(false);
    expect(isValidPassportNumber('12 45 6')).toBe(false);
  });
});

describe('isValidCaseNumber', () => {
  it('валидный формат 2-<номер>/<год>', () => {
    expect(isValidCaseNumber('2-1223/2026')).toBe(true);
    expect(isValidCaseNumber('2-1/2025')).toBe(true);
    expect(isValidCaseNumber('')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidCaseNumber('А40-1223/2026')).toBe(false);
    expect(isValidCaseNumber('2-1223-2026')).toBe(false);
    expect(isValidCaseNumber('3-1223/2026')).toBe(false);
    expect(isValidCaseNumber('2-1223/26')).toBe(false);
  });
});

describe('isValidFio', () => {
  it('полное ФИО и краткое Фамилия И.О.', () => {
    expect(isValidFio('Иванов Иван Иванович')).toBe(true);
    expect(isValidFio('Иванов И.О.')).toBe(true);
    expect(isValidFio('Иванов И. О.')).toBe(true);
    expect(isValidFio('Римский-Корсаков Николай Андреевич')).toBe(true);
    expect(isValidFio('')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidFio('иванов иван иванович')).toBe(false); // без заглавных
    expect(isValidFio('Иванов')).toBe(false); // одно слово
    expect(isValidFio('Иванов Иван')).toBe(false); // два слова
    expect(isValidFio('Ivanov Ivan Ivanovich')).toBe(false); // латиница
  });
});

describe('digitsOnly', () => {
  it('оставляет только цифры и режет до max', () => {
    expect(digitsOnly('60a18b', 4)).toBe('6018');
    expect(digitsOnly('12 34 56 78', 6)).toBe('123456');
    expect(digitsOnly('abc', 4)).toBe('');
  });
});
