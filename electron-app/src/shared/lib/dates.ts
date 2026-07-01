// Преобразование дат между русским форматом ДД.ММ.ГГГГ и форматом input[type="date"]
// (ГГГГ-ММ-ДД). Поведение перенесено 1:1 из DocumentAnalysis.

/** ДД.ММ.ГГГГ (или уже ISO) → ГГГГ-ММ-ДД. Пустая строка, если формат не распознан. */
export const toInputDate = (value?: string): string => {
  if (!value) return '';
  // Если уже в ISO-формате, возвращаем как есть
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  const match = value.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!match) return '';
  const [, day, month, year] = match;
  const dd = day.padStart(2, '0');
  const mm = month.padStart(2, '0');
  return `${year}-${mm}-${dd}`;
};

/** ГГГГ-ММ-ДД → ДД.ММ.ГГГГ. Возвращает вход как есть, если это не ISO-дата. */
export const fromInputDate = (value: string): string => {
  if (!value) return '';
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
};
