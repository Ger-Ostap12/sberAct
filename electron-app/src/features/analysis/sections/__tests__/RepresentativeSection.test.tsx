import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import RepresentativeSection from '../RepresentativeSection';
import RespondentRepresentativeSection from '../RespondentRepresentativeSection';

describe('RepresentativeSection (истца)', () => {
  it('заголовок, ФИО и срок доверенности (с/по), без паспорта', () => {
    render(<RepresentativeSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Представитель истца')).toBeInTheDocument();
    expect(screen.getByText('ФИО:')).toBeInTheDocument();
    expect(screen.getByText('Доверенность с:')).toBeInTheDocument();
    expect(screen.getByText('Доверенность по:')).toBeInTheDocument();
    expect(screen.queryByText('Паспорт (серия):')).not.toBeInTheDocument();
  });

  it('ФИО и даты правятся через onFieldChange', () => {
    const onFieldChange = jest.fn();
    render(
      <RepresentativeSection
        editedFields={{ representativeName: 'Иванов И.И.' }}
        onFieldChange={onFieldChange}
      />,
    );
    fireEvent.change(screen.getByDisplayValue('Иванов И.И.'), { target: { value: 'Петров П.П.' } });
    expect(onFieldChange).toHaveBeenCalledWith('representativeName', 'Петров П.П.');
  });
});

describe('RespondentRepresentativeSection (ответчика)', () => {
  it('заголовок и только ФИО', () => {
    render(<RespondentRepresentativeSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Представитель ответчика')).toBeInTheDocument();
    expect(screen.getByText('ФИО:')).toBeInTheDocument();
    expect(screen.queryByText('Доверенность с:')).not.toBeInTheDocument();
  });

  it('ФИО правится через onFieldChange', () => {
    const onFieldChange = jest.fn();
    render(<RespondentRepresentativeSection editedFields={{}} onFieldChange={onFieldChange} />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Сидоров С.С.' } });
    expect(onFieldChange).toHaveBeenCalledWith('respondentRepresentativeName', 'Сидоров С.С.');
  });
});
