import { matchBankKey } from '../banks';
import { Bank } from '../../constants/banks';

// Фикстура в форме ответа /banks (подмножество единого реестра).
const BANKS: Bank[] = [
  { display: 'Сбербанк', inn: '7707083893', ogrn: '1027700132195', address: 'г. Москва', aliases: ['пао сбербанк', 'сбербанк', 'сбер банк', 'сбер'] },
  { display: 'ВТБ', inn: '7702070139', ogrn: '1027739609391', address: 'г. СПб', aliases: ['втб', 'пао втб', 'втб банк', 'банк втб'] },
  { display: 'Т-Банк', inn: '7710140679', ogrn: '1027700130275', address: 'г. Москва', aliases: ['тинькофф', 'тинькофф банк', 'т-банк', 'т банк', 'тбанк'] },
  { display: 'Промсвязьбанк (ПСБ)', inn: '7744000912', ogrn: '1027739019142', address: 'г. Ярославль', aliases: ['псб', 'промсвязьбанк', 'промсвязь'] },
];

describe('matchBankKey', () => {
  it('точное совпадение по display', () => {
    expect(matchBankKey('Сбербанк', BANKS)).toBe('Сбербанк');
    expect(matchBankKey('ВТБ', BANKS)).toBe('ВТБ');
  });

  it('распознаёт по алиасам (регистр игнорируется)', () => {
    expect(matchBankKey('ПАО Сбербанк', BANKS)).toBe('Сбербанк');
    expect(matchBankKey('СБЕРБАНК РОССИИ', BANKS)).toBe('Сбербанк');
    expect(matchBankKey('Банк ВТБ (ПАО)', BANKS)).toBe('ВТБ');
    expect(matchBankKey('АО «Тинькофф Банк»', BANKS)).toBe('Т-Банк');
    expect(matchBankKey('Промсвязьбанк', BANKS)).toBe('Промсвязьбанк (ПСБ)');
  });

  it('вариант «сбер банк» с пробелом', () => {
    expect(matchBankKey('Сбер банк', BANKS)).toBe('Сбербанк');
  });

  it('null на неизвестном банке', () => {
    expect(matchBankKey('Неизвестный Банк', BANKS)).toBeNull();
  });

  it('null на пустом/undefined входе', () => {
    expect(matchBankKey('', BANKS)).toBeNull();
    expect(matchBankKey(undefined, BANKS)).toBeNull();
  });

  it('null на пустом реестре (бэкенд недоступен)', () => {
    expect(matchBankKey('ПАО Сбербанк', [])).toBeNull();
  });

  it('приоритет — первый банк в списке, чей алиас совпал', () => {
    // «сбер» стоит раньше «втб»: строка с обоими → Сбербанк
    expect(matchBankKey('Сбербанк и ВТБ', BANKS)).toBe('Сбербанк');
  });
});
