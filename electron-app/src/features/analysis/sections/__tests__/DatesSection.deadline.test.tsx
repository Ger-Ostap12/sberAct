import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DatesSection from '../DatesSection';

describe('DatesSection — срок возражений', () => {
  it('свободный текст сохраняется как есть', () => {
    const onFieldChange = jest.fn();
    render(<DatesSection editedFields={{}} onFieldChange={onFieldChange} mode="mortgage" />);
    const input = screen.getByPlaceholderText('ДД.ММ.ГГГГ или текст');
    fireEvent.change(input, { target: { value: 'в течение 30 дней' } });
    expect(onFieldChange).toHaveBeenCalledWith('objectionsDeadline18', 'в течение 30 дней');
  });

  it('цифры маскируются в ДД.ММ.ГГГГ', () => {
    const onFieldChange = jest.fn();
    render(<DatesSection editedFields={{}} onFieldChange={onFieldChange} mode="mortgage" />);
    fireEvent.change(screen.getByPlaceholderText('ДД.ММ.ГГГГ или текст'), { target: { value: '10042026' } });
    expect(onFieldChange).toHaveBeenCalledWith('objectionsDeadline18', '10.04.2026');
  });

  it('есть кнопка календаря', () => {
    render(<DatesSection editedFields={{}} onFieldChange={() => {}} mode="mortgage" />);
    expect(screen.getByLabelText('Выбрать дату в календаре')).toBeInTheDocument();
  });

  it('выбор даты в календаре пишет ДД.ММ.ГГГГ', () => {
    const onFieldChange = jest.fn();
    const { container } = render(
      <DatesSection editedFields={{ objectionsDeadline18: 'в течение 30 дней' }} onFieldChange={onFieldChange} mode="mortgage" />
    );
    // В секции несколько input[type=date]; наш — скрытый, при поле срока.
    const picker = container.querySelector('input[type="date"][aria-hidden="true"]') as HTMLInputElement;
    expect(picker).toBeTruthy();
    fireEvent.change(picker, { target: { value: '2026-04-10' } });
    expect(onFieldChange).toHaveBeenCalledWith('objectionsDeadline18', '10.04.2026');
  });

  it('свободный текст не ломает календарь (значение пустое, поле цело)', () => {
    const { container } = render(
      <DatesSection editedFields={{ objectionsDeadline18: 'в течение 30 дней' }} onFieldChange={() => {}} mode="mortgage" />
    );
    const picker = container.querySelector('input[type="date"][aria-hidden="true"]') as HTMLInputElement;
    expect(picker.value).toBe('');
    expect((screen.getByPlaceholderText('ДД.ММ.ГГГГ или текст') as HTMLInputElement).value).toBe('в течение 30 дней');
  });
});
