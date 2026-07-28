// Клиентская валидация полей ввода. Каждая функция: ПУСТАЯ строка считается
// валидной (не флагаем ещё не заполненное поле), непустая — проверяется по шаблону.
// Валидация информирующая (подсветка), не блокирующая переход по форме.

/** Email. Прагматичный шаблон (не полный RFC): локальная@домен.зона. */
export const isValidEmail = (value?: string): boolean => {
  const v = (value ?? '').trim();
  if (!v) return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
};

/** URL: http(s)://хост[...]. Требуем схему http/https, иначе поле сайта неоднозначно. */
export const isValidUrl = (value?: string): boolean => {
  const v = (value ?? '').trim();
  if (!v) return true;
  try {
    const u = new URL(v);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
};

/** Серия паспорта РФ — ровно 4 цифры. */
export const isValidPassportSeries = (value?: string): boolean => {
  const v = (value ?? '').trim();
  if (!v) return true;
  return /^\d{4}$/.test(v);
};

/** Номер паспорта РФ — ровно 6 цифр. */
export const isValidPassportNumber = (value?: string): boolean => {
  const v = (value ?? '').trim();
  if (!v) return true;
  return /^\d{6}$/.test(v);
};
