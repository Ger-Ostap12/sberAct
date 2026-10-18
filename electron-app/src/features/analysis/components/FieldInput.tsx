import React, { forwardRef, useEffect, useRef, useState } from 'react';
import { TextField, TextFieldProps } from '@mui/material';

/**
 * Поле ввода, которое печатает в своём состоянии.
 *
 * Форма анализа — одно большое дерево на сотню полей, и подъём каждого символа
 * в родителя перерисовывал её целиком: замер давал 230 мс на символ. Здесь
 * символ остаётся внутри поля, а наверх уходит после паузы в наборе.
 */
type Props = Omit<TextFieldProps, 'value' | 'onChange'> & {
  value: string;
  onChange: (value: string) => void;
  /** Пауза в наборе, после которой значение уходит наверх. */
  delay?: number;
};

// forwardRef обязателен: MUI Tooltip вешает обработчики и ref на ребёнка,
// и без него подсказка «откуда число» в финансах молча перестаёт всплывать.
export const FieldInput = forwardRef<HTMLDivElement, Props>(function FieldInput(
  { value, onChange, delay = 300, ...props },
  ref,
) {
  const [локальное, setЛокальное] = useState(value);
  const таймер = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Что мы сами отправили наверх: родитель вернёт это же значение, и перетирать
  // им набранное с тех пор нельзя.
  const отправленное = useRef(value);

  useEffect(() => {
    if (value !== отправленное.current) {
      отправленное.current = value;
      setЛокальное(value);
    }
  }, [value]);

  useEffect(() => () => {
    if (таймер.current) clearTimeout(таймер.current);
  }, []);

  const поднять = (следующее: string) => {
    отправленное.current = следующее;
    onChange(следующее);
  };

  const печатать = (событие: React.ChangeEvent<HTMLInputElement>) => {
    const следующее = событие.target.value;
    setЛокальное(следующее);
    if (таймер.current) clearTimeout(таймер.current);
    таймер.current = setTimeout(() => поднять(следующее), delay);
  };

  // Уход из поля не ждёт паузы: дальше по форме значение нужно сразу.
  const уйти = (событие: React.FocusEvent<HTMLInputElement>) => {
    if (таймер.current) clearTimeout(таймер.current);
    if (локальное !== отправленное.current) поднять(локальное);
    props.onBlur?.(событие);
  };

  return <TextField {...props} ref={ref} value={локальное} onChange={печатать} onBlur={уйти} />;
});
