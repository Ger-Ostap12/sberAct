import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import FinancesSection from '../FinancesSection';

// Секция «Финансовые данные»: для кредитора-ФНС раскладка перестраивается в 4 подблока
// по очередям реестра; для обычного банка — плоский общий блок. Проверяем обе ветки и
// проброс правок через onFieldChange (см. память fns-queue-finances).

describe('FinancesSection — обычный кредитор (не ФНС)', () => {
  it('рендерит плоский блок, без подблоков очередей', () => {
    render(<FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} />);
    expect(screen.getByText('Проценты:')).toBeInTheDocument();
    expect(screen.getByText('Банкротная госпошлина:')).toBeInTheDocument();
    expect(screen.queryByText('Первая очередь')).not.toBeInTheDocument();
    expect(screen.queryByText('Общая информация')).not.toBeInTheDocument();
  });
});

describe('FinancesSection — кредитор ФНС', () => {
  const fns = 'ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области';

  it('рендерит 4 подблока (Общая информация + 3 очереди), без банкротной ГП', () => {
    render(<FinancesSection editedFields={{ creditorName: fns }} onFieldChange={() => {}} />);
    expect(screen.getByText('Общая информация')).toBeInTheDocument();
    expect(screen.getByText('Первая очередь')).toBeInTheDocument();
    expect(screen.getByText('Вторая очередь')).toBeInTheDocument();
    expect(screen.getByText('Третья очередь')).toBeInTheDocument();
    // Новые ФНС-строки присутствуют; банкротной ГП у ФНС нет.
    expect(screen.getAllByText('Недоимка:').length).toBe(3);
    expect(screen.getAllByText('НДФЛ:').length).toBe(3);
    expect(screen.queryByText('Банкротная госпошлина:')).not.toBeInTheDocument();
  });

  it('отображает значения ФНС-полей и пробрасывает правки', () => {
    const onFieldChange = jest.fn();
    render(
      <FinancesSection
        editedFields={{ creditorName: fns, fnsQ3LoanDebt: '745 735,35' }}
        onFieldChange={onFieldChange}
      />,
    );
    const input = screen.getByDisplayValue('745 735,35');
    fireEvent.change(input, { target: { value: '1000,50' } });
    expect(onFieldChange).toHaveBeenCalledWith('fnsQ3LoanDebt', '1000.50');
  });
});
