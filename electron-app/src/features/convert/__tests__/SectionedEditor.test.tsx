import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SectionedEditor from '../SectionedEditor';
import { DocxSection } from '../../../services/electronApi';

// Три блока (Шапка → Основной текст → Просительная) с индексами по порядку.
const SECTIONS: DocxSection[] = [
  {
    id: 'header',
    title: 'Шапка',
    lines: [
      { text: 'В Арбитражный суд', index: 0 },
      { text: 'Должник: Иванов', index: 1 },
    ],
  },
  {
    id: 'body',
    title: 'Основной текст',
    lines: [
      { text: 'ЗАЯВЛЕНИЕ о банкротстве', index: 2 },
      { text: 'Между сторонами договор', index: 3 },
    ],
  },
  {
    id: 'prayer',
    title: 'Просительная часть',
    lines: [
      { text: 'Прошу признать банкротом', index: 4 },
      { text: 'Договор №1', index: 5 },
    ],
  },
];

const CANONICAL =
  'В Арбитражный суд\nДолжник: Иванов\nЗАЯВЛЕНИЕ о банкротстве\nМежду сторонами договор\nПрошу признать банкротом\nДоговор №1';

describe('SectionedEditor', () => {
  it('пересобирает канонический текст в исходном порядке index', () => {
    const onChange = jest.fn();
    render(<SectionedEditor sections={SECTIONS} onChange={onChange} />);
    expect(onChange).toHaveBeenLastCalledWith(CANONICAL);
  });

  it('рендерит ровно три блока: шапка / основной текст / просительная', () => {
    render(<SectionedEditor sections={SECTIONS} onChange={jest.fn()} />);
    expect(screen.getByTestId('section-header')).toHaveValue('В Арбитражный суд\nДолжник: Иванов');
    expect(screen.getByTestId('section-body')).toHaveValue(
      'ЗАЯВЛЕНИЕ о банкротстве\nМежду сторонами договор'
    );
    expect(screen.getByTestId('section-prayer')).toHaveValue('Прошу признать банкротом\nДоговор №1');
  });

  it('правка блока меняет канонический текст, сохраняя порядок index', async () => {
    const onChange = jest.fn();
    render(<SectionedEditor sections={SECTIONS} onChange={onChange} />);

    const prayer = screen.getByTestId('section-prayer');
    await userEvent.clear(prayer);
    await userEvent.type(prayer, 'Прошу отказать');

    expect(onChange).toHaveBeenLastCalledWith(
      'В Арбитражный суд\nДолжник: Иванов\nЗАЯВЛЕНИЕ о банкротстве\nМежду сторонами договор\nПрошу отказать'
    );
  });
});
