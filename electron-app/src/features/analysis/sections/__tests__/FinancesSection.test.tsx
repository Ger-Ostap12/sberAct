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

  it('сверка очереди: подытог = Σ строк → ✓; расхождение → ⚠', () => {
    const { rerender } = render(
      <FinancesSection
        editedFields={{ creditorName: fns, fnsQ3Total: '100,00', fnsQ3LoanDebt: '70,00', fnsQ3Forfeit: '30,00' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/Итог очереди: сходится/)).toBeInTheDocument();

    rerender(
      <FinancesSection
        editedFields={{ creditorName: fns, fnsQ3Total: '100,00', fnsQ3LoanDebt: '70,00', fnsQ3Forfeit: '5,00' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/Итог очереди:.*расхождение/)).toBeInTheDocument();
  });

  it('итоговая сверка: Общая сумма долга = Σ подытогов очередей', () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: fns, totalDebt: '300,00', fnsQ1Total: '100,00', fnsQ2Total: '100,00', fnsQ3Total: '100,00' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/Общая сумма долга: сходится/)).toBeInTheDocument();
  });

  it('флаг fnsTotalComputed=1 → предупреждение «вычислена»', () => {
    const { rerender } = render(
      <FinancesSection editedFields={{ creditorName: fns, totalDebt: '300,00' }} onFieldChange={() => {}} />,
    );
    expect(screen.queryByText(/вычислена как сумма подытогов/)).not.toBeInTheDocument();

    rerender(
      <FinancesSection
        editedFields={{ creditorName: fns, totalDebt: '300,00', fnsTotalComputed: '1' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/вычислена как сумма подытогов/)).toBeInTheDocument();
  });
});
