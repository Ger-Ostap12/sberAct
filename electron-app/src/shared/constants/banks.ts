// Банки-кредиторы больше не хардкодятся на фронте: единый источник — бэкенд
// (creditor_registry.py, эндпоинт GET /banks). Здесь только тип записи банка,
// приходящей с бэкенда. Загрузка — через useBanks (features/analysis/hooks).
export interface Bank {
  /** Имя для выпадающего списка. */
  display: string;
  inn: string;
  ogrn: string;
  address: string;
  /** Алиасы для сопоставления имени кредитора (см. matchBankKey). */
  aliases: string[];
}
