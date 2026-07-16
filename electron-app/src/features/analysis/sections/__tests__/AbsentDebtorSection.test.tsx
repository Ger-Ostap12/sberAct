import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import AbsentDebtorSection from '../AbsentDebtorSection';

// Блок «Информация по счетам»: три даты, все вводит пользователь (в заявлении их нет).
describe('AbsentDebtorSection', () => {
  it('рендерит три поля и заполняет из editedFields', () => {
    render(
      <AbsentDebtorSection
        editedFields={{
          lastTaxReportDate: '25.04.2024',
          lastAccountingReportDate: '31.03.2024',
          lastAccountOperationDate: '14.12.2024',
        }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText('Информация по счетам')).toBeInTheDocument();
    expect(screen.getByText('Дата последней налоговой отчётности:')).toBeInTheDocument();
    expect(screen.getByText('Дата последней бухгалтерской отчётности:')).toBeInTheDocument();
    expect(screen.getByText('Последняя операция по расчётным счетам:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('25.04.2024')).toBeInTheDocument();
    expect(screen.getByDisplayValue('31.03.2024')).toBeInTheDocument();
    expect(screen.getByDisplayValue('14.12.2024')).toBeInTheDocument();
  });

  it('маскирует ввод в дд.мм.гггг', () => {
    const onFieldChange = jest.fn();
    render(<AbsentDebtorSection editedFields={{}} onFieldChange={onFieldChange} />);
    fireEvent.change(screen.getAllByRole('textbox')[0], { target: { value: '25042024' } });
    expect(onFieldChange).toHaveBeenCalledWith('lastTaxReportDate', '25.04.2024');
  });

  it('показывает ошибку на несуществующей дате и молчит на корректной', () => {
    const { rerender } = render(
      <AbsentDebtorSection editedFields={{ lastAccountOperationDate: '31.02.2025' }} onFieldChange={() => {}} />,
    );
    expect(screen.getByText('Введите существующую дату в формате дд.мм.гггг')).toBeInTheDocument();

    rerender(
      <AbsentDebtorSection editedFields={{ lastAccountOperationDate: '28.02.2025' }} onFieldChange={() => {}} />,
    );
    expect(screen.queryByText('Введите существующую дату в формате дд.мм.гггг')).not.toBeInTheDocument();
  });

  it('незаполненное поле ошибкой не считается', () => {
    render(<AbsentDebtorSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.queryByText('Введите существующую дату в формате дд.мм.гггг')).not.toBeInTheDocument();
  });
});
