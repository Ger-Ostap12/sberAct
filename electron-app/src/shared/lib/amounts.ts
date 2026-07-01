// Форматирование и парсинг денежных сумм. Перенесено 1:1 из DocumentAnalysis.

/**
 * Форматирует сумму с разделением тысяч (ru-RU, 2 знака после запятой), без символа
 * валюты. Нечисловой вход возвращается строкой как есть.
 */
export const formatAmount = (amount: string | number | undefined): string => {
  if (!amount) return '';
  const num =
    typeof amount === 'string'
      ? parseFloat(amount.replace(/[^\d.,]/g, '').replace(',', '.'))
      : amount;
  if (isNaN(num)) return String(amount);
  // Форматируем с пробелами для тысяч, но без символа валюты.
  // Intl использует неразрывный пробел как разделитель — нормализуем к обычному.
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true
  })
    .format(num)
    .replace(/\s/g, ' ');
};

/** Оставляет только цифры/точку/запятую и приводит запятую к точке (сырое значение). */
export const parseAmount = (formattedAmount: string): string => {
  return formattedAmount.replace(/[^\d.,]/g, '').replace(',', '.');
};
