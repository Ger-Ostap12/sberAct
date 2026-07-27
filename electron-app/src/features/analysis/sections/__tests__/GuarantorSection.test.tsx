import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import GuarantorSection from '../GuarantorSection';
import { PartyLite } from '../../../../types';

const makeParty = (over: Partial<PartyLite> = {}): PartyLite => ({
  id: 'g-1',
  name: 'Сидоров Сидор Сидорович',
  inn: '616200000000',
  address: 'г. Таганрог, ул. Мира, 5',
  ...over,
});

describe('GuarantorSection', () => {
  it('заголовок «Информация о поручителе» и пустой список', () => {
    render(
      <GuarantorSection guarantors={[]} onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} />,
    );
    expect(screen.getByText('Информация о поручителе')).toBeInTheDocument();
    expect(screen.queryByText(/Поручитель 1/)).not.toBeInTheDocument();
  });

  it('рендерит карточку с ФИО/ИНН/адресом', () => {
    render(
      <GuarantorSection
        guarantors={[makeParty()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText('Поручитель 1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Сидоров Сидор Сидорович')).toBeInTheDocument();
    expect(screen.getByDisplayValue('616200000000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('г. Таганрог, ул. Мира, 5')).toBeInTheDocument();
  });

  it('onRemove по кнопке удаления', () => {
    const onRemove = jest.fn();
    render(
      <GuarantorSection
        guarantors={[makeParty()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByLabelText('Удалить поручителя'));
    expect(onRemove).toHaveBeenCalledWith(0);
  });

  it('onAdd по кнопке «Добавить поручителя»', () => {
    const onAdd = jest.fn();
    render(
      <GuarantorSection guarantors={[]} onUpdate={() => {}} onAdd={onAdd} onRemove={() => {}} />,
    );
    fireEvent.click(screen.getByText('Добавить поручителя'));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });
});
