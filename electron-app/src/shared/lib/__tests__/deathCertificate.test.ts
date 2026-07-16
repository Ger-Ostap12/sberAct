import { isValidDeathCertificate, maskDeathCertificate } from '../deathCertificate';

describe('isValidDeathCertificate', () => {
  it('пустое значение валидно (поле необязательное)', () => {
    expect(isValidDeathCertificate('')).toBe(true);
    expect(isValidDeathCertificate(undefined)).toBe(true);
    expect(isValidDeathCertificate('   ')).toBe(true);
  });

  it('принимает канонический вид из бланка', () => {
    expect(isValidDeathCertificate('II-МЮ № 123456')).toBe(true);
    expect(isValidDeathCertificate('IV-АН № 654321')).toBe(true);
    expect(isValidDeathCertificate('XIV-ЖД № 000001')).toBe(true);
  });

  it('разделители необязательны — сверяем состав, а не пунктуацию', () => {
    expect(isValidDeathCertificate('II-МЮ-123456')).toBe(true);
    expect(isValidDeathCertificate('II МЮ 123456')).toBe(true);
    expect(isValidDeathCertificate('IIМЮ123456')).toBe(true);
    expect(isValidDeathCertificate('  ii-мю № 123456  ')).toBe(true); // регистр не важен
  });

  it('принимает кириллические двойники в римской серии (русская раскладка)', () => {
    expect(isValidDeathCertificate('ХI-МЮ № 123456')).toBe(true);  // Х кириллическая
    expect(isValidDeathCertificate('ИИ-МЮ № 123456')).toBe(true);  // И вместо I
  });

  it('отвергает нарушенный состав', () => {
    expect(isValidDeathCertificate('II-МЮ № 12345')).toBe(false);   // пять цифр
    expect(isValidDeathCertificate('II-МЮ № 1234567')).toBe(false); // семь цифр
    expect(isValidDeathCertificate('II-М № 123456')).toBe(false);   // одна буква серии
    expect(isValidDeathCertificate('II-МЮЯ № 123456')).toBe(false); // три буквы серии
    expect(isValidDeathCertificate('II-MU № 123456')).toBe(false);  // латиница вместо русских букв
    expect(isValidDeathCertificate('-МЮ № 123456')).toBe(false);    // нет римской серии
    expect(isValidDeathCertificate('123456')).toBe(false);
    expect(isValidDeathCertificate('мусор')).toBe(false);
  });

  it('отвергает бессмысленные римские наборы', () => {
    expect(isValidDeathCertificate('IIII-МЮ № 123456')).toBe(false);
    expect(isValidDeathCertificate('VV-МЮ № 123456')).toBe(false);
  });
});

describe('maskDeathCertificate', () => {
  it('расставляет дефис и «№» при вводе без разделителей', () => {
    // Реальный ввод пользователя: буквы и цифры подряд.
    expect(maskDeathCertificate('XXМО123445')).toBe('XX-МО № 123445');
    expect(maskDeathCertificate('IIМЮ123456')).toBe('II-МЮ № 123456');
  });

  it('серия — две последние буквы перед цифрами, даже если похожи на римские', () => {
    // «М» годится и в римскую цифру, и в серию — развязка позиционная.
    expect(maskDeathCertificate('XIМД123456')).toBe('XI-МД № 123456');
  });

  it('приводит к верхнему регистру и чистит недопустимые символы', () => {
    expect(maskDeathCertificate('ii-мю № 123456')).toBe('II-МЮ № 123456');
    expect(maskDeathCertificate('II-МЮ № 123456!@#')).toBe('II-МЮ № 123456');
    expect(maskDeathCertificate('II_МЮ/123456')).toBe('II-МЮ № 123456');
  });

  it('уважает дефис, введённый пользователем, пока цифр ещё нет', () => {
    expect(maskDeathCertificate('II')).toBe('II');
    expect(maskDeathCertificate('II-')).toBe('II-');
    expect(maskDeathCertificate('II-М')).toBe('II-М');
    expect(maskDeathCertificate('II-МЮ')).toBe('II-МЮ');
    expect(maskDeathCertificate('II-МЮ1')).toBe('II-МЮ № 1');
  });

  it('пока цифр нет и дефиса нет — буквы не режем: границу серии знать неоткуда', () => {
    expect(maskDeathCertificate('XXМО')).toBe('XXМО');
  });

  it('обрезает номер до шести цифр', () => {
    expect(maskDeathCertificate('XXМО12344599')).toBe('XX-МО № 123445');
  });

  it('результат маски проходит валидацию', () => {
    expect(isValidDeathCertificate(maskDeathCertificate('XXМО123445'))).toBe(true);
  });
});
