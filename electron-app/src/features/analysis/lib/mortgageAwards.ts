import { MortgageKind } from '../../../types';

export const AWARD_OPTIONS = [
  { key: 'mortgageAwardTermination', label: 'Расторгнуть кредитный договор' },
  { key: 'mortgageAwardDebt', label: 'Взыскать задолженность' },
  { key: 'mortgageAwardForeclosure', label: 'Обратить взыскание на заложенное имущество' },
] as const;

export const AWARD_AMOUNTS = [
  { key: 'mortgageAwardPrincipal', label: 'Присуждённый основной долг' },
  { key: 'mortgageAwardInterest', label: 'Присуждённые проценты' },
  { key: 'mortgageAwardPenalty', label: 'Присуждённая неустойка' },
  { key: 'mortgageAwardDuty', label: 'Присуждённая госпошлина' },
] as const;

const SOURCES: Record<string, readonly string[]> = {
  mortgageAwardPrincipal: ['principalDebt', 'loanDebt', 'principalDebt13'],
  mortgageAwardInterest: ['interest', 'interest14'],
  mortgageAwardPenalty: ['forfeit', 'forfeit15', 'penalties'],
  mortgageAwardDuty: ['stateDuty16', 'stateDuty'],
};

export const awardChecked = (fields: Record<string, string | undefined>, key: string): boolean =>
  fields[key] !== 'false';

export const awardValue = (fields: Record<string, string | undefined>, key: string): string =>
  fields[key] ?? (SOURCES[key] || []).map((source) => fields[source])
    .find((value) => value !== undefined && value.trim() !== '') ?? '';

export const awardNumber = (value: string): number | null => {
  const text = value.replace(/\s/g, '').replace(/(?:руб(?:\.|ля|лей)?|₽)$/i, '');
  if (!text) return 0;
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(text)) return null;
  const amount = Number(text.replace(',', '.'));
  return Number.isFinite(amount) ? amount : null;
};

export const awardTotal = (fields: Record<string, string | undefined>): number | null => {
  const debt = awardChecked(fields, 'mortgageAwardDebt');
  const values = AWARD_AMOUNTS
    .filter(({ key }) => debt || key === 'mortgageAwardDuty')
    .map(({ key }) => awardNumber(awardValue(fields, key)));
  if (values.some((value) => value === null)) return null;
  return values.reduce<number>((sum, value) => sum + Math.round((value ?? 0) * 100), 0) / 100;
};

export const civilMortgageAwardError = (
  fields: Record<string, string | undefined>, kind: MortgageKind,
): string | null => {
  if (kind !== 'civil' || fields.claimResolution !== 'partial') return null;
  if (!AWARD_OPTIONS.some(({ key }) => awardChecked(fields, key))) {
    return 'Все требования отклонены. Выберите «Отказать в удовлетворении».';
  }
  if (awardTotal(fields) === null) {
    return 'Присуждённые суммы должны быть неотрицательными числами с точностью до копеек.';
  }
  const debtTotal = AWARD_AMOUNTS.filter(({ key }) => key !== 'mortgageAwardDuty')
    .reduce((sum, { key }) => sum + (awardNumber(awardValue(fields, key)) ?? 0), 0);
  if (awardChecked(fields, 'mortgageAwardDebt') && debtTotal <= 0) {
    return 'Укажите положительную сумму задолженности или снимите отметку «Взыскать задолженность».';
  }
  return null;
};

export const withCivilMortgageAwards = (fields: Record<string, string | undefined>): Record<string, string | undefined> => {
  if (fields.claimResolution !== 'partial') return fields;
  const result = { ...fields };
  AWARD_OPTIONS.forEach(({ key }) => { result[key] = awardChecked(fields, key) ? 'true' : 'false'; });
  AWARD_AMOUNTS.forEach(({ key }) => { result[key] = awardValue(fields, key); });
  return result;
};
