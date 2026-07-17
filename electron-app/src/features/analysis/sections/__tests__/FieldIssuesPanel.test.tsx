import React from 'react';
import { render, screen } from '@testing-library/react';
import FieldIssuesPanel from '../FieldIssuesPanel';
import { FieldIssue } from '../../../../types';

/**
 * Панель адресует юриста к полям, которые контракт счёл чужими. Ключевое
 * различение — «очищено» (вводить заново) против «оставлено» (сверить).
 */
describe('FieldIssuesPanel', () => {
  const cleared: FieldIssue = {
    field: 'loanDebt',
    reason: 'значение принадлежит полю «courtName», а не этому',
    value: 'Арбитражный суд Ростовской области',
    cleared: true,
  };
  const flagged: FieldIssue = {
    field: 'inn',
    reason: 'INN не проходит контрольную сумму',
    value: '612102429513',
    cleared: false,
  };

  it('не рендерится, когда претензий нет', () => {
    const { container } = render(<FieldIssuesPanel issues={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('не рендерится без пропа (старый ответ backend без fieldIssues)', () => {
    const { container } = render(<FieldIssuesPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it('показывает человекочитаемое имя поля, а не ключ', () => {
    render(<FieldIssuesPanel issues={[cleared]} />);
    expect(screen.getByText('Ссудная задолженность')).toBeInTheDocument();
    expect(screen.queryByText('loanDebt')).not.toBeInTheDocument();
  });

  it('показывает причину и прежнее значение', () => {
    render(<FieldIssuesPanel issues={[cleared]} />);
    expect(screen.getByText(/значение принадлежит полю/)).toBeInTheDocument();
    expect(screen.getByText(/было: Арбитражный суд Ростовской области/)).toBeInTheDocument();
  });

  it('разделяет очищенные и оставленные с пометкой', () => {
    render(<FieldIssuesPanel issues={[cleared, flagged]} />);
    expect(screen.getByText(/Очищены/)).toBeInTheDocument();
    expect(screen.getByText(/Оставлены, но проверьте/)).toBeInTheDocument();
    expect(screen.getByText('ИНН должника')).toBeInTheDocument();
  });

  it('показывает только нужный раздел, если претензии одного вида', () => {
    render(<FieldIssuesPanel issues={[flagged]} />);
    expect(screen.queryByText(/Очищены/)).not.toBeInTheDocument();
    expect(screen.getByText(/Оставлены, но проверьте/)).toBeInTheDocument();
  });

  it('имя поля записи должника берётся по базовому ключу', () => {
    render(
      <FieldIssuesPanel
        issues={[{ field: 'debtors[0].address', reason: 'нет адресных признаков', value: 'ПАО Сбер', cleared: true }]}
      />,
    );
    expect(screen.getByText('Адрес должника')).toBeInTheDocument();
  });

  it('длинное значение обрезается, чтобы не разносить вёрстку', () => {
    const long = 'А'.repeat(200);
    render(<FieldIssuesPanel issues={[{ ...cleared, value: long }]} />);
    expect(screen.getByText(/…$/)).toBeInTheDocument();
  });
});
