/** Валидация реквизитов свидетельства о смерти.
 *
 *  Формат: римская серия + две заглавные русские буквы + шестизначный номер
 *  («II-МЮ № 123456»). Разделители (дефисы, «№», пробелы) необязательны и в разных
 *  бланках расставлены по-разному, поэтому сверяем состав, а не пунктуацию:
 *  римские цифры → две русские буквы → шесть цифр.
 */

/** Разбор по структуре: римская часть, ровно две русские буквы, ровно шесть цифр.
 *  В римскую часть допускаем кириллические двойники: на русской раскладке «II»
 *  набирается латиницей, и пользователь легко введёт «ХХ»/«ІІ» вместо «XX»/«II».
 *  Двусмысленности нет — серия из букв всегда стоит вплотную перед шестью цифрами,
 *  и разбор доводится бэктрекингом. */
const PARSE_RE = /^([IVXLCDMХСМДЛИ]+)-?([А-ЯЁ]{2})-?(\d{6})$/;

/** Кириллические двойники латинских римских цифр. */
const LOOKALIKE: Readonly<Record<string, string>> = {
  Х: 'X', С: 'C', М: 'M', Д: 'D', Л: 'L', И: 'I',
};

/** Строгая римская цифра (1–3999): отсекает бессмысленные наборы вроде «IIII» или «VV». */
const ROMAN_RE = /^(?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$/;

/** Убирает пунктуацию, приводит к верхнему регистру: «II-МЮ № 123456» → «IIМЮ123456». */
const strip = (value: string): string =>
  value
    .toUpperCase()
    .replace(/[‐-―]/g, '-')
    .replace(/[\s№-]/g, '');

const toLatinRoman = (roman: string): string =>
  roman.replace(/[ХСМДЛИ]/g, (ch) => LOOKALIKE[ch] ?? ch);

/** Пустое значение валидно (поле необязательное) — как isValidDateStr. */
export const isValidDeathCertificate = (value?: string): boolean => {
  if (!value || !value.trim()) return true;
  const parsed = PARSE_RE.exec(strip(value));
  return parsed ? ROMAN_RE.test(toLatinRoman(parsed[1])) : false;
};

/** Живая маска: расставляет дефис и «№» по мере ввода — «XXМО123445» → «XX-МО № 123445».
 *
 *  Где кончается римская серия, определяем по структуре: серия — это ДВЕ последние
 *  буквы перед цифрами (буквы вроде «М» и «Х» годятся и в римскую цифру, и в серию,
 *  поэтому позиционное правило надёжнее алфавитного). Пока цифр нет, разделить
 *  буквы нечем — тогда границей служит дефис, если пользователь ввёл его сам.
 */
export const maskDeathCertificate = (raw: string): string => {
  const cleaned = raw
    .toUpperCase()
    .replace(/[‐-―]/g, '-')
    .replace(/[^IVXLCDMА-ЯЁ0-9-]/g, ''); // «№» и пробелы расставляем сами

  const digits = cleaned.replace(/\D/g, '').slice(0, 6);
  const head = cleaned.split(/\d/)[0]; // всё до первой цифры: римские + серия + дефис
  const letters = head.replace(/-/g, '');
  const typedDash = head.includes('-');

  let roman = letters;
  let series = '';
  if (typedDash) {
    // Пользователь сам обозначил границу: «II-МЮ».
    const [left, right = ''] = head.split('-');
    roman = left;
    series = right.slice(0, 2);
  } else if (digits && letters.length >= 3) {
    roman = letters.slice(0, -2);
    series = letters.slice(-2);
  }

  let out = roman;
  if (series) out += `-${series}`;
  else if (typedDash) out += '-';
  if (digits) out += ` № ${digits}`;
  return out;
};
