import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ClaimResolutionSection from '../sections/ClaimResolutionSection';
import FinancesSection from '../sections/FinancesSection';
import { awardTotal, mortgageAwardsError, withMortgageAwards } from '../lib/mortgageAwards';
import { MILITARY_FLAGS } from '../lib/militaryMortgageAwards';

const fields = {
  claimResolution: 'partial', principalDebt: '1000', interest: '200', forfeit: '50',
  forfeitInterest1362: '20', stateDuty16: '10', totalDebt: '1270',
  milPrincipalCzz: '800000', milLoanInterest: '50000', milPenaltySum: '30000',
  stateDutyLocalBudget1363: '10000',
};

it('показывает отдельные требования и суммы банка и ЦЖЗ только при частичном исходе', () => {
  const { rerender } = render(<ClaimResolutionSection mortgageKind="military" editedFields={fields} onFieldChange={() => {}} />);
  expect(screen.getAllByRole('checkbox')).toHaveLength(7);
  expect(screen.getByLabelText('ЦЖЗ: присуждённый основной долг')).toHaveValue('800000');
  expect(screen.getByLabelText('Банк: присуждённая неустойка на проценты')).toHaveValue('20');
  expect(awardTotal(fields, 'military')).toBe(891280);
  rerender(<ClaimResolutionSection mortgageKind="military" editedFields={{ ...fields, claimResolution: 'deny' }} onFieldChange={() => {}} />);
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});

it('исключает снятое взыскание ЦЖЗ из полей и итога, сохраняя банк', () => {
  const state = { ...fields, militaryAwardCzzDebt: 'false', militaryAwardCzzPrincipal: '-1' };
  render(<ClaimResolutionSection mortgageKind="military" editedFields={state} onFieldChange={() => {}} />);
  expect(screen.queryByLabelText('ЦЖЗ: присуждённый основной долг')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Банк: присуждённый основной долг')).toBeInTheDocument();
  expect(awardTotal(state, 'military')).toBe(11280);
  expect(mortgageAwardsError(state, 'military')).toBeNull();
});

it('проверяет отрицательные суммы, пустое взыскание и отказ во всех требованиях', () => {
  expect(mortgageAwardsError({ ...fields, militaryAwardCzzPrincipal: '-1' }, 'military')).toMatch(/неотрицательными/);
  expect(mortgageAwardsError({ ...fields, militaryAwardCzzPrincipal: '', militaryAwardCzzInterest: '', militaryAwardCzzPenalty: '' }, 'military')).toMatch(/положительную/);
  expect(mortgageAwardsError({ ...fields, ...Object.fromEntries(MILITARY_FLAGS.map(({ key }) => [key, 'false'])) }, 'military')).toMatch(/Все требования/);
});

it('передаёт отдельные присуждённые суммы без изменения исходных финансов', () => {
  const result = withMortgageAwards({ ...fields, militaryAwardCzzPrincipal: '500000' }, 'military');
  expect(result.milPrincipalCzz).toBe('800000');
  expect(result.militaryAwardCzzPrincipal).toBe('500000');
  expect(result.militaryAwardCzzDebt).toBe('true');
});

it('даёт ввести реквизиты ЦЖЗ, дату будущих процентов и вторую неустойку', () => {
  const change = jest.fn();
  render(<FinancesSection mode="mortgage" mortgageKind="military" editedFields={fields} onFieldChange={change} />);
  fireEvent.change(screen.getByLabelText('Номер договора ЦЖЗ'), { target: { value: 'ЦЖЗ-123' } });
  fireEvent.blur(screen.getByLabelText('Номер договора ЦЖЗ'));
  expect(change).toHaveBeenCalledWith('milCzzContractNumber', 'ЦЖЗ-123');
  fireEvent.change(screen.getByLabelText('Дата начала будущих процентов'), { target: { value: '2026-11-03' } });
  fireEvent.blur(screen.getByLabelText('Дата начала будущих процентов'));
  expect(change).toHaveBeenCalledWith('milFutureInterestFrom', '03.11.2026');
  expect(screen.getByLabelText('Неустойка за просроченные проценты')).toBeInTheDocument();
});
