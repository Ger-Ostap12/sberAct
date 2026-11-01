import {
  awardTotal, awardValue, civilMortgageAwardError, withCivilMortgageAwards,
} from '../mortgageAwards';
import { buildSubmitData, SubmitDataInput } from '../buildSubmitData';

const fields = {
  claimResolution: 'partial', principalDebt: '1000', interest: '200', forfeit: '50', stateDuty16: '10',
};

describe('частичное удовлетворение обычной ипотеки', () => {
  it('сохраняет исходные суммы и отдельно передаёт присуждённые', () => {
    const input = { ...fields, mortgageAwardPrincipal: '700' };
    const result = withCivilMortgageAwards(input);
    expect(input).not.toHaveProperty('mortgageAwardDebt');
    expect(result.principalDebt).toBe('1000');
    expect(result.mortgageAwardPrincipal).toBe('700');
    expect(result.mortgageAwardInterest).toBe('200');
    expect(result.mortgageAwardDebt).toBe('true');
    expect(awardTotal(result)).toBe(960);
  });

  it('пустое явно введённое значение означает ноль', () => {
    const input = { ...fields, mortgageAwardPenalty: '' };
    expect(awardValue(input, 'mortgageAwardPenalty')).toBe('');
    expect(awardTotal(input)).toBe(1210);
  });

  it('при отказе во взыскании считает только госпошлину', () => {
    const input = { ...fields, mortgageAwardDebt: 'false', mortgageAwardPrincipal: '-1' };
    expect(awardTotal(input)).toBe(10);
    expect(civilMortgageAwardError(input, 'civil')).toBeNull();
  });

  it.each(['full', 'deny'])('исход %s игнорирует прежние настройки частичного', (claimResolution) => {
    const input = { ...fields, claimResolution, mortgageAwardDebt: 'false' };
    expect(withCivilMortgageAwards(input)).toBe(input);
    expect(civilMortgageAwardError(input, 'civil')).toBeNull();
  });

  it.each(['-1', 'NaN', '1.001', '1,2,3'])('отклоняет некорректную сумму %s', (value) => {
    expect(civilMortgageAwardError({ ...fields, mortgageAwardPrincipal: value }, 'civil')).toMatch(/неотрицательными/);
  });

  it('не допускает отклонения всех требований в режиме частичного', () => {
    expect(civilMortgageAwardError({ ...fields, mortgageAwardTermination: 'false',
      mortgageAwardDebt: 'false', mortgageAwardForeclosure: 'false' }, 'civil')).toMatch(/Все требования/);
  });

  it('не допускает взыскания нулевой задолженности', () => {
    expect(civilMortgageAwardError({ ...fields, mortgageAwardPrincipal: '',
      mortgageAwardInterest: '', mortgageAwardPenalty: '' }, 'civil')).toMatch(/положительную сумму/);
  });

  it('не применяет проверки к ДДУ и военной ипотеке', () => {
    expect(civilMortgageAwardError({ claimResolution: 'partial' }, 'ddu')).toBeNull();
    expect(civilMortgageAwardError({ claimResolution: 'partial' }, 'military')).toBeNull();
  });

  it('считает копейки без хвоста двоичной дроби', () => {
    expect(awardTotal({ ...fields, mortgageAwardPrincipal: '0,10',
      mortgageAwardInterest: '0,20', mortgageAwardPenalty: '', mortgageAwardDuty: '' })).toBe(0.3);
  });
});

const submit = (kind: 'civil' | 'ddu' | 'military', category: 'mortgage' | 'bankruptcy' = 'mortgage') => {
  const input: SubmitDataInput = {
    analysisResult: { documentType: 'mortgage_claim', confidence: 1, entityType: 'individual',
      fields: { ...fields }, obligations: [], collaterals: [], thirdParties: [], debtors: [],
      rawText: '', metadata: { pageCount: 1, wordCount: 1, language: 'ru' } },
    editedFields: { mortgageAwardTermination: 'false', mortgageAwardPrincipal: '700' },
    entityType: 'individual', collateralOption: null, debtorStatus: null,
    applicationKind: 'initiation', selectedActs: [], documentCategory: category, mortgageKind: kind,
  };
  return buildSubmitData(input).fields;
};

it('передаёт флаги и отдельные суммы в генерацию обычной ипотеки', () => {
  const result = submit('civil');
  expect(result.mortgageAwardTermination).toBe('false');
  expect(result.mortgageAwardDebt).toBe('true');
  expect(result.mortgageAwardPrincipal).toBe('700');
  expect(result.principalDebt).toBe('1000');
  expect(result.totalDebt).toBeUndefined();
});

it.each(['military'] as const)('добавляет отдельные значения присуждений для %s', (kind) => {
  expect(submit(kind).mortgageAwardDebt).toBe('true');
  expect(submit(kind).militaryAwardCzzDebt).toBe('true');
});

it('не добавляет новые настройки в банкротство', () => {
  expect(submit('civil', 'bankruptcy')).not.toHaveProperty('mortgageAwardDebt');
});
