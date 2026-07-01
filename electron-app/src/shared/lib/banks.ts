import { BANK_DATA, BANK_ALIASES } from '../constants/banks';

// Распознавание банка по названию из документа → ключ в BANK_DATA (для автоподсветки
// в выпадающем списке). Перенесено 1:1 из DocumentAnalysis.
export const matchBankKey = (name?: string): string | null => {
  if (!name) return null;
  if (BANK_DATA[name]) return name; // точное совпадение с ключом
  const low = name.toLowerCase();
  for (const { key, keywords } of BANK_ALIASES) {
    if (keywords.some((k) => low.includes(k))) return key;
  }
  return null;
};
