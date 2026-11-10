import React, { useState } from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DateInput from '../DateInput';

const interact = async <T,>(action: () => Promise<T>): Promise<T> => {
  let result!: T;
  await act(async () => { result = await action(); });
  return result;
};

// Каждая клавиша — отдельное событие пользователя с завершённым обновлением React.
const keyboard = async (user: ReturnType<typeof userEvent.setup>, text: string) => {
  for (const key of text.match(/\{[^}]+\}|./gu) || []) {
    await interact(() => user.keyboard(key));
  }
};

const setup = (initial = '', options: { withTime?: boolean; allowText?: boolean } = {}) => {
  const changed = jest.fn();
  const Form = () => {
    const [value, setValue] = useState(initial);
    return <DateInput delay={0} label="Дата" value={value} onChange={next => { changed(next); setValue(next); }} {...options} />;
  };
  render(<Form />);
  return { input: screen.getByRole('textbox', { name: 'Дата' }) as HTMLInputElement, changed };
};
const paste = (input: HTMLInputElement, text: string) => fireEvent.paste(input, {
  clipboardData: { getData: () => text },
});

it('восемь цифр вводятся подряд с фиксированными точками, можно вводить точки вручную', async () => {
  const user = userEvent.setup();
  const { input, changed } = setup();
  await interact(() => user.click(input));
  await keyboard(user, '10042026');
  expect(input).toHaveValue('10.04.2026');
  expect(changed).toHaveBeenLastCalledWith('2026-04-10');
  input.select();
  await keyboard(user, '25.12.2027');
  expect(input).toHaveValue('25.12.2027');
});
it('Backspace и замена дня не перемещают месяц и год', async () => {
  const user = userEvent.setup();
  const { input } = setup('2026-04-25');
  await interact(() => user.click(input));
  input.setSelectionRange(2, 2);
  await keyboard(user, '{Backspace}');
  expect(input).toHaveValue('2_.04.2026');
  await keyboard(user, '5');
  expect(input).toHaveValue('25.04.2026');
  input.setSelectionRange(0, 2);
  await keyboard(user, '10');
  expect(input).toHaveValue('10.04.2026');
});
it.each(['10.04.2026', '10042026', '2026-04-10', '10/4/2026'])(
  'вставляет дату целиком из %s', text => {
    const { input, changed } = setup('2020-01-01');
    paste(input, text);
    expect(input).toHaveValue('10.04.2026');
    expect(changed).toHaveBeenLastCalledWith('2026-04-10');
  },
);
it('копирует дату целиком стандартным Ctrl+C и вставляет её в другое поле', async () => {
  const user = userEvent.setup();
  render(<><DateInput label="Первая" value="2026-04-10" onChange={() => {}} />
    <DateInput label="Вторая" value="" onChange={() => {}} /></>);
  const first = screen.getByRole('textbox', { name: 'Первая' }) as HTMLInputElement;
  const second = screen.getByRole('textbox', { name: 'Вторая' });
  await interact(() => user.click(first));
  first.select();
  const clipboard = await interact(() => user.copy());
  expect(clipboard?.getData('text/plain')).toBe('10.04.2026');
  await interact(() => user.click(second));
  await interact(() => user.paste());
  expect(second).toHaveValue('10.04.2026');
});
it.each(['33.13.2222', '31.04.2026', '29.02.2025', '10.04.202666'])(
  'выделяет ошибку при вставке %s, не обрезает и не исправляет дату молча', text => {
    const { input } = setup();
    paste(input, text);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveValue(text);
    expect(screen.getByText(/Введите существующую дату/)).toBeInTheDocument();
  },
);
it('принимает високосную дату, очищает Ctrl+A/Delete и проверяет неполный ввод после выхода', async () => {
  const user = userEvent.setup();
  const { input, changed } = setup();
  paste(input, '29.02.2024');
  expect(input).toHaveAttribute('aria-invalid', 'false');
  await interact(() => user.click(input));
  await keyboard(user, '{Control>}a{/Control}{Delete}');
  expect(input).toHaveValue('');
  expect(changed).toHaveBeenLastCalledWith('');
  await keyboard(user, '12');
  await interact(() => user.tab());
  expect(input).toHaveAttribute('aria-invalid', 'true');
});
it('сохраняет возможность набрать текстовый срок вместо даты', async () => {
  const user = userEvent.setup();
  const { input, changed } = setup('', { allowText: true });
  await interact(() => user.click(input));
  await keyboard(user, 'в течение 30 дней');
  expect(input).toHaveValue('в течение 30 дней');
  expect(changed).toHaveBeenLastCalledWith('в течение 30 дней');
  expect(input).toHaveAttribute('aria-invalid', 'false');
});
it('проверяет дату и время вместе, календарь записывает ISO с временем', () => {
  const { input, changed } = setup('', { withTime: true });
  paste(input, '10.04.2026 25:00');
  expect(input).toHaveAttribute('aria-invalid', 'true');
  paste(input, '10.04.2026 14:35');
  expect(changed).toHaveBeenLastCalledWith('2026-04-10T14:35');
  expect(input).toHaveAttribute('aria-invalid', 'false');
  const picker = document.querySelector('input[type="datetime-local"]') as HTMLInputElement;
  fireEvent.change(picker, { target: { value: '2026-05-01T09:00' } });
  expect(input).toHaveValue('01.05.2026 09:00');
});

it('откладывает обновление большой формы, но передаёт последнее значение сразу при выходе из поля', () => {
  jest.useFakeTimers();
  try {
    const changed = jest.fn();
    const { unmount } = render(<DateInput label="Отложенная дата" value="" onChange={changed} />);
    const input = screen.getByRole('textbox', { name: 'Отложенная дата' });
    fireEvent.change(input, { target: { value: '10.04.2026' } });
    expect(changed).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(changed).toHaveBeenLastCalledWith('2026-04-10');
    changed.mockClear();
    fireEvent.change(input, { target: { value: '11.04.2026' } });
    unmount();
    act(() => { jest.runOnlyPendingTimers(); });
    expect(changed).not.toHaveBeenCalled();
  } finally { jest.useRealTimers(); }
});
