import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import SolidaryLiabilitySection from '../SolidaryLiabilitySection';

describe('SolidaryLiabilitySection', () => {
  it('рендерит чекбокс, по умолчанию снят', () => {
    render(<SolidaryLiabilitySection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Солидарность')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Солидарное' })).not.toBeChecked();
  });

  it('отражает уже выставленный solidaryLiability', () => {
    render(<SolidaryLiabilitySection editedFields={{ solidaryLiability: 'true' }} onFieldChange={() => {}} />);
    expect(screen.getByRole('checkbox', { name: 'Солидарное' })).toBeChecked();
  });

  it('клик по пустому чекбоксу пишет solidaryLiability="true"', () => {
    const onFieldChange = jest.fn();
    render(<SolidaryLiabilitySection editedFields={{}} onFieldChange={onFieldChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Солидарное' }));
    expect(onFieldChange).toHaveBeenCalledWith('solidaryLiability', 'true');
  });

  it('снятие галочки пишет пустую строку, а не "false"', () => {
    // Строка 'false' на бэкенде считалась бы заполненным полем — отсюда проверка.
    const onFieldChange = jest.fn();
    render(<SolidaryLiabilitySection editedFields={{ solidaryLiability: 'true' }} onFieldChange={onFieldChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Солидарное' }));
    expect(onFieldChange).toHaveBeenCalledWith('solidaryLiability', '');
  });
});
