// Справочник судов для дефолтов (email/сайт/адрес по названию суда). Пока один
// суд — Ворошиловский районный суд г. Ростова-на-Дону. По мере необходимости
// добавлять записи; сопоставление — courts.ts::findCourtDefaults (по aliases).
export interface Court {
  /** Каноничное название суда. */
  display: string;
  /** Электронный адрес суда. */
  email: string;
  /** Адрес сайта суда. */
  site: string;
  /** Почтовый адрес суда (пусто, если неизвестен). */
  address: string;
  /** Подстроки для распознавания названия суда (нижний регистр). */
  aliases: string[];
}

export const COURTS: Court[] = [
  {
    display: 'Ворошиловский районный суд г. Ростова-на-Дону',
    email: 'voroshilovsky.ros@sudrf.ru',
    site: 'https://voroshilovsky--ros.sudrf.ru/',
    address: '',
    aliases: ['ворошиловский районный суд', 'ворошиловский рай'],
  },
];
