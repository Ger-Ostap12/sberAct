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

  it('реквизит записи получает метку, а не сырой ключ debtors[0].inn', () => {
    // Ключи записей добавлялись в контракт позже адресов — метки за ними не
    // поспели, и юрист видел в панели «debtors[0].inn».
    render(
      <FieldIssuesPanel
        issues={[{ field: 'debtors[0].inn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: false }]}
      />,
    );
    expect(screen.getByText(/ИНН должника \(карточка\)/)).toBeInTheDocument();
    expect(screen.queryByText(/debtors\[0\]/)).not.toBeInTheDocument();
  });

  it('одно значение в трёх полях — ОДНА строка, а не три', () => {
    // A53-9758…docx: битый OCR ИНН разбор кладёт в inn, companyInn и в карточку
    // должника. Это одна проблема; три строки про один номер — шум ровно там,
    // где панель обязана его снижать.
    render(
      <FieldIssuesPanel
        issues={[
          { field: 'inn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: false },
          { field: 'companyInn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: false },
          { field: 'debtors[0].inn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: false },
        ]}
      />,
    );
    expect(screen.getAllByText(/было: 612102429513/)).toHaveLength(1);
    expect(
      screen.getByText('ИНН должника, ИНН организации, ИНН должника (карточка)'),
    ).toBeInTheDocument();
  });

  it('РАЗНЫЕ значения с той же причиной не схлопываются', () => {
    // Иначе схлопывание съело бы настоящую вторую проблему: два разных битых
    // ИНН — это два разных номера, которые юрист правит по отдельности.
    render(
      <FieldIssuesPanel
        issues={[
          { field: 'inn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: false },
          { field: 'creditorInn', reason: 'INN не проходит контрольную сумму', value: '770708389311', cleared: false },
        ]}
      />,
    );
    expect(screen.getByText(/было: 612102429513/)).toBeInTheDocument();
    expect(screen.getByText(/было: 770708389311/)).toBeInTheDocument();
  });

  it('одинаковая причина, но разный статус — не схлопывается', () => {
    // «Очищено» и «оставлено» требуют разных действий: смешать их нельзя даже
    // при совпадении значения.
    render(
      <FieldIssuesPanel
        issues={[
          { field: 'inn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: false },
          { field: 'companyInn', reason: 'INN не проходит контрольную сумму', value: '612102429513', cleared: true },
        ]}
      />,
    );
    expect(screen.getByText(/Очищены/)).toBeInTheDocument();
    expect(screen.getByText(/Оставлены, но проверьте/)).toBeInTheDocument();
    expect(screen.getAllByText(/было: 612102429513/)).toHaveLength(2);
  });

  it('длинное значение обрезается, чтобы не разносить вёрстку', () => {
    const long = 'А'.repeat(200);
    render(<FieldIssuesPanel issues={[{ ...cleared, value: long }]} />);
    expect(screen.getByText(/…$/)).toBeInTheDocument();
  });
});
