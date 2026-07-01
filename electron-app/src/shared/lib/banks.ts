import { Bank } from '../constants/banks';

/**
 * Распознаёт банк по названию кредитора среди переданного списка (с бэкенда) →
 * возвращает `display` (ключ для выпадающего списка) или null. Логика прежняя:
 * точное совпадение по display, затем поиск по алиасам как подстроке (регистр
 * игнорируется).
 */
export const matchBankKey = (name: string | undefined, banks: Bank[]): string | null => {
  if (!name) return null;
  const exact = banks.find((b) => b.display === name);
  if (exact) return exact.display;
  const low = name.toLowerCase();
  for (const bank of banks) {
    if (bank.aliases.some((alias) => low.includes(alias))) return bank.display;
  }
  return null;
};
