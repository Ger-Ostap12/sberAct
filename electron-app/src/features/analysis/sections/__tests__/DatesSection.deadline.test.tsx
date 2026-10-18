import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DatesSection from '../DatesSection';

describe('DatesSection — срок возражений', () => {
  it('свободный текст сохраняется как есть', () => {
    const onFieldChange = jest.fn();
    render(<DatesSection editedFields={{}} onFieldChange={onFieldChange} mode="mortgage" />);
    const input = screen.getByPlaceholderText('ДД.ММ.ГГГГ или текст');
    const поле1 = input;
    fireEvent.change(поле1, { target: { value: 'в течение 30 дней' } });
    fireEvent.blur(поле1);
    expect(onFieldChange).toHaveBeenCalledWith('objectionsDeadline18', 'в течение 30 дней');
  });

  it('цифры маскируются в ДД.ММ.ГГГГ', () => {
    const onFieldChange = jest.fn();
    render(<DatesSection editedFields={{}} onFieldChange={onFieldChange} mode="mortgage" />);
    const поле2 = screen.getByPlaceholderText('ДД.ММ.ГГГГ или текст');
    fireEvent.change(поле2, { target: { value: '10042026' } });
    fireEvent.blur(поле2);
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
    const поле3 = picker;
    fireEvent.change(поле3, { target: { value: '2026-04-10' } });
    fireEvent.blur(поле3);
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
