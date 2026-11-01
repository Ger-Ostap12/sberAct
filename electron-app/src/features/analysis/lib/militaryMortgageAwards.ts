export const MILITARY_FLAGS = [
  { key: 'mortgageAwardTermination', label: 'Банк: расторгнуть кредитный договор' },
  { key: 'mortgageAwardDebt', label: 'Банк: взыскать задолженность' },
  { key: 'mortgageAwardForeclosure', label: 'Банк: обратить взыскание на залог' },
  { key: 'militaryAwardCzzTermination', label: 'Росвоенипотека: расторгнуть договор ЦЖЗ' },
  { key: 'militaryAwardCzzDebt', label: 'Росвоенипотека: взыскать задолженность по ЦЖЗ' },
  { key: 'militaryAwardCzzFutureInterest', label: 'Росвоенипотека: взыскать будущие проценты' },
  { key: 'militaryAwardCzzForeclosure', label: 'Росвоенипотека: обратить взыскание на залог' },
] as const;

export const MILITARY_AMOUNTS = [
  { key: 'mortgageAwardPrincipal', label: 'Банк: присуждённый основной долг', source: 'principalDebt' },
  { key: 'mortgageAwardInterest', label: 'Банк: присуждённые проценты', source: 'interest' },
  { key: 'mortgageAwardPenalty', label: 'Банк: присуждённая неустойка на основной долг', source: 'forfeit' },
  { key: 'mortgageAwardInterestPenalty', label: 'Банк: присуждённая неустойка на проценты', source: 'forfeitInterest1362' },
  { key: 'mortgageAwardDuty', label: 'Банк: присуждённые расходы по госпошлине', source: 'stateDuty16' },
  { key: 'militaryAwardCzzPrincipal', label: 'ЦЖЗ: присуждённый основной долг', source: 'milPrincipalCzz' },
  { key: 'militaryAwardCzzInterest', label: 'ЦЖЗ: присуждённые проценты', source: 'milLoanInterest' },
  { key: 'militaryAwardCzzPenalty', label: 'ЦЖЗ: присуждённые пени', source: 'milPenaltySum' },
  { key: 'militaryAwardBudgetDuty', label: 'Присуждённая госпошлина в бюджет', source: 'stateDutyLocalBudget1363' },
] as const;

type Fields = Record<string, string | undefined>;

export const militaryValue = (fields: Fields, key: string): string => {
  if (fields[key] !== undefined) return fields[key] ?? '';
  const source = MILITARY_AMOUNTS.find((item) => item.key === key)?.source;
  if (!source) return '';
  if (source === 'principalDebt') return fields.principalDebt || fields.loanDebt || '';
  if (source === 'interest') return fields.interest ?? fields.interest14 ?? '';
  if (source === 'forfeit') return fields.forfeit ?? fields.forfeit15 ?? '';
  if (source === 'stateDuty16') return fields.stateDuty16 ?? fields.stateDuty ?? '';
  return fields[source] ?? '';
};

export const militaryAmountActive = (fields: Fields, key: string): boolean => {
  if (key === 'mortgageAwardDuty' || key === 'militaryAwardBudgetDuty') return true;
  return fields[key.startsWith('militaryAwardCzz') ? 'militaryAwardCzzDebt' : 'mortgageAwardDebt'] !== 'false';
};

const number = (value: string): number | null => {
  const text = value.replace(/\s/g, '').replace(/(?:руб(?:\.|ля|лей)?|₽)$/i, '');
  if (!text) return 0;
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(text)) return null;
  const amount = Number(text.replace(',', '.'));
  return Number.isFinite(amount) ? amount : null;
};

export const militaryTotal = (fields: Fields): number | null => {
  const amounts = MILITARY_AMOUNTS.filter(({ key }) => militaryAmountActive(fields, key))
    .map(({ key }) => number(militaryValue(fields, key)));
  if (amounts.some((value) => value === null)) return null;
  return amounts.reduce<number>((sum, value) => sum + Math.round((value ?? 0) * 100), 0) / 100;
};

export const militaryError = (fields: Fields): string | null => {
  if (fields.claimResolution !== 'partial') return null;
  if (!MILITARY_FLAGS.some(({ key }) => fields[key] !== 'false')) {
    return 'Все требования отклонены. Выберите «Отказать в удовлетворении».';
  }
  if (militaryTotal(fields) === null) return 'Присуждённые суммы должны быть неотрицательными числами с точностью до копеек.';
  for (const [flag, prefix] of [['mortgageAwardDebt', 'mortgageAward'], ['militaryAwardCzzDebt', 'militaryAwardCzz']]) {
    const total = MILITARY_AMOUNTS.filter(({ key }) => key.startsWith(prefix)
      && key !== 'mortgageAwardDuty').reduce((sum, { key }) => sum + (number(militaryValue(fields, key)) ?? 0), 0);
    if (fields[flag] !== 'false' && total <= 0) return 'Укажите положительную присуждённую задолженность или снимите требование взыскания.';
  }
  return null;
};

export const withMilitaryAwards = (fields: Fields): Fields => {
  if (fields.claimResolution !== 'partial') return fields;
  const result = { ...fields };
  MILITARY_FLAGS.forEach(({ key }) => { result[key] = fields[key] === 'false' ? 'false' : 'true'; });
  MILITARY_AMOUNTS.forEach(({ key }) => { result[key] = militaryValue(fields, key); });
  return result;
};
