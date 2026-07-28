import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import MortgagePropertySection from '../MortgagePropertySection';
import { MortgageProperty } from '../../../../types';

const makeProperty = (over: Partial<MortgageProperty> = {}): MortgageProperty => ({
  id: 'mp-1',
  description: '',
  cadastralNumber: '',
  address: '',
  value: '',
  startingPrice: '',
  appraisalReport: '',
  ...over,
});

describe('MortgagePropertySection', () => {
  it('заголовок и все метки полей недвижимости для одного предмета', () => {
    render(
      <MortgagePropertySection
        mortgageProperties={[makeProperty()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText('Предмет ипотеки')).toBeInTheDocument();
    expect(screen.getByText('Предмет ипотеки 1')).toBeInTheDocument();
    expect(screen.getByText('Описание объекта:')).toBeInTheDocument();
    expect(screen.getByText('Кадастровый номер:')).toBeInTheDocument();
    expect(screen.getByText('Адрес объекта:')).toBeInTheDocument();
    expect(screen.getByText('Стоимость (оценка):')).toBeInTheDocument();
    expect(screen.getByText('Начальная продажная цена:')).toBeInTheDocument();
    expect(screen.getByText('Стратегия определения НПЦ:')).toBeInTheDocument();
    expect(screen.getByText('Запись в ЕГРН:')).toBeInTheDocument();
    expect(screen.getByText('Дата записи ЕГРН:')).toBeInTheDocument();
    expect(screen.getByText('Отчёт об оценке:')).toBeInTheDocument();
    // ДДУ-поля показываются только при mortgageKind='ddu'.
    expect(screen.queryByText('Договор долевого участия:')).not.toBeInTheDocument();
    expect(screen.queryByText('Дата ДДУ:')).not.toBeInTheDocument();
  });

  it('ДДУ: показываются поля договора долевого участия', () => {
    render(
      <MortgagePropertySection
        mortgageProperties={[makeProperty()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
        mortgageKind="ddu"
      />,
    );
    expect(screen.getByText('Договор долевого участия:')).toBeInTheDocument();
    expect(screen.getByText('Дата ДДУ:')).toBeInTheDocument();
  });

  it('заполняет значения из объекта предмета', () => {
    render(
      <MortgagePropertySection
        mortgageProperties={[makeProperty({ startingPrice: '2 500 000', value: '3 000 000' })]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('2 500 000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('3 000 000')).toBeInTheDocument();
  });

  it('несколько предметов — карточки нумеруются', () => {
    render(
      <MortgagePropertySection
        mortgageProperties={[
          makeProperty({ id: 'mp-1', description: 'квартира' }),
          makeProperty({ id: 'mp-2', description: 'машиноместо' }),
        ]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText('Предмет ипотеки 1')).toBeInTheDocument();
    expect(screen.getByText('Предмет ипотеки 2')).toBeInTheDocument();
    expect(screen.getByDisplayValue('квартира')).toBeInTheDocument();
    expect(screen.getByDisplayValue('машиноместо')).toBeInTheDocument();
  });

  it('onUpdate при правке начальной цены (с индексом карточки)', () => {
    const onUpdate = jest.fn();
    render(
      <MortgagePropertySection
        mortgageProperties={[makeProperty(), makeProperty({ id: 'mp-2', startingPrice: '2 500 000' })]}
        onUpdate={onUpdate}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    fireEvent.change(screen.getByDisplayValue('2 500 000'), { target: { value: '2 600 000' } });
    expect(onUpdate).toHaveBeenCalledWith(1, 'startingPrice', '2 600 000');
  });

  it('кнопка «Добавить предмет ипотеки» вызывает onAdd', () => {
    const onAdd = jest.fn();
    render(
      <MortgagePropertySection
        mortgageProperties={[makeProperty()]}
        onUpdate={() => {}}
        onAdd={onAdd}
        onRemove={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Добавить предмет ипотеки' }));
    expect(onAdd).toHaveBeenCalled();
  });

  it('крестик удаления вызывает onRemove с индексом', () => {
    const onRemove = jest.fn();
    render(
      <MortgagePropertySection
        mortgageProperties={[makeProperty(), makeProperty({ id: 'mp-2' })]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={onRemove}
      />,
    );
    const buttons = screen.getAllByLabelText('Удалить предмет ипотеки');
    fireEvent.click(buttons[1]);
    expect(onRemove).toHaveBeenCalledWith(1);
  });
});
