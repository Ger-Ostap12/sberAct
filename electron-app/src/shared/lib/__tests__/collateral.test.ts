import { extractCollateralData } from '../collateral';

describe('extractCollateralData — адрес', () => {
  it('извлекает адрес по метке «по адресу» с индексом', () => {
    const desc = 'Квартира, расположенная по адресу: 344000, г. Ростов-на-Дону, ул. Ленина, д. 1';
    const r = extractCollateralData(desc);
    expect(r.address).toContain('344000');
    expect(r.address).toContain('Ростов');
  });

  it('извлекает адрес по индексу без метки', () => {
    const desc = 'Объект 190000, г. Санкт-Петербург, Невский проспект, д. 10';
    const r = extractCollateralData(desc);
    expect(r.address).toContain('190000');
  });

  it('не выдаёт адрес, если ни индекса, ни адресных слов нет', () => {
    const r = extractCollateralData('Просто какое-то имущество без адреса');
    expect(r.address).toBeUndefined();
  });
});

describe('extractCollateralData — кадастровый номер', () => {
  it('извлекает кадастр формата XX:XX:XXXXXX:XX', () => {
    const r = extractCollateralData('Земельный участок, кадастровый номер 61:44:0010203:15');
    expect(r.cadastralNumber).toBe('61:44:0010203:15');
  });

  it('извлекает кадастр без метки по формату с двоеточиями', () => {
    const r = extractCollateralData('Помещение 50:21:0080105:123 площадью 100 кв.м');
    expect(r.cadastralNumber).toBe('50:21:0080105:123');
  });

  it('нет кадастра — поле отсутствует', () => {
    const r = extractCollateralData('Автомобиль Toyota Camry 2020 г.в.');
    expect(r.cadastralNumber).toBeUndefined();
  });
});

describe('extractCollateralData — граничные случаи', () => {
  it('пустое описание → пустой объект', () => {
    expect(extractCollateralData('')).toEqual({});
  });

  it('извлекает и адрес, и кадастр из одного описания', () => {
    const desc =
      'Квартира по адресу: 344000, г. Ростов-на-Дону, ул. Мира, д. 5, кадастровый номер 61:44:0011122:77';
    const r = extractCollateralData(desc);
    expect(r.address).toContain('344000');
    expect(r.cadastralNumber).toBe('61:44:0011122:77');
  });
});
