import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import PaymentOrdersSection from '../PaymentOrdersSection';

// Блок вынесен из «Финансовых данных»: те скрыты у самобанкрота, а даты ПП нужны
// юристу при любом заявителе (маркеры [80]/[81]).

describe('PaymentOrdersSection', () => {
  it('рендерит обе даты и показывает значения в формате поля даты', () => {
    render(
      <PaymentOrdersSection
        editedFields={{ ppDepositDate80: '15.09.2026', ppStateDutyDate81: '20.09.2026' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText('Платёжные поручения')).toBeInTheDocument();
    expect(screen.getByText('Дата ПП депозит:')).toBeInTheDocument();
    expect(screen.getByText('Дата ПП ГП:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2026-09-15')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2026-09-20')).toBeInTheDocument();
  });

  it('правка даты уходит наверх в формате документа', () => {
    const changes: Array<[string, string]> = [];
    render(
      <PaymentOrdersSection
        editedFields={{ ppDepositDate80: '15.09.2026' }}
        onFieldChange={(field, value) => changes.push([field, value])}
      />,
    );
    const input = screen.getByDisplayValue('2026-09-15');
    fireEvent.change(input, { target: { value: '2026-09-16' } });
    fireEvent.blur(input);
    expect(changes).toContainEqual(['ppDepositDate80', '16.09.2026']);
  });

  it('пустые даты не падают', () => {
    render(<PaymentOrdersSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getAllByDisplayValue('')).toHaveLength(2);
  });
});
