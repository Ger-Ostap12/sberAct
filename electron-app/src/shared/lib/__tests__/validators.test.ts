import {
  isValidEmail,
  isValidUrl,
  isValidPassportSeries,
  isValidPassportNumber,
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
