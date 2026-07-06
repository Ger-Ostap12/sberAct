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
