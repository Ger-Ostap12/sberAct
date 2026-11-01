import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import ClaimResolutionSection from '../sections/ClaimResolutionSection';
import FinancesSection from '../sections/FinancesSection';
import {
  awardTotal, awardValue, mortgageAwardsError, withMortgageAwards,
} from '../lib/mortgageAwards';
import { buildSubmitData, SubmitDataInput } from '../lib/buildSubmitData';

const values = { claimResolution: 'partial', principalDebt: '1000', interest: '200',
  forfeit: '50', forfeitInterest1362: '20', stateDuty16: '10', totalDebt: '1270' };

it('показывает и считает две присуждённые неустойки только для ДДУ', () => {
  const { rerender } = render(<ClaimResolutionSection editedFields={values} mortgageKind="ddu" onFieldChange={() => {}} />);
  expect(screen.getAllByRole('checkbox')).toHaveLength(3);
  expect(screen.getByLabelText('Присуждённая неустойка за основной долг')).toHaveValue('50');
  expect(screen.getByLabelText('Присуждённая неустойка за проценты')).toHaveValue('20');
  expect(screen.getByLabelText('Итого присуждено')).toHaveValue('1 280,00');
  rerender(<ClaimResolutionSection editedFields={values} mortgageKind="civil" onFieldChange={() => {}} />);
  expect(screen.queryByLabelText('Присуждённая неустойка за проценты')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Итого присуждено')).toHaveValue('1 260,00');
});

it('передаёт правку второй неустойки и скрывает обе при выключении долга', () => {
  const Form = () => {
    const [fields, setFields] = React.useState<Record<string, string>>(values);
    return <ClaimResolutionSection editedFields={fields} mortgageKind="ddu"
      onFieldChange={(key, value) => setFields((old) => ({ ...old, [key]: value }))} />;
  };
  render(<Form />);
  fireEvent.change(screen.getByLabelText('Присуждённая неустойка за проценты'), { target: { value: '5' } });
  expect(screen.getByLabelText('Итого присуждено')).toHaveValue('1 265,00');
  fireEvent.click(screen.getByRole('checkbox', { name: 'Взыскать задолженность' }));
  expect(screen.queryByLabelText('Присуждённая неустойка за основной долг')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Присуждённая неустойка за проценты')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Итого присуждено')).toHaveValue('10,00');
  fireEvent.click(screen.getByRole('checkbox', { name: 'Взыскать задолженность' }));
  expect(screen.getByLabelText('Присуждённая неустойка за проценты')).toHaveValue('5');
});

it('в финансовом блоке ДДУ вторая неустойка участвует в сверке', () => {
  const change = jest.fn();
  const { rerender } = render(<FinancesSection mode="mortgage" mortgageKind="ddu"
    editedFields={values} onFieldChange={change} />);
  expect(screen.getByText('Неустойка за просроченный основной долг:')).toBeInTheDocument();
  expect(screen.getByLabelText('Неустойка за просроченные проценты')).toHaveValue('20');
  expect(screen.getByText(/Расчеты корректны/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Неустойка за просроченные проценты'), { target: { value: '30' } });
  expect(change).toHaveBeenCalledWith('forfeitInterest1362', '30');
  rerender(<FinancesSection mode="mortgage" mortgageKind="ddu"
    editedFields={{ ...values, forfeitInterest1362: '30' }} onFieldChange={change} />);
  expect(screen.getByText(/Не сходится/)).toBeInTheDocument();
});

it.each(['civil'] as const)('в финансовом блоке %s вторая неустойка не используется', (kind) => {
  render(<FinancesSection mode="mortgage" mortgageKind={kind}
    editedFields={{ ...values, totalDebt: '1250' }} onFieldChange={() => {}} />);
  expect(screen.queryByLabelText('Неустойка за просроченные проценты')).not.toBeInTheDocument();
  expect(screen.getByText(/Расчеты корректны/)).toBeInTheDocument();
});

it('сохраняет исходные суммы и отдельно задаёт две присуждённые', () => {
  const input = { ...values, mortgageAwardPenalty: '20', mortgageAwardInterestPenalty: '5' };
  const output = withMortgageAwards(input, 'ddu');
  expect(output.forfeit).toBe('50');
  expect(output.forfeitInterest1362).toBe('20');
  expect(output.mortgageAwardPenalty).toBe('20');
  expect(output.mortgageAwardInterestPenalty).toBe('5');
  expect(awardTotal(output, 'ddu')).toBe(1235);
  expect(input).not.toHaveProperty('mortgageAwardDebt');
});

it.each(['-1', 'abc', '1.001', 'NaN'])('проверяет вторую присуждённую неустойку %s', (value) => {
  const fields = { ...values, mortgageAwardInterestPenalty: value };
  expect(mortgageAwardsError(fields, 'ddu')).toMatch(/неотрицательными/);
  expect(mortgageAwardsError({ ...fields, mortgageAwardDebt: 'false' }, 'ddu')).toBeNull();
  expect(mortgageAwardsError(fields, 'civil')).toBeNull();
});

it('не восстанавливает очищенные поля из скрытых устаревших алиасов', () => {
  const fields = { ...values, principalDebt: '', loanDebt: '', principalDebt13: '999',
    interest: '', interest14: '900', forfeit: '', forfeit15: '800', penalties: '700',
    stateDuty16: '', stateDuty: '600', forfeitInterest1362: '' };
  expect(awardValue(fields, 'mortgageAwardPrincipal', 'ddu')).toBe('');
  expect(awardValue(fields, 'mortgageAwardInterest', 'ddu')).toBe('');
  expect(awardValue(fields, 'mortgageAwardPenalty', 'ddu')).toBe('');
  expect(awardValue(fields, 'mortgageAwardDuty', 'ddu')).toBe('');
  expect(awardTotal(fields, 'ddu')).toBe(0);
  expect(mortgageAwardsError(fields, 'ddu')).toMatch(/положительную сумму/);
});

it.each(['full', 'deny'])('при %s не показывает дополнительные суммы ДДУ', (claimResolution) => {
  render(<ClaimResolutionSection mortgageKind="ddu" editedFields={{ ...values, claimResolution }}
    onFieldChange={() => {}} />);
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Присуждённая неустойка за проценты')).not.toBeInTheDocument();
});

it('сохраняет исходные значения двух неустоек при передаче и согласует алиасы', () => {
  const input: SubmitDataInput = {
    analysisResult: { documentType: 'mortgage_claim', confidence: 1, entityType: 'individual',
      fields: { ...values, forfeit15: '999', interest14: '888' }, obligations: [],
      collaterals: [], thirdParties: [], debtors: [], rawText: '',
      metadata: { pageCount: 1, wordCount: 1, language: 'ru' } },
    editedFields: { claimResolution: 'partial', forfeit: '0', interest: '80',
      mortgageAwardInterestPenalty: '5' },
    entityType: 'individual', collateralOption: 'no_collateral', debtorStatus: null,
    applicationKind: 'initiation', selectedActs: [], documentCategory: 'mortgage', mortgageKind: 'ddu',
  };
  const result = buildSubmitData(input).fields;
  expect(result.forfeit).toBe('0');
  expect(result.forfeit15).toBe('0');
  expect(result.interest14).toBe('80');
  expect(result.forfeitInterest1362).toBe('20');
  expect(result.mortgageAwardInterestPenalty).toBe('5');
  expect(result.mortgageAwardDebt).toBe('true');
  expect(input.analysisResult.fields.forfeit15).toBe('999');
});
