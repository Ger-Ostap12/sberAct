import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import FinancesSection from '../FinancesSection';

// Секция «Финансовые данные»: для кредитора-ФНС раскладка перестраивается в 4 подблока
// по очередям реестра; для обычного банка — плоский общий блок. Проверяем обе ветки и
// проброс правок через onFieldChange (см. память fns-queue-finances).

describe('FinancesSection — обычный кредитор (не ФНС)', () => {
  it('рендерит плоский блок, без подблоков очередей', () => {
    render(<FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} />);
    expect(screen.getByText('Проценты:')).toBeInTheDocument();
    expect(screen.getByText('Банкротная госпошлина:')).toBeInTheDocument();
    expect(screen.queryByText('Первая очередь')).not.toBeInTheDocument();
    expect(screen.queryByText('Общая информация')).not.toBeInTheDocument();
  });

  it('тултип-разбивка при наведении на поле с ≥2 слагаемыми', async () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: 'ПАО Сбербанк', principalDebt: '1 465 013 605,99' }}
        onFieldChange={() => {}}
        financeBreakdown={{ principalDebt: ['465 015 355,26', '999 998 250,73'] }}
      />,
    );
    fireEvent.mouseOver(screen.getByDisplayValue('1 465 013 605,99'));
    expect(await screen.findByText(/465 015 355,26/)).toBeInTheDocument();
    expect(screen.getByText(/999 998 250,73/)).toBeInTheDocument();
  });

  it('тултип при ОДНОМ слагаемом — «Из документа: N» (кейс Форте Хоум)', async () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: 'ПАО Сбербанк', principalDebt: '4 463 145 841,47' }}
        onFieldChange={() => {}}
        financeBreakdown={{ principalDebt: ['4 463 145 841,47'] }}
      />,
    );
    fireEvent.mouseOver(screen.getByDisplayValue('4 463 145 841,47'));
    expect(await screen.findByText(/Из документа: 4 463 145 841,47/)).toBeInTheDocument();
  });
});

describe('FinancesSection — кредитор ФНС', () => {
  const fns = 'ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области';

  it('рендерит 4 подблока (Общая информация + 3 очереди), без банкротной ГП', () => {
    render(<FinancesSection editedFields={{ creditorName: fns }} onFieldChange={() => {}} />);
    expect(screen.getByText('Общая информация')).toBeInTheDocument();
    expect(screen.getByText('Первая очередь')).toBeInTheDocument();
    expect(screen.getByText('Вторая очередь')).toBeInTheDocument();
    expect(screen.getByText('Третья очередь')).toBeInTheDocument();
    // Новые ФНС-строки присутствуют; банкротной ГП у ФНС нет.
    expect(screen.getAllByText('Недоимка:').length).toBe(3);
    expect(screen.getAllByText('НДФЛ:').length).toBe(3);
    expect(screen.queryByText('Банкротная госпошлина:')).not.toBeInTheDocument();
  });

  it('отображает значения ФНС-полей и пробрасывает правки', () => {
    const onFieldChange = jest.fn();
    render(
      <FinancesSection
        editedFields={{ creditorName: fns, fnsQ3LoanDebt: '745 735,35' }}
        onFieldChange={onFieldChange}
      />,
    );
    const input = screen.getByDisplayValue('745 735,35');
    fireEvent.change(input, { target: { value: '1000,50' } });
    expect(onFieldChange).toHaveBeenCalledWith('fnsQ3LoanDebt', '1000.50');
  });

  it('сверка очереди: подытог = Σ строк → ✓; расхождение → ⚠', () => {
    const { rerender } = render(
      <FinancesSection
        editedFields={{ creditorName: fns, fnsQ3Total: '100,00', fnsQ3LoanDebt: '70,00', fnsQ3Forfeit: '30,00' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/Итог очереди: сходится/)).toBeInTheDocument();

    rerender(
      <FinancesSection
        editedFields={{ creditorName: fns, fnsQ3Total: '100,00', fnsQ3LoanDebt: '70,00', fnsQ3Forfeit: '5,00' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/Итог очереди:.*расхождение/)).toBeInTheDocument();
  });

  it('итоговая сверка: Общая сумма долга = Σ подытогов очередей', () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: fns, totalDebt: '300,00', fnsQ1Total: '100,00', fnsQ2Total: '100,00', fnsQ3Total: '100,00' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/Общая сумма долга: сходится/)).toBeInTheDocument();
  });

  it('флаг fnsTotalComputed=1 → предупреждение «вычислена»', () => {
    const { rerender } = render(
      <FinancesSection editedFields={{ creditorName: fns, totalDebt: '300,00' }} onFieldChange={() => {}} />,
    );
    expect(screen.queryByText(/вычислена как сумма подытогов/)).not.toBeInTheDocument();

    rerender(
      <FinancesSection
        editedFields={{ creditorName: fns, totalDebt: '300,00', fnsTotalComputed: '1' }}
        onFieldChange={() => {}}
      />,
    );
    expect(screen.getByText(/вычислена как сумма подытогов/)).toBeInTheDocument();
  });
});

// Подсветка подозрительных полей (backend fieldQuality). Денежные поля — главная
// жертва чужого текста: «Арбитражный суд Ростовской области» приезжал в «Ссудную
// задолженность» и печатался в акте как «основной долг в размере ... руб.».
describe('FinancesSection — подсветка подозрительных полей', () => {
  const bank = 'ПАО Сбербанк';

  it('без fieldQuality ничего не подсвечено', () => {
    render(<FinancesSection editedFields={{ creditorName: bank, interest: '100,00' }} onFieldChange={() => {}} />);
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });

  it('поле уровня low подсвечивается', () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: bank, interest: '100,00' }}
        onFieldChange={() => {}}
        fieldQuality={{ interest: { level: 'low', reasons: ['в денежном поле текст, а не сумма'], cleared: true } }}
      />,
    );
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
  });

  it('medium не подсвечивается — иначе подсветка станет шумом', () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: bank, interest: '100,00' }}
        onFieldChange={() => {}}
        fieldQuality={{ interest: { level: 'medium', reasons: [] } }}
      />,
    );
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });

  it('подсветка НЕ ломает тултип «откуда число» на том же поле', async () => {
    // АНТИ-РЕГРЕССИЯ: FieldQualityMark вложен внутрь BreakdownTip, а MUI Tooltip
    // вешает на ребёнка ref и обработчики наведения. Без forwardRef тултип
    // разбивки молча переставал открываться.
    render(
      <FinancesSection
        editedFields={{ creditorName: bank, principalDebt: '1 465 013 605,99' }}
        onFieldChange={() => {}}
        financeBreakdown={{ principalDebt: ['465 015 355,26', '999 998 250,73'] }}
        fieldQuality={{ principalDebt: { level: 'low', reasons: ['проверить'], cleared: false } }}
      />,
    );
    fireEvent.mouseOver(screen.getByDisplayValue('1 465 013 605,99'));
    expect(await screen.findByText(/465 015 355,26/)).toBeInTheDocument();
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
  });

  it('«Ссудная задолженность» ловит претензию к loanDebt, хотя показывает principalDebt', () => {
    // Поле формы = principalDebt OR loanDebt; контракт вычистил именно loanDebt
    // (туда попадал текст суда) — юрист должен увидеть пометку на том, что видит.
    render(
      <FinancesSection
        editedFields={{ creditorName: bank }}
        onFieldChange={() => {}}
        fieldQuality={{ loanDebt: { level: 'low', reasons: ['значение принадлежит полю «courtName»'], cleared: true } }}
      />,
    );
    expect(screen.getAllByTestId('field-quality-low')).toHaveLength(1);
  });
});

describe('FinancesSection — итоговая сумма (ипотека)', () => {
  it('банкротство: поля «Итоговая сумма» нет', () => {
    render(<FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} />);
    expect(screen.queryByText('Итоговая сумма:')).not.toBeInTheDocument();
  });

  it('ипотека: «Итоговая сумма» = Общая сумма долга + банкротная госпошлина', () => {
    render(
      <FinancesSection
        editedFields={{ creditorName: 'ПАО Сбербанк', totalDebt: '100000', stateDuty16: '5000' }}
        onFieldChange={() => {}}
        mode="mortgage"
      />,
    );
    expect(screen.getByText('Итоговая сумма:')).toBeInTheDocument();
    // 100000 + 5000 = 105 000,00 (формат ru-RU).
    expect(screen.getByDisplayValue('105 000,00')).toBeInTheDocument();
  });

  it('ипотека: «Ссудная госпошлина» скрыта; банкротство — показана', () => {
    const { rerender } = render(
      <FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} />,
    );
    expect(screen.getByText('Ссудная госпошлина:')).toBeInTheDocument();
    rerender(
      <FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} mode="mortgage" />,
    );
    expect(screen.queryByText('Ссудная госпошлина:')).not.toBeInTheDocument();
  });

  it('ипотека: даты ПП депозит/ГП скрыты; банкротство — показаны', () => {
    const { rerender } = render(
      <FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} />,
    );
    expect(screen.getByText('Дата ПП депозит:')).toBeInTheDocument();
    expect(screen.getByText('Дата ПП ГП:')).toBeInTheDocument();
    rerender(
      <FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} mode="mortgage" />,
    );
    expect(screen.queryByText('Дата ПП депозит:')).not.toBeInTheDocument();
    expect(screen.queryByText('Дата ПП ГП:')).not.toBeInTheDocument();
  });
});

describe('FinancesSection — военная ипотека (ЦЖЗ)', () => {
  it('civil: обычные поля (Проценты, Банкротная госпошлина)', () => {
    render(
      <FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} mode="mortgage" mortgageKind="civil" />,
    );
    expect(screen.getByText('Проценты:')).toBeInTheDocument();
    expect(screen.queryByText('Основной долг по ЦЖЗ:')).not.toBeInTheDocument();
  });

  it('military: военные поля вместо обычных', () => {
    render(
      <FinancesSection editedFields={{ creditorName: 'ПАО Сбербанк' }} onFieldChange={() => {}} mode="mortgage" mortgageKind="military" />,
    );
    expect(screen.getByText('Общая сумма взыскания:')).toBeInTheDocument();
    expect(screen.getByText('Основной долг по ЦЖЗ:')).toBeInTheDocument();
    expect(screen.getByText('Проценты за пользование займом:')).toBeInTheDocument();
    expect(screen.getByText('Сумма пени:')).toBeInTheDocument();
    expect(screen.getByText('Процентная ставка (%):')).toBeInTheDocument();
    expect(screen.getByText('Ставка пени (%):')).toBeInTheDocument();
    expect(screen.getByText('Период начисления процентов с:')).toBeInTheDocument();
    expect(screen.getByText('Период начисления процентов по:')).toBeInTheDocument();
    // Обычных банкротных полей больше нет.
    expect(screen.queryByText('Банкротная госпошлина:')).not.toBeInTheDocument();
    expect(screen.queryByText('Итоговая сумма:')).not.toBeInTheDocument();
  });

  it('military: пустые проценты/пени — показывается расчёт по формуле (подсказка)', () => {
    // Осн.долг=1 000 000, ставка 10%, ставка пени 0.1%, период 15.01–14.02.2023 = 30 дней.
    // Проценты = 1000000*0.10*(30/365) = 8219,18. Пени = 1000000*0.001*30 = 30 000,00.
    render(
      <FinancesSection
        editedFields={{
          creditorName: 'ПАО Сбербанк',
          milPrincipalCzz: '1000000',
          milInterestRate: '10',
          milPenaltyRate: '0.1',
          milInterestPeriodFrom: '15.01.2023',
          milInterestPeriodTo: '14.02.2023',
        }}
        onFieldChange={() => {}}
        mode="mortgage"
        mortgageKind="military"
      />,
    );
    expect(screen.getByText(/Расчёт по формуле: 8 219,18/)).toBeInTheDocument();
    expect(screen.getByText(/Расчёт по формуле: 30 000,00/)).toBeInTheDocument();
  });

  it('military: значение процентов из документа расходится с формулой → предупреждение', () => {
    const base = {
      creditorName: 'ПАО Сбербанк',
      milPrincipalCzz: '1000000',
      milInterestRate: '10',
      milPenaltyRate: '0.1',
      milInterestPeriodFrom: '15.01.2023',
      milInterestPeriodTo: '14.02.2023',
    };
    // Проценты из документа = 9000,00, а расчёт 8 219,18 → ⚠ с расчётом.
    render(
      <FinancesSection
        editedFields={{ ...base, milLoanInterest: '9000' }}
        onFieldChange={() => {}}
        mode="mortgage"
        mortgageKind="military"
      />,
    );
    expect(screen.getByText(/В документе 9 000,00, расчёт по формуле 8 219,18/)).toBeInTheDocument();
  });

  it('military: проверка Общей суммы взыскания = Осн.долг + Проценты(док) + Пени(док)', () => {
    // Осн.долг 1 000 000 + проценты(док) 8 219,18 + пени(док) 30 000,00 = 1 038 219,18.
    const base = {
      creditorName: 'ПАО Сбербанк',
      milPrincipalCzz: '1000000',
      milLoanInterest: '8219.18',
      milPenaltySum: '30000',
    };
    const { rerender } = render(
      <FinancesSection editedFields={{ ...base, milTotalClaim: '1038219.18' }} onFieldChange={() => {}} mode="mortgage" mortgageKind="military" />,
    );
    expect(screen.getByText(/Общая сумма взыскания сходится/)).toBeInTheDocument();

    rerender(
      <FinancesSection editedFields={{ ...base, milTotalClaim: '999999' }} onFieldChange={() => {}} mode="mortgage" mortgageKind="military" />,
    );
    expect(screen.getByText(/Общая сумма взыскания = 999 999,00/)).toBeInTheDocument();
  });
});
