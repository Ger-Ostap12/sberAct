import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Раздельные наборы финальных актов: инициирование против включения в РТК.

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
  fields: { courtName: 'Арбитражный суд', caseNumber: 'A-1', creditorName: 'ПАО Сбербанк' },
  obligations: [],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

const renderForm = (mutate?: (d: ExtractedData) => void) => {
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

const box = (name: RegExp | string) => screen.getByRole('checkbox', { name });
const noBox = (name: RegExp | string) => screen.queryByRole('checkbox', { name });
const выбратьЛицо = (name: string) => fireEvent.click(screen.getByRole('radio', { name }));
const выбратьВид = (name: string) => fireEvent.click(screen.getByRole('radio', { name }));

describe('инициирование: набор по типу лица', () => {
  it('физлицо — реализация и реструктуризация', () => {
    renderForm();
    выбратьЛицо('Физ.лицо');
    expect(box(/Решение реализация/)).toBeChecked();
    expect(box(/Определение реструктуризация/)).toBeChecked();
    expect(box(/Решение конкурсное/)).not.toBeChecked();
    expect(box(/Определение Наблюдение/)).not.toBeChecked();
  });

  it('ИП — тот же набор, что у физлица', () => {
    renderForm();
    выбратьЛицо('ИП');
    expect(box(/Решение реализация/)).toBeChecked();
    expect(box(/Определение реструктуризация/)).toBeChecked();
  });

  it('юрлицо — конкурсное и наблюдение', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    expect(box(/Решение конкурсное/)).toBeChecked();
    expect(box(/Определение Наблюдение/)).toBeChecked();
    expect(box(/Решение реализация/)).not.toBeChecked();
  });

  it('КФХ — как юрлицо', () => {
    renderForm();
    выбратьЛицо('Глава КФХ');
    expect(box(/Решение конкурсное/)).toBeChecked();
    expect(box(/Определение Наблюдение/)).toBeChecked();
  });

  it('акта включения в РТК в этом окне нет', () => {
    renderForm();
    выбратьЛицо('Физ.лицо');
    expect(noBox(/ВКЛ в РТК/)).not.toBeInTheDocument();
    expect(noBox(/включение в РТК/)).not.toBeInTheDocument();
  });

  it('смена типа лица пересчитывает набор', () => {
    renderForm();
    выбратьЛицо('Физ.лицо');
    expect(box(/Решение реализация/)).toBeChecked();
    выбратьЛицо('Юр.лицо');
    expect(box(/Решение реализация/)).not.toBeChecked();
    expect(box(/Решение конкурсное/)).toBeChecked();
  });
});

describe('инициирование: статус лица старше типа', () => {
  it('ликвидируемое ЮЛ — только конкурсное, наблюдения не бывает', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    fireEvent.click(screen.getByRole('button', { name: 'Ликвидируемый' }));
    expect(box(/Решение конкурсное/)).toBeChecked();
    expect(box(/Определение Наблюдение/)).not.toBeChecked();
  });

  it('отсутствующее ЮЛ — тоже только конкурсное', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    fireEvent.click(screen.getByRole('button', { name: 'Отсутствующий' }));
    expect(box(/Решение конкурсное/)).toBeChecked();
    expect(box(/Определение Наблюдение/)).not.toBeChecked();
  });

  it('умерший — только реализация, но выбор остальных не закрыт', () => {
    renderForm();
    выбратьЛицо('Физ.лицо');
    fireEvent.click(screen.getByRole('button', { name: 'Умерший' }));
    expect(box(/Решение реализация/)).toBeChecked();
    expect(box(/Определение реструктуризация/)).not.toBeChecked();
    expect(box(/Определение реструктуризация/)).toBeEnabled();
    fireEvent.click(box(/Определение реструктуризация/));
    expect(box(/Определение реструктуризация/)).toBeChecked();
  });
});

describe('включение в РТК: виды акта по типу лица', () => {
  it('физлицу — реализация, реструктуризация, за реестр', () => {
    renderForm();
    выбратьЛицо('Физ.лицо');
    выбратьВид('Включение в РТК');
    expect(box(/РТК реализация/)).toBeInTheDocument();
    expect(box(/РТК реструктуризация/)).toBeInTheDocument();
    expect(box(/За реестр/)).toBeInTheDocument();
    expect(noBox(/РТК конкурсное/)).not.toBeInTheDocument();
    expect(noBox(/РТК наблюдение/)).not.toBeInTheDocument();
  });

  it('юрлицу — конкурсное, наблюдение, за реестр', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    выбратьВид('Включение в РТК');
    expect(box(/РТК конкурсное/)).toBeInTheDocument();
    expect(box(/РТК наблюдение/)).toBeInTheDocument();
    expect(box(/За реестр/)).toBeInTheDocument();
    expect(noBox(/РТК реализация/)).not.toBeInTheDocument();
  });

  it('процедурных актов инициирования в этом окне нет', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    выбратьВид('Включение в РТК');
    expect(noBox(/Решение конкурсное/)).not.toBeInTheDocument();
    expect(noBox(/Определение Наблюдение/)).not.toBeInTheDocument();
  });

  it('виды взаимоисключающие: выбор другого снимает прежний', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    выбратьВид('Включение в РТК');
    fireEvent.click(box(/РТК конкурсное/));
    expect(box(/РТК конкурсное/)).toBeChecked();
    fireEvent.click(box(/За реестр/));
    expect(box(/За реестр/)).toBeChecked();
    expect(box(/РТК конкурсное/)).not.toBeChecked();
  });

  it('смена типа лица сбрасывает вид, чужой новому типу', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    выбратьВид('Включение в РТК');
    fireEvent.click(box(/РТК наблюдение/));
    выбратьЛицо('Физ.лицо');
    expect(box(/РТК реализация/)).not.toBeChecked();
    expect(box(/РТК реструктуризация/)).not.toBeChecked();
  });

  it('«За реестр» переживает смену типа лица: он есть в обоих наборах', () => {
    renderForm();
    выбратьЛицо('Юр.лицо');
    выбратьВид('Включение в РТК');
    fireEvent.click(box(/За реестр/));
    выбратьЛицо('Физ.лицо');
    expect(box(/За реестр/)).toBeChecked();
  });
});

describe('включение в РТК: подстановка по введённой процедуре', () => {
  const сПроцедурой = (значение: string) => (d: ExtractedData) => {
    d.fields = { ...d.fields, introducedProcedure: значение };
    (d as any).recommendedActs = { recommendedActIds: ['final_rtk_inclusion'] };
  };

  it('ЮЛ и «введено конкурсное производство» — отмечено конкурсное', () => {
    renderForm(сПроцедурой('competition'));
    выбратьЛицо('Юр.лицо');
    expect(box(/РТК конкурсное/)).toBeChecked();
  });

  it('ЮЛ и наблюдение — отмечено наблюдение', () => {
    renderForm(сПроцедурой('observation'));
    выбратьЛицо('Юр.лицо');
    expect(box(/РТК наблюдение/)).toBeChecked();
  });

  it('ФЛ и реализация — отмечена реализация, рядом чип «Рекомендуется»', () => {
    renderForm(сПроцедурой('realization'));
    выбратьЛицо('Физ.лицо');
    expect(box(/РТК реализация/)).toBeChecked();
    expect(screen.getByText('Рекомендуется')).toBeInTheDocument();
  });

  it('ФЛ и реструктуризация — отмечена реструктуризация', () => {
    renderForm(сПроцедурой('restructuring'));
    выбратьЛицо('Физ.лицо');
    expect(box(/РТК реструктуризация/)).toBeChecked();
  });

  it('процедура, чужая типу лица, не подставляется', () => {
    // Документ сказал «конкурсное», юрист выбрал физлицо — решает он сам.
    renderForm(сПроцедурой('competition'));
    выбратьЛицо('Физ.лицо');
    expect(box(/РТК реализация/)).not.toBeChecked();
    expect(box(/РТК реструктуризация/)).not.toBeChecked();
    expect(box(/За реестр/)).not.toBeChecked();
  });

  it('без процедуры в документе ничего не подставляем', () => {
    renderForm(d => {
      (d as any).recommendedActs = { recommendedActIds: ['final_rtk_inclusion'] };
    });
    выбратьЛицо('Юр.лицо');
    expect(box(/РТК конкурсное/)).not.toBeChecked();
    expect(box(/РТК наблюдение/)).not.toBeChecked();
  });

  it('выбор юриста переживает повторный рендер и не возвращается к подстановке', () => {
    renderForm(сПроцедурой('competition'));
    выбратьЛицо('Юр.лицо');
    fireEvent.click(box(/РТК наблюдение/));
    expect(box(/РТК наблюдение/)).toBeChecked();
    // Переключение чужой кнопки (залог) контекст финальных актов не меняет.
    fireEvent.click(box('Залог ТС'));
    expect(box(/РТК наблюдение/)).toBeChecked();
  });
});
