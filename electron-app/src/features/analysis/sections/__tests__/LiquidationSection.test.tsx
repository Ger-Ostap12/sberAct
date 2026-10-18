import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import LiquidationSection from '../LiquidationSection';

// Блок «Объявление о ликвидации»: наименование ликвидатора (авто), номер заявления
// и дата ликвидации (ввод пользователя).
describe('LiquidationSection', () => {
  it('рендерит три поля и заполняет из editedFields', () => {
    render(
      <LiquidationSection
        editedFields={{
          liquidatorName: 'Оленченко Олег Игоревич',
          liquidationApplicationNumber: '36504402',
          liquidationDate: '01.06.2026',
        }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText('Объявление о ликвидации')).toBeInTheDocument();
    expect(screen.getByText('Наименование ликвидатора:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Оленченко Олег Игоревич')).toBeInTheDocument();
    expect(screen.getByDisplayValue('36504402')).toBeInTheDocument();
    expect(screen.getByDisplayValue('01.06.2026')).toBeInTheDocument();
  });

  it('номер заявления принимает только цифры', () => {
    const onFieldChange = jest.fn();
    render(<LiquidationSection editedFields={{}} onFieldChange={onFieldChange} />);
    // Поля по порядку: наименование ликвидатора, номер заявления, дата ликвидации.
    const input = screen.getAllByRole('textbox')[1];
    const поле1 = input;
    fireEvent.change(поле1, { target: { value: '12a3-4' } });
    fireEvent.blur(поле1);
    expect(onFieldChange).toHaveBeenCalledWith('liquidationApplicationNumber', '1234');
  });

  it('дата ликвидации маскируется в дд.мм.гггг', () => {
    const onFieldChange = jest.fn();
    render(<LiquidationSection editedFields={{}} onFieldChange={onFieldChange} />);
    const input = screen.getAllByRole('textbox')[2];
    const поле2 = input;
    fireEvent.change(поле2, { target: { value: '01062026' } });
    fireEvent.blur(поле2);
    expect(onFieldChange).toHaveBeenCalledWith('liquidationDate', '01.06.2026');
  });
});
