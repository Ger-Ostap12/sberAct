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

/** Значение пункта «ФНС» в выпадающем списке кредитора (не банк, отдельная категория). */
export const FNS_CREDITOR_KEY = 'ФНС';

/**
 * Кредитор — налоговый орган (ФНС/ИФНС/УФНС/налоговая служба). Нужно, чтобы селектор
 * кредитора показывал «ФНС», а не «Другой кредитор», когда анализ распознал налоговый
 * орган (напр. «ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области»).
 */
export const isFnsCreditor = (name: string | undefined): boolean =>
  !!name && (/фнс/i.test(name) || /налогов/i.test(name));
