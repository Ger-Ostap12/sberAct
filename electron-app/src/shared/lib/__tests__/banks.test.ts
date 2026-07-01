import { matchBankKey } from '../banks';

describe('matchBankKey', () => {
  it('точное совпадение с ключом BANK_DATA', () => {
    expect(matchBankKey('Сбербанк')).toBe('Сбербанк');
    expect(matchBankKey('Газпромбанк')).toBe('Газпромбанк');
  });

  it('распознаёт банк по ключевым словам вне зависимости от регистра', () => {
    expect(matchBankKey('ПАО Сбербанк')).toBe('Сбербанк');
    expect(matchBankKey('СБЕРБАНК РОССИИ')).toBe('Сбербанк');
    expect(matchBankKey('Банк ВТБ (ПАО)')).toBe('ПАО ВТБ Банк');
    expect(matchBankKey('АО «Тинькофф Банк»')).toBe('Т-банк');
    expect(matchBankKey('АО «Альфа-Банк»')).toBe('Альфа банк');
    expect(matchBankKey('ПАО «МТС-Банк»')).toBe('МТС банк');
    expect(matchBankKey('Банк Центр-инвест')).toBe('банк Центр-инвест');
    expect(matchBankKey('Промсвязьбанк')).toBe('ПСБ банк');
  });

  it('распознаёт вариант «сбер банк» с пробелом', () => {
    expect(matchBankKey('Сбер банк')).toBe('Сбербанк');
  });

  it('возвращает null на неизвестном банке', () => {
    expect(matchBankKey('Неизвестный Банк')).toBeNull();
  });

  it('возвращает null на пустом/undefined входе', () => {
    expect(matchBankKey('')).toBeNull();
    expect(matchBankKey(undefined)).toBeNull();
  });

  it('приоритет ключей: первый матч в порядке BANK_ALIASES', () => {
    // «сбербанк» стоит раньше «втб»: строка с обоими → Сбербанк
    expect(matchBankKey('Сбербанк и ВТБ')).toBe('Сбербанк');
  });
});
