// Извлечение адреса и кадастрового номера из свободного описания предмета залога.
// Перенесено 1:1 из DocumentAnalysis (слоистые regex-паттерны с fallback).
export const extractCollateralData = (
  description: string
): { address?: string; cadastralNumber?: string } => {
  if (!description) return {};

  const result: { address?: string; cadastralNumber?: string } = {};

  // Извлекаем адрес (формат: индекс (6 цифр) + адрес)
  // Паттерн: 6 цифр, затем запятая/пробел, затем русские буквы и адресные данные
  // Ищем адрес после слов "адрес", "расположен", "находится", "по адресу"
  const addressPatterns = [
    /(?:адрес|расположен|находится|по\s+адресу)[:\s]*([0-9]{6}[,\s]+[А-ЯЁа-яё][^,\n]{10,200}?(?:[,\s]+[А-ЯЁа-яё][^,\n]{5,100}?)*)/i,
    /([0-9]{6}[,\s]+[А-ЯЁа-яё][^,\n]{10,200}?(?:[,\s]+[А-ЯЁа-яё][^,\n]{5,100}?)*)/,
    /([А-ЯЁа-яё]+[,\s]+[А-ЯЁа-яё]+[,\s]+(?:ул|улица|проспект|пр|переулок|пер|площадь|пл|бульвар|б-р)[^,\n]{5,100}?)/i
  ];

  for (const pattern of addressPatterns) {
    const match = description.match(pattern);
    if (match) {
      const address = match[1].trim();
      // Проверяем, что это действительно адрес (содержит индекс или адресные слова)
      if (
        address.length > 10 &&
        (address.match(/^\d{6}/) ||
          address.match(
            /(?:ул|улица|проспект|пр|переулок|пер|площадь|пл|бульвар|б-р|дом|д\.|квартира|кв\.|офис|оф\.)/i
          ))
      ) {
        result.address = address;
        break;
      }
    }
  }

  // Извлекаем кадастровый номер
  // Паттерны: XX:XX:XXXXXX:XX или просто набор цифр с двоеточиями
  // Также ищем после слов "кадастровый номер", "кадастр", "кадастровый"
  const cadastralPatterns = [
    /кадастровый\s+номер[:\s]*([\d:]+(?:\d|:)+)/i,
    /кадастр[:\s]*([\d:]+(?:\d|:)+)/i,
    /кадастровый[:\s]*([\d:]+(?:\d|:)+)/i,
    /([\d]{2}:[\d]{2}:[\d]{6,}:[\d]{1,})/, // Формат XX:XX:XXXXXX:XX
    /([\d]{2}:[\d]{2}:[\d]{4,}:[\d]{1,})/, // Формат XX:XX:XXXX:XX
    /([\d]{2}:[\d]{2}:[\d]{2,}:[\d]{1,})/, // Формат XX:XX:XX:XX
    /([\d]{10,})/ // Просто длинный номер (10+ цифр подряд)
  ];

  for (const pattern of cadastralPatterns) {
    const match = description.match(pattern);
    if (match) {
      const cadastral = match[1].trim();
      // Проверяем, что это действительно кадастровый номер (содержит двоеточия или достаточно длинный)
      if (cadastral.includes(':') || cadastral.length >= 10) {
        result.cadastralNumber = cadastral;
        break;
      }
    }
  }

  return result;
};
