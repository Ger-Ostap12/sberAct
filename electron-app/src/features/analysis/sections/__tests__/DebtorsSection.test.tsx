import React from 'react';
import { render, screen } from '@testing-library/react';
import DebtorsSection from '../DebtorsSection';
import { Debtor } from '../../../../types';

// Карточки должников строятся ОТДЕЛЬНЫМ путём, мимо `fields` (ловушка §J.3), поэтому
// у претензий контракта к ним свои ключи — `debtors[N].address`, а не плоское имя
// поля. Тесты держат именно этот стык: ошибка в формате ключа = молчащая подсветка
// при живой претензии в списке сверху.

function debtor(over: Partial<Debtor> = {}): Debtor {
  return { id: '1', name: 'Иванов Иван Иванович', ...over } as Debtor;
}

const noop = () => {};

describe('DebtorsSection — подсветка подозрительных полей', () => {
  it('без fieldQuality ничего не подсвечено', () => {
    render(
      <DebtorsSection
        debtors={[debtor({ address: 'ПАО Сбер', inn: '612102429513' })]}
        entityType="individual"
        onUpdate={noop}
        onAdd={noop}
        onRemove={noop}
      />,
    );
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });

  it('адрес карточки уровня low подсвечивается', () => {
    render(
      <DebtorsSection
        debtors={[debtor({ address: '' })]}
        entityType="individual"
        onUpdate={noop}
        onAdd={noop}
        onRemove={noop}
        fieldQuality={{
          'debtors[0].address': {
            level: 'low',
            reasons: ['значение не содержит ни одного адресного признака'],
            cleared: true,
          },
        }}
      />,
    );
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
  });

  it('ИНН карточки: помечен, но значение осталось (реквизиты не чистим)', () => {
    render(
      <DebtorsSection
        debtors={[debtor({ inn: '612102429513' })]}
        entityType="individual"
        onUpdate={noop}
        onAdd={noop}
        onRemove={noop}
        fieldQuality={{
          'debtors[0].inn': {
            level: 'low',
            reasons: ['INN не проходит контрольную сумму'],
            cleared: false,
          },
        }}
      />,
    );
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
    expect(screen.getByDisplayValue('612102429513')).toBeInTheDocument();
  });

  it('претензия ко ВТОРОЙ карточке не красит первую', () => {
    // Многодолжниковые заявления — норма; ключ несёт индекс, и перепутать его
    // значило бы показать юристу ошибку не в том должнике.
    render(
      <DebtorsSection
        debtors={[debtor({ id: '1', address: '344068, г. Ростов-на-Дону, ул. Ленина, д. 5' }),
          debtor({ id: '2', name: 'Петров Пётр Петрович', address: '' })]}
        entityType="individual"
        onUpdate={noop}
        onAdd={noop}
        onRemove={noop}
        fieldQuality={{
          'debtors[1].address': { level: 'low', reasons: ['проверить'], cleared: true },
        }}
      />,
    );
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
  });

  it('ОГРНИП подсвечивается у ИП (поле переключается по типу лица)', () => {
    render(
      <DebtorsSection
        debtors={[debtor({ ogrnip: '317619600232839' })]}
        entityType="ip"
        onUpdate={noop}
        onAdd={noop}
        onRemove={noop}
        fieldQuality={{
          'debtors[0].ogrnip': { level: 'low', reasons: ['OGRNIP не проходит контрольную сумму'], cleared: false },
        }}
      />,
    );
    expect(screen.getByText('ОГРНИП:')).toBeInTheDocument();
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
  });

  it('medium не подсвечивается', () => {
    render(
      <DebtorsSection
        debtors={[debtor({ address: '344068, г. Ростов-на-Дону, ул. Ленина, д. 5' })]}
        entityType="individual"
        onUpdate={noop}
        onAdd={noop}
        onRemove={noop}
        fieldQuality={{ 'debtors[0].address': { level: 'medium', reasons: [] } }}
      />,
    );
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });
});
