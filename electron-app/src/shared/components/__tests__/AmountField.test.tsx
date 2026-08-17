import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import AmountField from '../AmountField';

describe('AmountField — форматирование по blur', () => {
  it('вне фокуса показывает сгруппированное значение', () => {
    render(<AmountField value="123456.78" onValueChange={() => {}} />);
    expect(screen.getByDisplayValue('123 456,78')).toBeInTheDocument();
  });

  it('при фокусе показывает редактируемый вид (запятая, без пробелов)', () => {
    render(<AmountField value="123456.78" onValueChange={() => {}} />);
    const input = screen.getByDisplayValue('123 456,78');
    fireEvent.focus(input);
    expect(screen.getByDisplayValue('123456,78')).toBeInTheDocument();
  });

  it('ввод через запятую → канон с точкой в onValueChange', () => {
    const onValueChange = jest.fn();
    render(<AmountField value="" onValueChange={onValueChange} />);
    const input = screen.getByRole('textbox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '123 456,7' } });
    expect(onValueChange).toHaveBeenLastCalledWith('123456.7');
  });

  it('после blur снова форматирует', () => {
    const Wrapper = () => {
      const [v, setV] = React.useState('1000000');
      return <AmountField value={v} onValueChange={setV} />;
    };
    render(<Wrapper />);
    const input = screen.getByDisplayValue('1 000 000');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '2000000.5' } });
    fireEvent.blur(input);
    expect(screen.getByDisplayValue('2 000 000,5')).toBeInTheDocument();
  });
});
