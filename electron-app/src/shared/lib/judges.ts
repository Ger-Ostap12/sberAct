// Приведение полного ФИО судьи к формату «Фамилия И.О.». Перенесено 1:1.
export const formatJudgeName = (fullName: string): string => {
  if (!fullName || !fullName.trim()) return fullName;

  // Разбиваем ФИО на части
  const parts = fullName.trim().split(/\s+/);

  if (parts.length < 2) {
    // Если только одно слово, возвращаем как есть
    return fullName;
  }

  // Фамилия - первое слово
  const lastName = parts[0];

  // Имя и отчество - остальные слова
  const firstName = parts[1] || '';
  const middleName = parts[2] || '';

  // Берем первые буквы имени и отчества
  const firstInitial = firstName.charAt(0).toUpperCase();
  const middleInitial = middleName.charAt(0).toUpperCase();

  // Формируем результат: "Фамилия И.О."
  if (middleInitial) {
    return `${lastName} ${firstInitial}.${middleInitial}.`;
  } else if (firstInitial) {
    return `${lastName} ${firstInitial}.`;
  } else {
    return lastName;
  }
};
