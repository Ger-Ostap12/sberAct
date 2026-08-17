import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Interaction-тесты на CRUD-логику формы (страхуют вынос секций/карточек).

const documentData: DocumentData = {
  filePath: 'test.docx',
  fileName: 'test.docx',
  fileSize: 1,
  uploadDate: new Date('2024-01-01T00:00:00Z'),
};

const makeData = (): ExtractedData => ({
  documentType: 'rtk_application',
  confidence: 1,
  entityType: 'legal',
  fields: { courtName: 'Арбитражный суд', caseNumber: 'A-1' },
  obligations: [
    { id: 'o1', contractNumber: '111', contractDate: '01.02.2024', obligationType: 'Кредитный договор' },
  ],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

const renderForm = () =>
  render(
    <DocumentAnalysis
      documentData={documentData}
      extractedData={makeData()}
      onAnalysisComplete={() => {}}
      onBack={() => {}}
    />
  );

describe('DocumentAnalysis — CRUD обязательств', () => {
  // Карточки — сворачиваемые (Accordion), в шапке «Обязательство N [— № …]».
  it('стартует с одним обязательством', () => {
    renderForm();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
    expect(screen.queryByText(/Обязательство 2/)).not.toBeInTheDocument();
  });

  it('«Добавить обязательство» добавляет карточку', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить обязательство' }));
    expect(screen.getByText(/Обязательство 2/)).toBeInTheDocument();
  });

  it('кнопка удаления убирает обязательство', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить обязательство' }));
    expect(screen.getByText(/Обязательство 2/)).toBeInTheDocument();

    const removeButtons = screen.getAllByLabelText('Удалить обязательство');
    fireEvent.click(removeButtons[0]);
    expect(screen.queryByText(/Обязательство 2/)).not.toBeInTheDocument();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
  });

  it('редактирование номера договора обновляет поле (даже в свёрнутой карточке)', () => {
    renderForm();
    // Поля свёрнутой карточки остаются в DOM (MUI Collapse не размонтирует контент).
    const numberInput = screen.getByDisplayValue('111');
    fireEvent.change(numberInput, { target: { value: '222' } });
    expect(screen.getByDisplayValue('222')).toBeInTheDocument();
  });
});

describe('DocumentAnalysis — раскладка ФНС', () => {
  const renderWith = (creditorName?: string, collaterals?: ExtractedData['collaterals']) => {
    const data = makeData();
    data.fields = { ...data.fields, creditorName: creditorName || '' };
    if (collaterals) data.collaterals = collaterals;
    return render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
  };

  it('для обычного кредитора блоки «Залог», «Обязательства», «Третьи лица» показаны', () => {
    renderWith('ПАО Сбербанк');
    expect(screen.getByText('Залог')).toBeInTheDocument();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
    expect(screen.getByText('Третьи лица')).toBeInTheDocument();
  });

  it('для кредитора-ФНС блоки «Залог», «Обязательства», «Третьи лица» скрыты, финансы — по очередям', () => {
    renderWith('ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области');
    expect(screen.queryByText('Залог')).not.toBeInTheDocument();
    expect(screen.queryByText(/Обязательство 1/)).not.toBeInTheDocument();
    expect(screen.queryByText('Третьи лица')).not.toBeInTheDocument();
    expect(screen.getByText('Первая очередь')).toBeInTheDocument();
  });

  const collOther = [{ id: 'c1', collateralType: 'other', otherDescription: 'оборудование' }] as ExtractedData['collaterals'];

  it('не-ФНС: задетекченный залог «иное» отмечает «Залог иное»', () => {
    renderWith('ПАО Сбербанк', collOther);
    expect(screen.getByRole('checkbox', { name: 'Залог иное' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Без залога' })).not.toBeChecked();
  });

  it('ФНС: даже при задетекченном залоге по умолчанию «Без залога»', () => {
    renderWith('ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области', collOther);
    expect(screen.getByRole('checkbox', { name: 'Без залога' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Залог иное' })).not.toBeChecked();
  });
});

describe('DocumentAnalysis — самобанкротство', () => {
  const renderSelf = (mutate?: (d: ExtractedData) => void) => {
    const data = makeData();
    if (mutate) mutate(data);
    return render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
  };

  it('«Самобанкрот» — всем категориям (вид заявления); статусы лица гейтятся типом лица', () => {
    renderSelf();
    // «Самобанкрот» — радио в блоке «Вид заявления», доступно всегда.
    // Статусы лица (Умерший/Отсутствующий/Ликвидируемый) — ToggleButton (role button).
    // ИП: статусов лица нет.
    fireEvent.click(screen.getByRole('radio', { name: 'ИП' }));
    expect(screen.getByRole('radio', { name: 'Самобанкрот' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Умерший' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отсутствующий' })).not.toBeInTheDocument();
    // ФЛ: «Умерший».
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    expect(screen.getByRole('button', { name: 'Умерший' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Самобанкрот' })).toBeInTheDocument();
    // ЮЛ: «Отсутствующий»/«Ликвидируемый».
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    expect(screen.getByRole('button', { name: 'Отсутствующий' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ликвидируемый' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Самобанкрот' })).toBeInTheDocument();
  });

  it('вид заявления и статус лица независимы: Инициирование + Ликвидируемый одновременно', () => {
    renderSelf();
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    // По умолчанию вид — «Инициирование»; выбираем статус «Ликвидируемый».
    fireEvent.click(screen.getByRole('button', { name: 'Ликвидируемый' }));
    expect(screen.getByRole('radio', { name: 'Инициирование' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Ликвидируемый' })).toHaveAttribute('aria-pressed', 'true');
    // Повторный клик по активному статусу снимает выбор (ToggleButton exclusive).
    fireEvent.click(screen.getByRole('button', { name: 'Ликвидируемый' }));
    expect(screen.getByRole('button', { name: 'Ликвидируемый' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('выбор «Самобанкрот» скрывает «Информация о кредиторе» и «Финансовые данные», возврат через «Инициирование»', () => {
    renderSelf();
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    expect(screen.getByText('Информация о кредиторе')).toBeInTheDocument();
    expect(screen.getByText('Финансовые данные')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'Самобанкрот' }));
    expect(screen.queryByText('Информация о кредиторе')).not.toBeInTheDocument();
    expect(screen.queryByText('Финансовые данные')).not.toBeInTheDocument();

    // Радио взаимоисключающее — возврат через выбор «Инициирование».
    fireEvent.click(screen.getByRole('radio', { name: 'Инициирование' }));
    expect(screen.getByText('Информация о кредиторе')).toBeInTheDocument();
    expect(screen.getByText('Финансовые данные')).toBeInTheDocument();
  });

  it('«Самобанкрот» не сбрасывается при смене категории лица', () => {
    renderSelf();
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    fireEvent.click(screen.getByRole('radio', { name: 'Самобанкрот' }));
    fireEvent.click(screen.getByRole('radio', { name: 'ИП' }));
    expect(screen.getByRole('radio', { name: 'Самобанкрот' })).toBeChecked();
    expect(screen.queryByText('Информация о кредиторе')).not.toBeInTheDocument();
  });

  it('applicationKind=self_bankruptcy с бэка автопроставляет статус и скрывает кредитора', () => {
    renderSelf((d) => {
      d.applicationKind = 'self_bankruptcy';
      (d as any).recommendedActs = { entityType: 'individual' };
    });
    expect(screen.getByRole('radio', { name: 'Самобанкрот' })).toBeChecked();
    expect(screen.queryByText('Информация о кредиторе')).not.toBeInTheDocument();
  });
});

describe('DocumentAnalysis — поле СРО у управляющего', () => {
  const renderWithSro = () => {
    const data = makeData();
    data.fields = { ...data.fields, sroName: 'Ассоциация "Содействие"' };
    return render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
  };

  it('поле СРО показано, когда «ВКЛ в РТК» выключена (инициирование)', () => {
    renderWithSro();
    expect(screen.getByText('Саморегулируемая организация:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Ассоциация "Содействие"')).toBeInTheDocument();
  });

  it('выбор радио «Включение в РТК» скрывает поле СРО', () => {
    renderWithSro();
    fireEvent.click(screen.getByRole('radio', { name: 'Включение в РТК' }));
    expect(screen.queryByText('Саморегулируемая организация:')).not.toBeInTheDocument();
  });

  it('возврат на «Инициирование» снова показывает поле СРО', () => {
    renderWithSro();
    fireEvent.click(screen.getByRole('radio', { name: 'Включение в РТК' }));
    fireEvent.click(screen.getByRole('radio', { name: 'Инициирование' }));
    expect(screen.getByText('Саморегулируемая организация:')).toBeInTheDocument();
  });
});

// Матрица полей блока «Арбитражный управляющий»:
//   банк+инициирование → СРО+адрес (ФИО скрыт)
//   ФНС+инициирование  → ФИО+СРО+адрес
//   банк/ФНС+РТК       → ФИО+адрес (СРО скрыт)
//   самобанкрот        → СРО+адрес (ФИО скрыт)
describe('DocumentAnalysis — матрица полей управляющего (ФИО/СРО)', () => {
  const FNS = 'ФНС России в лице Межрайонной ИФНС России № 13 по Ростовской области';
  const renderMatrix = (creditorName?: string) => {
    const data = makeData();
    data.fields = { ...data.fields, creditorName: creditorName || '', sroName: 'СРО', managerName: 'Иванов И.И.' };
    return render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
  };
  const hasFio = () => screen.queryByText('ФИО:') !== null;
  const hasSro = () => screen.queryByText('Саморегулируемая организация:') !== null;

  it('банк + инициирование: СРО есть, ФИО скрыт', () => {
    renderMatrix('ПАО Сбербанк');
    expect(hasSro()).toBe(true);
    expect(hasFio()).toBe(false);
  });

  it('ФНС + инициирование: ФИО и СРО показаны', () => {
    renderMatrix(FNS);
    expect(hasSro()).toBe(true);
    expect(hasFio()).toBe(true);
  });

  it('банк + РТК: ФИО есть, СРО скрыт', () => {
    renderMatrix('ПАО Сбербанк');
    fireEvent.click(screen.getByRole('radio', { name: 'Включение в РТК' }));
    expect(hasFio()).toBe(true);
    expect(hasSro()).toBe(false);
  });

  it('ФНС + РТК: ФИО есть, СРО скрыт', () => {
    renderMatrix(FNS);
    fireEvent.click(screen.getByRole('radio', { name: 'Включение в РТК' }));
    expect(hasFio()).toBe(true);
    expect(hasSro()).toBe(false);
  });

  it('самобанкрот: СРО есть, ФИО скрыт', () => {
    renderMatrix('ПАО Сбербанк');
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    fireEvent.click(screen.getByRole('radio', { name: 'Самобанкрот' }));
    expect(hasSro()).toBe(true);
    expect(hasFio()).toBe(false);
  });
});

// Блок «Объявление о ликвидации» виден только при статусе «Ликвидируемый».
describe('DocumentAnalysis — блок «Объявление о ликвидации»', () => {
  const renderForm = () =>
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={makeData()}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );

  it('по умолчанию блок скрыт', () => {
    renderForm();
    expect(screen.queryByText('Объявление о ликвидации')).not.toBeInTheDocument();
  });

  it('выбор «Ликвидируемый» (ЮЛ) показывает блок, снятие — скрывает', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ликвидируемый' }));
    expect(screen.getByText('Объявление о ликвидации')).toBeInTheDocument();
    expect(screen.getByText('Наименование ликвидатора:')).toBeInTheDocument();
    // Повторный клик снимает статус — блок исчезает.
    fireEvent.click(screen.getByRole('button', { name: 'Ликвидируемый' }));
    expect(screen.queryByText('Объявление о ликвидации')).not.toBeInTheDocument();
  });

  it('статус «Отсутствующий» блок не показывает', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отсутствующий' }));
    expect(screen.queryByText('Объявление о ликвидации')).not.toBeInTheDocument();
  });

  it('debtorStatusHint=liquidation с бэка автопоказывает блок и заполняет ликвидатора', () => {
    const data = makeData();
    (data as any).debtorStatusHint = 'liquidation';
    (data as any).recommendedActs = { entityType: 'legal' };
    data.fields = { ...data.fields, liquidatorName: 'Оленченко Олег Игоревич' };
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
    expect(screen.getByText('Объявление о ликвидации')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Оленченко Олег Игоревич')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ликвидируемый' })).toHaveAttribute('aria-pressed', 'true');
  });
});

// Блок «Информация по счетам» виден только при статусе «Отсутствующий» (ЮЛ).
describe('DocumentAnalysis — блок «Информация по счетам»', () => {
  const renderForm = () =>
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={makeData()}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );

  it('по умолчанию блок скрыт', () => {
    renderForm();
    expect(screen.queryByText('Информация по счетам')).not.toBeInTheDocument();
  });

  it('выбор «Отсутствующий» (ЮЛ) показывает блок с тремя датами, снятие — скрывает', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отсутствующий' }));
    expect(screen.getByText('Информация по счетам')).toBeInTheDocument();
    expect(screen.getByText('Дата последней налоговой отчётности:')).toBeInTheDocument();
    expect(screen.getByText('Дата последней бухгалтерской отчётности:')).toBeInTheDocument();
    expect(screen.getByText('Последняя операция по расчётным счетам:')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Отсутствующий' }));
    expect(screen.queryByText('Информация по счетам')).not.toBeInTheDocument();
  });

  it('статус «Ликвидируемый» блок не показывает', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ликвидируемый' }));
    expect(screen.queryByText('Информация по счетам')).not.toBeInTheDocument();
  });

  it('debtorStatusHint=absent с бэка автопроставляет статус и показывает блок', () => {
    const data = makeData();
    (data as any).debtorStatusHint = 'absent';
    (data as any).recommendedActs = { entityType: 'legal' };
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
    expect(screen.getByText('Информация по счетам')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отсутствующий' })).toHaveAttribute('aria-pressed', 'true');
  });
});

// Блок «Сведения о смерти» виден только при статусе «Умерший» (физлицо).
describe('DocumentAnalysis — блок «Сведения о смерти»', () => {
  const renderForm = () =>
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={makeData()}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );

  it('по умолчанию блок скрыт', () => {
    renderForm();
    expect(screen.queryByText('Сведения о смерти')).not.toBeInTheDocument();
  });

  it('выбор «Умерший» (физлицо) показывает блок, снятие — скрывает', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Умерший' }));
    expect(screen.getByText('Сведения о смерти')).toBeInTheDocument();
    expect(screen.getByText('ФИО нотариуса:')).toBeInTheDocument();
    expect(screen.getByText('Адрес нотариуса:')).toBeInTheDocument();
    expect(screen.getByText('Дата смерти:')).toBeInTheDocument();
    expect(screen.getByText('Свидетельство о смерти:')).toBeInTheDocument();
    // Повторный клик снимает статус — блок исчезает.
    fireEvent.click(screen.getByRole('button', { name: 'Умерший' }));
    expect(screen.queryByText('Сведения о смерти')).not.toBeInTheDocument();
  });

  it('у ЮЛ кнопки «Умерший» нет — блок недостижим', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    expect(screen.queryByRole('button', { name: 'Умерший' })).not.toBeInTheDocument();
    expect(screen.queryByText('Сведения о смерти')).not.toBeInTheDocument();
  });

  it('debtorStatusHint=deceased с бэка автопроставляет статус, показывает блок и наследников', () => {
    const data = makeData();
    (data as any).debtorStatusHint = 'deceased';
    (data as any).recommendedActs = { entityType: 'individual' };
    (data as any).heirs = [{ name: 'Ким Эмма Николаевна', address: '346744, Ростовская обл.' }];
    data.fields = { ...data.fields, deathDate: '13.05.2015' };
    render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
    expect(screen.getByText('Сведения о смерти')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Умерший' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByDisplayValue('13.05.2015')).toBeInTheDocument();
    // Наследник из заявления подставлен, хотя backend отдал его без id.
    expect(screen.getByText('Наследник 1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Ким Эмма Николаевна')).toBeInTheDocument();
  });

  it('добавление наследника создаёт новую карточку', () => {
    renderForm();
    fireEvent.click(screen.getByRole('radio', { name: 'Физ.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Умерший' }));
    expect(screen.queryByText('Наследник 1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить наследника' }));
    expect(screen.getByText('Наследник 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Удалить наследника' }));
    expect(screen.queryByText('Наследник 1')).not.toBeInTheDocument();
  });
});

// Режим «Ипотека»: скрыты банкротные блоки, показаны созаёмщик/поручитель/предмет.
describe('DocumentAnalysis — режим «Ипотека»', () => {
  const renderMortgage = (mutate?: (d: ExtractedData) => void) => {
    const data = makeData();
    data.fields = { ...data.fields, creditorName: 'ПАО Сбербанк' };
    if (mutate) mutate(data);
    return render(
      <DocumentAnalysis
        documentData={documentData}
        extractedData={data}
        mode="mortgage"
        onAnalysisComplete={() => {}}
        onBack={() => {}}
      />,
    );
  };

  it('скрывает управляющего, залог, выбор актов, сведения о взыскании', () => {
    renderMortgage();
    expect(screen.queryByText('Арбитражный управляющий')).not.toBeInTheDocument();
    expect(screen.queryByText('Залог')).not.toBeInTheDocument();
    expect(screen.queryByText('Выбор судебных актов')).not.toBeInTheDocument();
    expect(screen.queryByText('Сведения о взыскании')).not.toBeInTheDocument();
  });

  it('показывает истца, ответчика, представителя, созаёмщика, поручителя, третьё лицо, предмет ипотеки', () => {
    renderMortgage();
    expect(screen.getByText('Информация об истце')).toBeInTheDocument();
    expect(screen.getByText('Данные ответчика')).toBeInTheDocument();
    expect(screen.getByText('Представитель истца')).toBeInTheDocument();
    expect(screen.getByText('Представитель ответчика')).toBeInTheDocument();
    expect(screen.getByText('Созаёмщик')).toBeInTheDocument();
    expect(screen.getByText('Информация о поручителе')).toBeInTheDocument();
    expect(screen.getByText('Третьи лица')).toBeInTheDocument();
    expect(screen.getByText('Предмет ипотеки')).toBeInTheDocument();
  });

  it('оставляет общие блоки: судебная информация, обязательства', () => {
    renderMortgage();
    expect(screen.getByText('Судебная информация')).toBeInTheDocument();
    expect(screen.getByText(/Обязательство 1/)).toBeInTheDocument();
  });

  it('ответчик ← ВСЕ должники; созаёмщик/поручитель пустые; третьё лицо ← третьи лица', () => {
    renderMortgage((d) => {
      d.debtors = [
        { id: 'd1', name: 'Первый Ответчик', inn: '111', address: 'адрес1' },
        { id: 'd2', name: 'Второй Ответчик', inn: '222', address: 'адрес2' },
      ];
      d.thirdParties = [{ id: 'tp1', name: 'Третье Лицо Пётр', inn: '333', address: 'адрес3' }];
    });
    // Оба должника — ответчики.
    expect(screen.getByText('Ответчик 1')).toBeInTheDocument();
    expect(screen.getByText('Ответчик 2')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Первый Ответчик')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Второй Ответчик')).toBeInTheDocument();
    // Третье лицо подставлено из thirdParties.
    expect(screen.getByDisplayValue('Третье Лицо Пётр')).toBeInTheDocument();
    // Созаёмщик и поручитель пустые (без карточек).
    expect(screen.queryByText('Созаёмщик 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Поручитель 1')).not.toBeInTheDocument();
  });

  it('ввод «Ворошиловский районный суд» подставляет email и сайт по умолчанию', () => {
    renderMortgage();
    const courtInput = screen.getByPlaceholderText('Арбитражный суд Ростовской области');
    fireEvent.change(courtInput, { target: { value: 'Ворошиловский районный суд г. Ростова-на-Дону' } });
    expect(screen.getByDisplayValue('voroshilovsky.ros@sudrf.ru')).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://voroshilovsky--ros.sudrf.ru/')).toBeInTheDocument();
  });

  it('«Добавить созаёмщика»/«Добавить поручителя» создают карточки', () => {
    renderMortgage();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить созаёмщика' }));
    expect(screen.getByText('Созаёмщик 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить поручителя' }));
    expect(screen.getByText('Поручитель 1')).toBeInTheDocument();
  });
});
