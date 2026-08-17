import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import MortgageKindSection from '../MortgageKindSection';

describe('MortgageKindSection', () => {
  it('рендерит радио «Ипотека»/«Военная ипотека»/«ДДУ», выбрана civil', () => {
    render(<MortgageKindSection mortgageKind="civil" onChange={() => {}} />);
    expect(screen.getByText('Вид ипотеки')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Ипотека' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Военная ипотека' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'ДДУ' })).not.toBeChecked();
  });

  it('клик по «Военная ипотека» вызывает onChange("military")', () => {
    const onChange = jest.fn();
    render(<MortgageKindSection mortgageKind="civil" onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Военная ипотека' }));
    expect(onChange).toHaveBeenCalledWith('military');
  });

  it('клик по «ДДУ» вызывает onChange("ddu")', () => {
    const onChange = jest.fn();
    render(<MortgageKindSection mortgageKind="civil" onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: 'ДДУ' }));
    expect(onChange).toHaveBeenCalledWith('ddu');
  });
});
