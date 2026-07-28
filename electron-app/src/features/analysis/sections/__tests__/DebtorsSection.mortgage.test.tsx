import React from 'react';
import { render, screen } from '@testing-library/react';
import DebtorsSection from '../DebtorsSection';
import { Debtor } from '../../../../types';

const debtor: Debtor = { id: 'd1', name: 'Иванов Иван', address: 'адрес', inn: '111' };

describe('DebtorsSection — режим ипотеки (Ответчик)', () => {
  it('банкротство: заголовок «Данные должника», паспорта нет', () => {
    render(
      <DebtorsSection debtors={[debtor]} entityType="individual" onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} />,
    );
    expect(screen.getByText('Данные должника')).toBeInTheDocument();
    expect(screen.getByText('Добавить должника')).toBeInTheDocument();
    expect(screen.queryByText('Паспорт (серия):')).not.toBeInTheDocument();
  });

  it('ипотека: заголовок «Данные ответчика», кнопка «Добавить ответчика», паспорт есть', () => {
    render(
      <DebtorsSection debtors={[debtor]} entityType="individual" onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} mode="mortgage" />,
    );
    expect(screen.getByText('Данные ответчика')).toBeInTheDocument();
    expect(screen.getByText('Добавить ответчика')).toBeInTheDocument();
    expect(screen.getByText('Паспорт (серия):')).toBeInTheDocument();
    expect(screen.getByText('Паспорт (номер):')).toBeInTheDocument();
  });

  it('ипотека: подписи «ФИО:» и «Адрес ответчика:» (не «должника»)', () => {
    render(
      <DebtorsSection debtors={[debtor]} entityType="individual" onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} mode="mortgage" />,
    );
    expect(screen.getByText('ФИО:')).toBeInTheDocument();
    expect(screen.getByText('Адрес ответчика:')).toBeInTheDocument();
    expect(screen.queryByText('ФИО/наименование:')).not.toBeInTheDocument();
    expect(screen.queryByText('Адрес должника:')).not.toBeInTheDocument();
  });

  it('ипотека: невалидная серия паспорта подсвечивается', () => {
    render(
      <DebtorsSection
        debtors={[{ ...debtor, passportSeries: '60', passportNumber: '123456' }]}
        entityType="individual"
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
        mode="mortgage"
      />,
    );
    expect(screen.getByText('4 цифры')).toBeInTheDocument();
    expect(screen.queryByText('6 цифр')).not.toBeInTheDocument();
  });
});
