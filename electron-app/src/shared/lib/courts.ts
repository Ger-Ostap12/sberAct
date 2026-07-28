import { COURTS, Court } from '../constants/courts';

/** Дефолты суда (email/сайт/адрес), извлекаемые из справочника. */
export interface CourtDefaults {
  email: string;
  site: string;
  address: string;
  /** Название суда в родительном падеже — «якорь» для акта (минуя морфологию). */
  genitive: string;
}

/**
 * Ищет суд по названию: точное совпадение по display, затем по алиасам как
 * подстроке (регистр игнорируется, ё/е нормализуются). По образцу matchBankKey.
 * Возвращает дефолты (email/сайт/адрес) или null.
 */
export const findCourtDefaults = (courtName?: string): CourtDefaults | null => {
  if (!courtName) return null;
  const norm = (s: string) => s.toLowerCase().replace(/ё/g, 'е').trim();
  const low = norm(courtName);
  const match: Court | undefined =
    COURTS.find((c) => norm(c.display) === low) ||
    COURTS.find((c) => c.aliases.some((alias) => low.includes(norm(alias))));
  if (!match) return null;
  return { email: match.email, site: match.site, address: match.address, genitive: match.genitive };
};
