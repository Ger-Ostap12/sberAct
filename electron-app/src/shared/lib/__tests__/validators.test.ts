import {
  isValidEmail,
  isValidUrl,
  isValidPassportSeries,
  isValidPassportNumber,
  isValidCaseNumber,
  isValidFio,
  digitsOnly,
  isValidCadastralNumber,
  isValidEgrnRecord,
  isValidMoney,
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

describe('isValidCadastralNumber', () => {
  it('валидный кадастровый номер', () => {
    expect(isValidCadastralNumber('23:50:7228765:0587')).toBe(true);
    expect(isValidCadastralNumber('23:69:9464362:1223')).toBe(true);
    expect(isValidCadastralNumber('')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidCadastralNumber('23:50:7228765')).toBe(false); // мало групп
    expect(isValidCadastralNumber('23-68-09/699/4620-144')).toBe(false); // это ЕГРН
    expect(isValidCadastralNumber('просто текст')).toBe(false);
  });
});

describe('isValidEgrnRecord', () => {
  it('одиночная запись и долевая (несколько с долями)', () => {
    expect(isValidEgrnRecord('23:26:5876727:9651-59/678/6420-2')).toBe(true);
    expect(isValidEgrnRecord('23-68-09/699/4620-144')).toBe(true);
    expect(isValidEgrnRecord('2/4 23:47:0250041:668-03/389/9020-2; 1/4 23:39:9163758:507-82/301/8620-2')).toBe(true);
    expect(isValidEgrnRecord('')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidEgrnRecord('abc')).toBe(false); // нет разделителей/коротко
    expect(isValidEgrnRecord('12345')).toBe(false);
  });
});

describe('isValidMoney', () => {
  it('только число (пробелы-разряды и «,»/«.» ок)', () => {
    expect(isValidMoney('4069525')).toBe(true);
    expect(isValidMoney('3662572,50')).toBe(true);
    expect(isValidMoney('6 307 002,10')).toBe(true);
    expect(isValidMoney('9010003.00')).toBe(true);
    expect(isValidMoney('')).toBe(true);
  });
  it('невалидные', () => {
    expect(isValidMoney('4069525 руб')).toBe(false);
    expect(isValidMoney('сто рублей')).toBe(false);
    expect(isValidMoney('12,345')).toBe(false); // 3 знака после запятой
  });
});
