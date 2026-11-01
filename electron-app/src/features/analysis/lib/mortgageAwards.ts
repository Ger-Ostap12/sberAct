import { MILITARY_AMOUNTS, militaryValue, militaryTotal, militaryError, withMilitaryAwards } from './militaryMortgageAwards';
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

export interface AwardAmount {
  key: string;
  label: string;
}

export const awardAmounts = (kind: MortgageKind = 'civil'): readonly AwardAmount[] => {
  if (kind === 'military') return MILITARY_AMOUNTS;
  if (kind !== 'ddu') return AWARD_AMOUNTS;
  const amounts: AwardAmount[] = AWARD_AMOUNTS.map((item) => ({ ...item }));
  const at = amounts.findIndex(({ key }) => key === 'mortgageAwardPenalty');
  amounts[at].label = 'Присуждённая неустойка за основной долг';
  amounts.splice(at + 1, 0, {
    key: 'mortgageAwardInterestPenalty', label: 'Присуждённая неустойка за проценты',
  });
  return amounts;
};

const SOURCES: Record<string, readonly string[]> = {
  mortgageAwardPrincipal: ['principalDebt', 'loanDebt', 'principalDebt13'],
  mortgageAwardInterest: ['interest', 'interest14'],
  mortgageAwardPenalty: ['forfeit', 'forfeit15', 'penalties'],
  mortgageAwardDuty: ['stateDuty16', 'stateDuty'],
  mortgageAwardInterestPenalty: ['forfeitInterest1362'],
};

export const awardChecked = (fields: Record<string, string | undefined>, key: string): boolean =>
  fields[key] !== 'false';

export const awardValue = (
  fields: Record<string, string | undefined>, key: string, kind: MortgageKind = 'civil',
): string => {
  if (kind === 'military') return militaryValue(fields, key);
  if (fields[key] !== undefined) return fields[key] ?? '';
  if (kind === 'ddu') {
    const values: Record<string, string | undefined> = {
      mortgageAwardPrincipal: fields.principalDebt || fields.loanDebt || '',
      mortgageAwardInterest: fields.interest ?? fields.interest14,
      mortgageAwardPenalty: fields.forfeit ?? fields.forfeit15,
      mortgageAwardInterestPenalty: fields.forfeitInterest1362,
      mortgageAwardDuty: fields.stateDuty16 ?? fields.stateDuty,
    };
    return values[key] ?? '';
  }
  return (SOURCES[key] || []).map((source) => fields[source])
    .find((value) => value !== undefined && value.trim() !== '') ?? '';
};

export const awardNumber = (value: string): number | null => {
  const text = value.replace(/\s/g, '').replace(/(?:руб(?:\.|ля|лей)?|₽)$/i, '');
  if (!text) return 0;
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(text)) return null;
  const amount = Number(text.replace(',', '.'));
  return Number.isFinite(amount) ? amount : null;
};

export const awardTotal = (
  fields: Record<string, string | undefined>, kind: MortgageKind = 'civil',
): number | null => {
  if (kind === 'military') return militaryTotal(fields);
  const debt = awardChecked(fields, 'mortgageAwardDebt');
  const values = awardAmounts(kind)
    .filter(({ key }) => debt || key === 'mortgageAwardDuty')
    .map(({ key }) => awardNumber(awardValue(fields, key, kind)));
  if (values.some((value) => value === null)) return null;
  return values.reduce<number>((sum, value) => sum + Math.round((value ?? 0) * 100), 0) / 100;
};

export const mortgageAwardsError = (
  fields: Record<string, string | undefined>, kind: MortgageKind,
): string | null => {
  if (kind === 'military') return militaryError(fields);
  if (fields.claimResolution !== 'partial') return null;
  if (!AWARD_OPTIONS.some(({ key }) => awardChecked(fields, key))) {
    return 'Все требования отклонены. Выберите «Отказать в удовлетворении».';
  }
  if (awardTotal(fields, kind) === null) {
    return 'Присуждённые суммы должны быть неотрицательными числами с точностью до копеек.';
  }
  const debtTotal = awardAmounts(kind).filter(({ key }) => key !== 'mortgageAwardDuty')
    .reduce((sum, { key }) => sum + (awardNumber(awardValue(fields, key, kind)) ?? 0), 0);
  if (awardChecked(fields, 'mortgageAwardDebt') && debtTotal <= 0) {
    return 'Укажите положительную сумму задолженности или снимите отметку «Взыскать задолженность».';
  }
  return null;
};

export const withMortgageAwards = (
  fields: Record<string, string | undefined>, kind: MortgageKind = 'civil',
): Record<string, string | undefined> => {
  if (kind === 'military') return withMilitaryAwards(fields);
  if (fields.claimResolution !== 'partial') return fields;
  const result = { ...fields };
  AWARD_OPTIONS.forEach(({ key }) => { result[key] = awardChecked(fields, key) ? 'true' : 'false'; });
  awardAmounts(kind).forEach(({ key }) => { result[key] = awardValue(fields, key, kind); });
  return result;
};

// Прежние civil-входы сохраняют область действия.
export const civilMortgageAwardError = (
  fields: Record<string, string | undefined>, kind: MortgageKind,
): string | null => kind === 'civil' ? mortgageAwardsError(fields, kind) : null;

export const withCivilMortgageAwards = (
  fields: Record<string, string | undefined>,
): Record<string, string | undefined> => withMortgageAwards(fields, 'civil');
