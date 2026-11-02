import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import ClaimResolutionSection from '../ClaimResolutionSection';
import { MortgageKind } from '../../../../types';

const initial = {
  claimResolution: 'full', principalDebt: '1000', interest: '200', forfeit: '50', stateDuty16: '10',
};

const Form = ({ kind = 'civil' }: { kind?: MortgageKind }) => {
  const [fields, setFields] = React.useState<Record<string, string>>(initial);
  return <>
    <ClaimResolutionSection editedFields={fields} mortgageKind={kind}
      onFieldChange={(key, value) => setFields((previous) => ({ ...previous, [key]: value }))} />
    <output data-testid="original-principal">{fields.principalDebt}</output>
  </>;
};

it('показывает дополнительные настройки только при частичном удовлетворении', () => {
  render(<Form />);
  expect(screen.queryByRole('group', { name: 'Частичное удовлетворение' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить частично' }));
  expect(screen.getAllByRole('checkbox')).toHaveLength(3);
  screen.getAllByRole('checkbox').forEach((checkbox) => expect(checkbox).toBeChecked());
  expect(screen.getByLabelText('Присуждённый основной долг')).toHaveValue('1000');
  fireEvent.click(screen.getByRole('radio', { name: 'Отказать в удовлетворении' }));
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});

it('сохраняет отдельные суммы при переключении исходов и требований', () => {
  render(<Form />);
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить частично' }));
  fireEvent.change(screen.getByLabelText('Присуждённый основной долг'), { target: { value: '700' } });
  expect(screen.getByLabelText('Итого присуждено')).toHaveValue('960,00');
  expect(screen.getByTestId('original-principal')).toHaveTextContent('1000');
  fireEvent.click(screen.getByRole('checkbox', { name: 'Взыскать задолженность' }));
  expect(screen.queryByLabelText('Присуждённый основной долг')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Присуждённая госпошлина')).toHaveValue('10');
  expect(screen.getByLabelText('Итого присуждено')).toHaveValue('10,00');
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить полностью' }));
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить частично' }));
  fireEvent.click(screen.getByRole('checkbox', { name: 'Взыскать задолженность' }));
  expect(screen.getByLabelText('Присуждённый основной долг')).toHaveValue('700');
});

it('показывает ошибку при отклонении всех требований и неверной сумме', () => {
  render(<Form />);
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить частично' }));
  fireEvent.change(screen.getByLabelText('Присуждённый основной долг'), { target: { value: '-1' } });
  expect(screen.getByRole('alert')).toHaveTextContent('неотрицательными');
  screen.getAllByRole('checkbox').forEach((checkbox) => fireEvent.click(checkbox));
  expect(screen.getByRole('alert')).toHaveTextContent('Все требования отклонены');
});

it.each(['military'] as const)('рисует отдельные требования и проверяет незаполненные суммы ЦЖЗ для %s', (kind) => {
  render(<Form kind={kind} />);
  fireEvent.click(screen.getByRole('radio', { name: 'Удовлетворить частично' }));
  expect(screen.getAllByRole('checkbox')).toHaveLength(7);
  expect(screen.getByRole('checkbox', { name: 'Росвоенипотека: взыскать задолженность по ЦЖЗ' })).toBeChecked();
  expect(screen.getByRole('alert')).toHaveTextContent('положительную');
});
