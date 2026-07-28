// Денежные суммы: канонизация ввода и красивое отображение.
// Пользователь может ввести «123 456,78», «123456.78», «123 456» — приводим к
// канону «123456.78» для хранения, а показываем сгруппированно «123 456,78».

/**
 * Нормализует введённую сумму к канону: без пробелов, десятичный разделитель —
 * точка. Принимает пробелы (в т.ч. неразрывные), запятую и точку. Оставляет
 * только цифры и одну точку. Пустая строка → пустая.
 */
export const parseAmount = (input?: string): string => {
  let s = (input ?? '').replace(/[\s ]/g, '').replace(',', '.');
  s = s.replace(/[^\d.]/g, '');
  const firstDot = s.indexOf('.');
  if (firstDot !== -1) {
    // Оставляем только первую точку, остальные (случайные) убираем.
    s = s.slice(0, firstDot + 1) + s.slice(firstDot + 1).replace(/\./g, '');
  }
  return s;
};

/** Группирует целую часть пробелами по три разряда: «1234567» → «1 234 567». */
const groupThousands = (intPart: string): string =>
  intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

/**
 * Форматирует сумму для показа: «123 456,78». На вход принимает любой формат
 * (канон/пробелы/запятую) — сначала канонизирует. Пустая/нечисловая → пустая.
 * Хвостовую точку без дробной части отбрасываем («123.» → «123»).
 */
export const formatAmount = (value?: string): string => {
  const canon = parseAmount(value);
  if (!canon) return '';
  const [intPart, fracPart = ''] = canon.split('.');
  const intGrouped = groupThousands(intPart || '0');
  return fracPart ? `${intGrouped},${fracPart}` : intGrouped;
};

/** Редактируемая форма суммы (при фокусе): канон с запятой, без группировки. */
export const editableAmount = (value?: string): string => parseAmount(value).replace('.', ',');
