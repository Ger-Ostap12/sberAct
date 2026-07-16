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

/** Маска ручного ввода даты: берём цифры (макс 8) и расставляем точки — дд.мм.гггг. */
export const maskDate = (raw: string): string => {
  const d = raw.replace(/\D/g, '').slice(0, 8);
  const parts = [d.slice(0, 2), d.slice(2, 4), d.slice(4, 8)].filter(Boolean);
  return parts.join('.');
};

/** Полная ли и существующая ли дата дд.мм.гггг. Пустая строка считается валидной:
 *  поле необязательно, ошибку показываем только на заведомо неверной дате (31.02). */
export const isValidDateStr = (value?: string): boolean => {
  if (!value) return true;
  const match = value.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!match) return false;
  const [, dd, mm, yyyy] = match.map(Number) as unknown as [string, number, number, number];
  const date = new Date(yyyy, mm - 1, dd);
  // Date молча переносит перелёт («31.02» → 3 марта) — сверяем компоненты обратно.
  return date.getFullYear() === yyyy && date.getMonth() === mm - 1 && date.getDate() === dd;
};

/** ГГГГ-ММ-ДД → ДД.ММ.ГГГГ. Возвращает вход как есть, если это не ISO-дата. */
export const fromInputDate = (value: string): string => {
  if (!value) return '';
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
};
