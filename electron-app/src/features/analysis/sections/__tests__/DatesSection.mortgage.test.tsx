import React from 'react';
import { render, screen } from '@testing-library/react';
import DatesSection from '../DatesSection';

describe('DatesSection — режим ипотеки', () => {
  it('банкротство: метка «Дата принятия определения», банкротные сроки показаны', () => {
    render(<DatesSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Дата принятия определения:')).toBeInTheDocument();
    expect(screen.getByText('Установка срока на предоставление возражений:')).toBeInTheDocument();
    expect(screen.getByText('На рассмотрение заявления в срок:')).toBeInTheDocument();
    expect(screen.getByText('Срок для оставления без движения:')).toBeInTheDocument();
  });

  it('ипотека: метка «Дата принятия решения»; возражения остаются, рассмотрение/без движения скрыты', () => {
    render(<DatesSection editedFields={{}} onFieldChange={() => {}} mode="mortgage" />);
    expect(screen.getByText('Дата принятия решения:')).toBeInTheDocument();
    expect(screen.queryByText('Дата принятия определения:')).not.toBeInTheDocument();
    // «Установка срока на предоставление возражений» возвращена в ипотеку.
    expect(screen.getByText('Установка срока на предоставление возражений:')).toBeInTheDocument();
    expect(screen.queryByText('На рассмотрение заявления в срок:')).not.toBeInTheDocument();
    expect(screen.queryByText('Срок для оставления без движения:')).not.toBeInTheDocument();
  });

  it('ипотека: общие даты остаются (направление/поступление/заседание)', () => {
    render(<DatesSection editedFields={{}} onFieldChange={() => {}} mode="mortgage" />);
    expect(screen.getByText('Дата направления в суд:')).toBeInTheDocument();
    expect(screen.getByText('Дата поступления заявления в суд (согласно штампу):')).toBeInTheDocument();
    expect(screen.getByText('Дата и время судебного заседания:')).toBeInTheDocument();
  });

  it('«Дата извещения» есть только в ипотеке', () => {
    const { rerender } = render(<DatesSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.queryByText('Дата извещения:')).not.toBeInTheDocument();
    rerender(<DatesSection editedFields={{}} onFieldChange={() => {}} mode="mortgage" />);
    expect(screen.getByText('Дата извещения:')).toBeInTheDocument();
  });
});
