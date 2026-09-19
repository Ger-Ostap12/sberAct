import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import CreditorsListSection from '../CreditorsListSection';
import { Creditor } from '../../../../types';

const cred = (over: Partial<Creditor> = {}): Creditor => ({
  id: 'cr-1',
  name: '',
  address: '',
  inn: '',
  ogrn: '',
  ...over,
});

describe('CreditorsListSection — список кредиторов самобанкрота', () => {
  it('рисует карточку на каждого кредитора с нумерацией', () => {
    render(
      <CreditorsListSection
        creditors={[
          cred({ id: 'cr-1', name: 'ООО МКК «Русинтерфинанс»' }),
          cred({ id: 'cr-2', name: 'ПАО «Сбербанк»' }),
        ]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText('Кредитор 1')).toBeInTheDocument();
    expect(screen.getByText('Кредитор 2')).toBeInTheDocument();
    expect(screen.getByDisplayValue('ООО МКК «Русинтерфинанс»')).toBeInTheDocument();
    expect(screen.getByDisplayValue('ПАО «Сбербанк»')).toBeInTheDocument();
  });

  it('показывает все четыре поля карточки', () => {
    render(
      <CreditorsListSection
        creditors={[cred()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText('Наименование:')).toBeInTheDocument();
    expect(screen.getByText('Адрес:')).toBeInTheDocument();
    expect(screen.getByText('ИНН:')).toBeInTheDocument();
    expect(screen.getByText('ОГРН:')).toBeInTheDocument();
  });

  it('пустой список: карточек нет, кнопка добавления есть', () => {
    render(
      <CreditorsListSection
        creditors={[]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.queryByText('Кредитор 1')).not.toBeInTheDocument();
    expect(screen.getByText('Добавить кредитора')).toBeInTheDocument();
  });

  it('правка наименования вызывает onUpdate с индексом и полем', () => {
    const onUpdate = jest.fn();
    render(
      <CreditorsListSection
        creditors={[cred(), cred({ id: 'cr-2' })]}
        onUpdate={onUpdate}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    const поля = screen.getAllByRole('textbox');
    // Порядок полей в карточке: наименование, адрес, ИНН, ОГРН.
    fireEvent.change(поля[4], { target: { value: 'АО «Тбанк»' } });
    expect(onUpdate).toHaveBeenCalledWith(1, 'name', 'АО «Тбанк»');
  });

  it('удаление вызывает onRemove с индексом карточки', () => {
    const onRemove = jest.fn();
    render(
      <CreditorsListSection
        creditors={[cred(), cred({ id: 'cr-2' })]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getAllByLabelText('Удалить кредитора')[1]);
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('кнопка вызывает onAdd', () => {
    const onAdd = jest.fn();
    render(
      <CreditorsListSection
        creditors={[]}
        onUpdate={() => {}}
        onAdd={onAdd}
        onRemove={() => {}}
      />,
    );
    fireEvent.click(screen.getByText('Добавить кредитора'));
    expect(onAdd).toHaveBeenCalled();
  });
});
