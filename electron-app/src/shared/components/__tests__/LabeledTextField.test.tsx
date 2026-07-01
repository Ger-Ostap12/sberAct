import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import LabeledField from '../LabeledField';
import LabeledTextField from '../LabeledTextField';

describe('LabeledField', () => {
  it('показывает метку и содержимое', () => {
    render(
      <LabeledField label="Название суда:">
        <span>содержимое</span>
      </LabeledField>
    );
    expect(screen.getByText('Название суда:')).toBeInTheDocument();
    expect(screen.getByText('содержимое')).toBeInTheDocument();
  });
});

describe('LabeledTextField', () => {
  it('рендерит метку и текущее значение', () => {
    render(<LabeledTextField label="Номер дела:" value="А53-123" onChange={() => {}} />);
    expect(screen.getByText('Номер дела:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('А53-123')).toBeInTheDocument();
  });

  it('вызывает onChange с новым значением при вводе', () => {
    const onChange = jest.fn();
    render(<LabeledTextField label="Кредитор:" value="" onChange={onChange} />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'ПАО Сбербанк' } });
    expect(onChange).toHaveBeenCalledWith('ПАО Сбербанк');
  });

  it('прокидывает placeholder', () => {
    render(
      <LabeledTextField
        label="Суд:"
        value=""
        onChange={() => {}}
        placeholder="Арбитражный суд Ростовской области"
      />
    );
    expect(
      screen.getByPlaceholderText('Арбитражный суд Ростовской области')
    ).toBeInTheDocument();
  });
});
