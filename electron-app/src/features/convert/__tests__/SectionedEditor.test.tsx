import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SectionedEditor from '../SectionedEditor';
import { DocxSection } from '../../../services/electronApi';

// Секции в ПОРЯДКЕ ОТОБРАЖЕНИЯ (как отдаёт бэкенд), но с индексами вразнобой:
// таблица (index 2) показывается после «Требований», хотя канонически стоит
// между должником и кредитором — проверяем пересборку по index.
const SECTIONS: DocxSection[] = [
  { id: 'intro', title: 'Вводная часть', lines: [{ text: 'В Арбитражный суд', index: 0 }] },
  { id: 'debtor', title: 'Должник', lines: [{ text: 'Должник: Иванов', index: 1 }] },
  { id: 'creditor', title: 'Кредитор / Заявитель', lines: [{ text: 'Кредитор: Сбербанк', index: 3 }] },
  { id: 'finances', title: 'Требования', lines: [{ text: 'Прошу признать банкротом', index: 4 }] },
  { id: 'tables', title: 'Таблицы', lines: [{ text: 'Договор №1', index: 2 }] },
  { id: 'other', title: 'Реквизиты и примечания', lines: [{ text: 'ИНН 6100000000', index: 5 }] },
];

const CANONICAL =
  'В Арбитражный суд\nДолжник: Иванов\nДоговор №1\nКредитор: Сбербанк\nПрошу признать банкротом\nИНН 6100000000';

describe('SectionedEditor', () => {
  it('пересобирает канонический текст в исходном порядке index (не в порядке секций)', () => {
    const onChange = jest.fn();
    render(<SectionedEditor sections={SECTIONS} onChange={onChange} />);
    expect(onChange).toHaveBeenLastCalledWith(CANONICAL);
  });

  it('должник и кредитор — в РАЗНЫХ секциях (не слиты)', () => {
    render(<SectionedEditor sections={SECTIONS} onChange={jest.fn()} />);
    expect(screen.getByTestId('section-debtor')).toHaveValue('Должник: Иванов');
    expect(screen.getByTestId('section-creditor')).toHaveValue('Кредитор: Сбербанк');
    // Таблица отделена в свою секцию (а не в хвосте общего текста).
    expect(screen.getByTestId('section-tables')).toHaveValue('Договор №1');
  });

  it('правка секции меняет канонический текст, сохраняя порядок index', async () => {
    const onChange = jest.fn();
    render(<SectionedEditor sections={SECTIONS} onChange={onChange} />);

    const debtor = screen.getByTestId('section-debtor');
    await userEvent.clear(debtor);
    await userEvent.type(debtor, 'Должник: Петров');

    expect(onChange).toHaveBeenLastCalledWith(
      'В Арбитражный суд\nДолжник: Петров\nДоговор №1\nКредитор: Сбербанк\nПрошу признать банкротом\nИНН 6100000000'
    );
  });
});
