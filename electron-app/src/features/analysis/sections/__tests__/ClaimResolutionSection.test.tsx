import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ClaimResolutionSection from '../ClaimResolutionSection';

describe('ClaimResolutionSection', () => {
  it('рендерит три радио, по умолчанию ничего не выбрано', () => {
    render(<ClaimResolutionSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Удовлетворение иска')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Удовлетворить полностью' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Удовлетворить частично' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Отказать в удовлетворении' })).not.toBeChecked();
  });

  it('отражает уже выбранное значение claimResolution', () => {
    render(<ClaimResolutionSection editedFields={{ claimResolution: 'partial' }} onFieldChange={() => {}} />);
    expect(screen.getByRole('radio', { name: 'Удовлетворить частично' })).toBeChecked();
  });

  it('клик по «Отказать в удовлетворении» пишет claimResolution="deny"', () => {
    const onFieldChange = jest.fn();
    render(<ClaimResolutionSection editedFields={{}} onFieldChange={onFieldChange} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Отказать в удовлетворении' }));
    expect(onFieldChange).toHaveBeenCalledWith('claimResolution', 'deny');
  });
});
