import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import CoborrowerSection from '../CoborrowerSection';
import { PartyLite } from '../../../../types';

const makeParty = (over: Partial<PartyLite> = {}): PartyLite => ({
  id: 'cb-1',
  name: 'Иванов Иван Иванович',
  inn: '616100000000',
  address: 'г. Ростов-на-Дону, ул. Ленина, 1',
  ...over,
});

describe('CoborrowerSection', () => {
  it('заголовок и пустой список без карточек', () => {
    render(
      <CoborrowerSection coborrowers={[]} onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} />,
    );
    expect(screen.getByText('Созаёмщик')).toBeInTheDocument();
    expect(screen.queryByText(/Созаёмщик 1/)).not.toBeInTheDocument();
  });

  it('рендерит карточку с ФИО/ИНН/адресом', () => {
    render(
      <CoborrowerSection
        coborrowers={[makeParty()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText('Созаёмщик 1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Иванов Иван Иванович')).toBeInTheDocument();
    expect(screen.getByDisplayValue('616100000000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('г. Ростов-на-Дону, ул. Ленина, 1')).toBeInTheDocument();
  });

  it('onAdd по кнопке «Добавить созаёмщика»', () => {
    const onAdd = jest.fn();
    render(
      <CoborrowerSection coborrowers={[]} onUpdate={() => {}} onAdd={onAdd} onRemove={() => {}} />,
    );
    fireEvent.click(screen.getByText('Добавить созаёмщика'));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('onUpdate при правке ФИО', () => {
    const onUpdate = jest.fn();
    render(
      <CoborrowerSection
        coborrowers={[makeParty()]}
        onUpdate={onUpdate}
        onAdd={() => {}}
        onRemove={() => {}}
      />,
    );
    fireEvent.change(screen.getByDisplayValue('Иванов Иван Иванович'), {
      target: { value: 'Петров Пётр' },
    });
    expect(onUpdate).toHaveBeenCalledWith(0, 'name', 'Петров Пётр');
  });
});
