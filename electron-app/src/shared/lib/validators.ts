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

/** Оставляет только цифры и обрезает до max символов (жёсткая маска ввода). */
export const digitsOnly = (value: string, max: number): string =>
  value.replace(/\D/g, '').slice(0, max);

/** Номер дела (ипотека): формат «2-<порядковый>/<год>», напр. «2-1223/2026». */
export const isValidCaseNumber = (value?: string): boolean => {
  const v = (value ?? '').trim();
  if (!v) return true;
  return /^2-\d+\/\d{4}$/.test(v);
};

// ФИО: «Фамилия Имя Отчество» или «Фамилия И.О.» (кириллица, дефис в фамилии
// допустим: «Римский-Корсаков» — с заглавной после дефиса). Инициалы — с точками,
// пробел между ними опционален.
const FIO_WORD = '[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?';
const FIO_FULL = new RegExp(`^${FIO_WORD}\\s+${FIO_WORD}\\s+${FIO_WORD}$`);
const FIO_SHORT = new RegExp(`^${FIO_WORD}\\s+[А-ЯЁ]\\.\\s?[А-ЯЁ]\\.$`);

/** ФИО в формате «Фамилия Имя Отчество» или «Фамилия И.О.». Пустое — валидно. */
export const isValidFio = (value?: string): boolean => {
  const v = (value ?? '').trim();
  if (!v) return true;
  return FIO_FULL.test(v) || FIO_SHORT.test(v);
};
