import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ObligationsSection from '../ObligationsSection';
import { Obligation } from '../../../../types';

const obl: Obligation = {
  id: 'o1',
  contractNumber: '111',
  contractDate: '01.02.2024',
  obligationType: 'Кредитный договор',
};

describe('ObligationsSection — период взыскания (ипотека)', () => {
  it('банкротство: периода взыскания нет', () => {
    render(<ObligationsSection obligations={[obl]} onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} />);
    expect(screen.queryByText('Период взыскания с:')).not.toBeInTheDocument();
    expect(screen.queryByText('Период взыскания по:')).not.toBeInTheDocument();
  });

  it('ипотека: у обязательства появляются даты «с/по»', () => {
    render(
      <ObligationsSection obligations={[obl]} onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} mode="mortgage" />,
    );
    expect(screen.getByText('Период взыскания с:')).toBeInTheDocument();
    expect(screen.getByText('Период взыскания по:')).toBeInTheDocument();
  });

  it('ипотека: правка даты «с» патчит collectionPeriodFrom', () => {
    const onUpdate = jest.fn();
    render(
      <ObligationsSection obligations={[obl]} onUpdate={onUpdate} onAdd={() => {}} onRemove={() => {}} mode="mortgage" />,
    );
    // Первый date-инпут «Период взыскания с» (после «Дата договора»).
    const dateInputs = document.querySelectorAll('input[type="date"]');
    // индекс 1: [0]=Дата договора, [1]=Период взыскания с, [2]=по
    fireEvent.change(dateInputs[1], { target: { value: '2023-01-15' } });
    expect(onUpdate).toHaveBeenCalledWith(0, { collectionPeriodFrom: '15.01.2023' });
  });
});
