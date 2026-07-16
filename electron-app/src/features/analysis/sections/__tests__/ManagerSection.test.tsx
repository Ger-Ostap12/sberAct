import React from 'react';
import { render, screen } from '@testing-library/react';
import ManagerSection from '../ManagerSection';

// Поле «Саморегулируемая организация» показывается только при showSro (инициирующие
// финальные акты). ФИО/адрес — всегда.
describe('ManagerSection — поле СРО', () => {
  it('без showSro поля СРО нет', () => {
    render(<ManagerSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.queryByText('Саморегулируемая организация:')).not.toBeInTheDocument();
  });

  it('с showSro поле СРО показано и заполнено из sroName', () => {
    render(
      <ManagerSection
        editedFields={{ sroName: 'Ассоциация "Содействие"' }}
        onFieldChange={() => {}}
        showSro
      />,
    );
    expect(screen.getByText('Саморегулируемая организация:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Ассоциация "Содействие"')).toBeInTheDocument();
  });
});

// Поле «ФИО» управляющего показывается по умолчанию; скрывается при showFio={false}
// (банк-инициирование, самобанкрот — управляющий ещё не утверждён).
describe('ManagerSection — поле ФИО', () => {
  it('по умолчанию поле ФИО показано', () => {
    render(<ManagerSection editedFields={{ managerName: 'Иванов И.И.' }} onFieldChange={() => {}} />);
    expect(screen.getByText('ФИО:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Иванов И.И.')).toBeInTheDocument();
  });

  it('при showFio={false} поля ФИО нет, адрес остаётся', () => {
    render(
      <ManagerSection
        editedFields={{ managerName: 'Иванов И.И.' }}
        onFieldChange={() => {}}
        showFio={false}
      />,
    );
    expect(screen.queryByText('ФИО:')).not.toBeInTheDocument();
    expect(screen.getByText('Адрес:')).toBeInTheDocument();
  });
});
