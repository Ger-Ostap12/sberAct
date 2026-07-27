import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import MortgagePropertySection from '../MortgagePropertySection';

describe('MortgagePropertySection', () => {
  it('заголовок и все метки полей недвижимости', () => {
    render(<MortgagePropertySection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Предмет ипотеки')).toBeInTheDocument();
    expect(screen.getByText('Описание объекта:')).toBeInTheDocument();
    expect(screen.getByText('Кадастровый номер:')).toBeInTheDocument();
    expect(screen.getByText('Адрес объекта:')).toBeInTheDocument();
    expect(screen.getByText('Стоимость (оценка):')).toBeInTheDocument();
    expect(screen.getByText('Начальная цена продажи:')).toBeInTheDocument();
    expect(screen.getByText('Отчёт об оценке:')).toBeInTheDocument();
  });

  it('заполняет значения из editedFields', () => {
    render(
      <MortgagePropertySection
        editedFields={{
          mortgageStartingPrice1225: '2 500 000',
          mortgageCollateralValue1224: '3 000 000',
        }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('2 500 000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('3 000 000')).toBeInTheDocument();
  });

  it('onFieldChange при правке начальной цены', () => {
    const onFieldChange = jest.fn();
    render(
      <MortgagePropertySection
        editedFields={{ mortgageStartingPrice1225: '2 500 000' }}
        onFieldChange={onFieldChange}
      />,
    );
    fireEvent.change(screen.getByDisplayValue('2 500 000'), { target: { value: '2 600 000' } });
    expect(onFieldChange).toHaveBeenCalledWith('mortgageStartingPrice1225', '2 600 000');
  });
});
