import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import LlmFieldHint, { LlmHintPending } from '../LlmFieldHint';
import { LlmHintsValue } from '../../../features/analysis/lib/LlmHintsContext';

// Контекст подменяем целиком: тестируем поведение компонента, а не сеть.
let mockValue: LlmHintsValue;
jest.mock('../../../features/analysis/lib/LlmHintsContext', () => ({
  useLlmHints: () => mockValue,
}));

const HINT = {
  field: 'courtName',
  label: 'Название суда',
  block: 'court',
  regexValue: 'Приморский районный суд',
  llmValue: 'Ленинский районный суд',
  agrees: false,
};

const makeValue = (over: Partial<LlmHintsValue> = {}): LlmHintsValue => ({
  running: false,
  blocksDone: 0,
  blocksTotal: 0,
  hintFor: () => undefined,
  dismiss: jest.fn(),
  isBlockDone: () => false,
  ...over,
});

describe('LlmFieldHint — баннер расхождения', () => {
  it('молчит, когда расхождения нет: согласие не повод тревожить юриста', () => {
    mockValue = makeValue();
    const { container } = render(<LlmFieldHint field="courtName" block="court" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('разбор пуст, модель нашла: предлагает вписать, а не сверить', () => {
    // Худший случай для юриста — пустое поле без объяснения: непонятно, в
    // документе нет значения или разбор его потерял. Раньше подсказка тут
    // молчала.
    mockValue = makeValue({
      hintFor: () => ({
        field: 'courtAddress',
        label: 'Адрес суда',
        block: 'court',
        regexValue: '',
        llmValue: '353907, г. Новороссийск, ул. Индустриальная, д. 4 А',
        agrees: false,
      }),
    });
    render(<LlmFieldHint field="courtAddress" block="court" />);
    expect(screen.getByText(/не нашёл значение для этого поля/)).toBeInTheDocument();
    expect(screen.getByText(/Новороссийск/)).toBeInTheDocument();
    // Формулировки сравнения быть не должно: сравнивать не с чем.
    expect(screen.queryByText(/Автоматический разбор дал/)).not.toBeInTheDocument();
  });

  it('замечание о правдоподобии: показывает значение и причину, без альтернативы', () => {
    // У sanity-подсказки llmValue пуст намеренно — модель не предлагает замену,
    // а сообщает, что значение не похоже на своё поле.
    mockValue = makeValue({
      hintFor: () => ({
        field: 'courtAddress',
        label: 'Адрес суда',
        block: 'sanity',
        regexValue: '32093 блаблакаркукук',
        llmValue: '',
        agrees: false,
        reason: 'посторонний текст вместо адреса',
      }),
    });
    render(<LlmFieldHint field="courtAddress" block="court" />);
    expect(screen.getByText('Перепроверьте «Адрес суда»')).toBeInTheDocument();
    expect(screen.getByText(/32093 блаблакаркукук/)).toBeInTheDocument();
    expect(screen.getByText(/посторонний текст вместо адреса/)).toBeInTheDocument();
    // Формулировки сравнения тут быть не должно: сравнивать не с чем.
    expect(screen.queryByText(/второй способ проверки нашёл/)).not.toBeInTheDocument();
  });

  it('показывает оба значения при расхождении', () => {
    mockValue = makeValue({ hintFor: () => HINT });
    render(<LlmFieldHint field="courtName" block="court" />);
    expect(screen.getByText('Перепроверьте «Название суда»')).toBeInTheDocument();
    expect(screen.getByText(/Приморский районный суд/)).toBeInTheDocument();
    expect(screen.getByText(/Ленинский районный суд/)).toBeInTheDocument();
  });

  it('молчит, если юрист уже правил поле руками — решение принято', () => {
    mockValue = makeValue({ hintFor: () => HINT });
    const { container } = render(<LlmFieldHint field="courtName" block="court" edited />);
    expect(container).toBeEmptyDOMElement();
  });

  it('закрытие сообщает наверх, чтобы подсказка не вернулась', () => {
    const dismiss = jest.fn();
    mockValue = makeValue({ hintFor: () => HINT, dismiss });
    render(<LlmFieldHint field="courtName" block="court" />);
    fireEvent.click(screen.getByTitle('Close'));
    expect(dismiss).toHaveBeenCalledWith('courtName');
  });
});

describe('LlmHintPending — иконка ожидания', () => {
  it('видна, пока блок проверяется', () => {
    mockValue = makeValue({ running: true });
    render(<LlmHintPending field="courtName" block="court" />);
    expect(screen.getByTestId('llm-hint-pending')).toBeInTheDocument();
  });

  it('исчезает, когда блок проверен', () => {
    mockValue = makeValue({ running: true, isBlockDone: () => true });
    const { container } = render(<LlmHintPending field="courtName" block="court" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('не появляется, если проверка не идёт (слой выключен или недоступен)', () => {
    mockValue = makeValue({ running: false });
    const { container } = render(<LlmHintPending field="courtName" block="court" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('уступает место баннеру, когда расхождение уже найдено', () => {
    mockValue = makeValue({ running: true, hintFor: () => HINT });
    const { container } = render(<LlmHintPending field="courtName" block="court" />);
    expect(container).toBeEmptyDOMElement();
  });
});
