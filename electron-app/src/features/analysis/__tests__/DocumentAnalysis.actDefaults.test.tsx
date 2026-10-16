import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData } from '../../../types';

// Умолчания окон актов и связь залогового акта с карточками залога.

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

const renderForm = (mutate?: (d: ExtractedData) => void, onDone: (d: ExtractedData) => void = () => {}) => {
  const data = makeData();
  if (mutate) mutate(data);
  return render(
    <DocumentAnalysis
      documentData={documentData}
      extractedData={data}
      onAnalysisComplete={onDone}
      onBack={() => {}}
    />,
  );
};

const checkbox = (name: string) => screen.getByRole('checkbox', { name });

const ПРИНЯТИЕ = [
  'Определение о принятии',
  'Определение Б/Д нет ГП',
  'Определение Б/Д иное',
  'Принятие после Б/Д',
];
// Акты упрощёнки сюда не входят: они зависят от вида заявления и проверены
// в DocumentAnalysis.intermediateActs.test.tsx.
const ПРОМЕЖУТОЧНЫЕ = [
  'Отложение',
  'Общий возврат',
  'Возврат нет ГП',
  'Продление Б/Д',
];

describe('умолчания окон «Принятие» и «Промежуточные»', () => {
  it('все акты принятия, кроме залогового, отмечены сразу', () => {
    renderForm();
    ПРИНЯТИЕ.forEach(name => expect(checkbox(name)).toBeChecked());
  });

  it('все промежуточные акты отмечены сразу', () => {
    renderForm();
    ПРОМЕЖУТОЧНЫЕ.forEach(name => expect(checkbox(name)).toBeChecked());
  });

  it('«Резолютивная часть» отмечена сразу', () => {
    renderForm();
    expect(checkbox('Резолютивная часть')).toBeChecked();
  });

  it('рекомендации бэкенда не снимают галки принятия и промежуточных', () => {
    renderForm(d => {
      (d as any).recommendedActs = { entityType: 'legal', recommendedActIds: ['final_competition'] };
    });
    ПРИНЯТИЕ.forEach(name => expect(checkbox(name)).toBeChecked());
    ПРОМЕЖУТОЧНЫЕ.forEach(name => expect(checkbox(name)).toBeChecked());
    expect(screen.getByRole('checkbox', { name: /Решение конкурсное/ })).toBeChecked();
  });

  it('чип «Рекомендуется» остался только в окне финальных актов', () => {
    renderForm(d => {
      (d as any).recommendedActs = {
        entityType: 'legal',
        recommendedActIds: ['final_competition', 'acceptance_definition', 'intermediate_return'],
      };
    });
    const чипы = screen.getAllByText('Рекомендуется');
    expect(чипы).toHaveLength(1);
    // Чип стоит у финального акта, а не у «Определения о принятии».
    const финальное = screen.getByText('3. Финальные СА').closest('.MuiAccordion-root') as HTMLElement;
    expect(within(финальное).getByText('Рекомендуется')).toBeInTheDocument();
  });
});

describe('залоговый акт принятия идёт за составом залога', () => {
  const квартира = [{
    id: 'c1', collateralType: 'real_estate', objectName: 'Квартира',
  }] as ExtractedData['collaterals'];

  it('без залога акт снят, но юрист может поставить его руками', () => {
    renderForm();
    expect(checkbox('Определение Б/Д нет ГП залог')).not.toBeChecked();
    fireEvent.click(checkbox('Определение Б/Д нет ГП залог'));
    expect(checkbox('Определение Б/Д нет ГП залог')).toBeChecked();
  });

  // Залоговый акт есть только у включения в РТК: форма стартует с инициирования,
  // где он погашен, поэтому вид переключаем явно.
  const включение = () => fireEvent.click(screen.getByRole('radio', { name: 'Включение в РТК' }));

  it('залог из документа отмечает и вид залога, и залоговый акт', () => {
    renderForm(d => { d.collaterals = квартира; });
    expect(checkbox('Залог недвижимость')).toBeChecked();
    включение();
    expect(checkbox('Определение Б/Д нет ГП залог')).toBeChecked();
  });

  it('карточка, добавленная вручную, поднимает вид залога и залоговый акт', () => {
    renderForm();
    включение();
    expect(checkbox('Без залога')).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить залог' }));
    // Новая карточка создаётся с типом «Недвижимость».
    expect(checkbox('Залог недвижимость')).toBeChecked();
    expect(checkbox('Без залога')).not.toBeChecked();
    expect(checkbox('Определение Б/Д нет ГП залог')).toBeChecked();
  });

  it('удаление последней карточки возвращает «Без залога» и снимает залоговый акт', () => {
    renderForm(d => { d.collaterals = квартира; });
    fireEvent.click(screen.getByLabelText('Удалить залог'));
    expect(checkbox('Без залога')).toBeChecked();
    expect(checkbox('Залог недвижимость')).not.toBeChecked();
    expect(checkbox('Определение Б/Д нет ГП залог')).not.toBeChecked();
  });
});

describe('карточки залога — источник истины для галок вида', () => {
  const квартира = [{
    id: 'c1', collateralType: 'real_estate', objectName: 'Квартира',
  }] as ExtractedData['collaterals'];

  it('снять галку вида при живой карточке нельзя — предупреждаем', () => {
    renderForm(d => { d.collaterals = квартира; });
    fireEvent.click(checkbox('Залог недвижимость'));
    expect(checkbox('Залог недвижимость')).toBeChecked();
    expect(screen.getByText(/подтверждён карточкой/)).toBeInTheDocument();
  });

  it('«Без залога» при живой карточке тоже не выбрать', () => {
    renderForm(d => { d.collaterals = квартира; });
    fireEvent.click(checkbox('Без залога'));
    expect(checkbox('Без залога')).not.toBeChecked();
    expect(screen.getByText(/удалите их, чтобы выбрать/)).toBeInTheDocument();
  });

  it('галку вида без карточек снять можно', () => {
    renderForm();
    fireEvent.click(checkbox('Залог ТС'));
    expect(checkbox('Залог ТС')).toBeChecked();
    fireEvent.click(checkbox('Залог ТС'));
    expect(checkbox('Залог ТС')).not.toBeChecked();
  });
});

describe('генерация не идёт, пока отмеченный вид залога не подтверждён карточкой', () => {
  it('галка без карточки блокирует переход и объясняет почему', () => {
    const onDone = jest.fn();
    renderForm(undefined, onDone);
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(checkbox('Залог ТС'));
    fireEvent.click(screen.getByRole('button', { name: /Продолжить|Перейти/ }));
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByText(/Залог ТС.*карточка залога не заполнена/s)).toBeInTheDocument();
  });

  it('пустая карточка нужного вида генерацию тоже не пускает', () => {
    const onDone = jest.fn();
    renderForm(undefined, onDone);
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: 'Добавить залог' }));
    fireEvent.click(screen.getByRole('button', { name: /Продолжить|Перейти/ }));
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByText(/Залог недвижимость.*карточка залога не заполнена/s)).toBeInTheDocument();
  });

  it('заполненная карточка пропускает генерацию', () => {
    const onDone = jest.fn();
    renderForm(d => {
      d.collaterals = [{ id: 'c1', collateralType: 'real_estate', objectName: 'Квартира' }] as ExtractedData['collaterals'];
    }, onDone);
    fireEvent.click(screen.getByRole('radio', { name: 'Юр.лицо' }));
    fireEvent.click(screen.getByRole('button', { name: /Продолжить|Перейти/ }));
    expect(onDone).toHaveBeenCalled();
  });
});

describe('ФНС и акт «Б/Д нет ГП»', () => {
  const фнс = (d: ExtractedData) => {
    d.fields = { ...d.fields, creditorName: 'ФНС России в лице Межрайонной ИФНС № 13' };
  };

  it('у ФНС галка снята: госпошлины не бывает', () => {
    renderForm(фнс);
    expect(checkbox('Определение Б/Д нет ГП')).not.toBeChecked();
  });

  it('у банка галка стоит', () => {
    renderForm();
    expect(checkbox('Определение Б/Д нет ГП')).toBeChecked();
  });

  it('остальные акты принятия у ФНС не трогаются', () => {
    renderForm(фнс);
    expect(checkbox('Определение о принятии')).toBeChecked();
    expect(checkbox('Определение Б/Д иное')).toBeChecked();
    expect(checkbox('Принятие после Б/Д')).toBeChecked();
  });

  it('юрист может поставить галку руками', () => {
    renderForm(фнс);
    fireEvent.click(checkbox('Определение Б/Д нет ГП'));
    expect(checkbox('Определение Б/Д нет ГП')).toBeChecked();
  });
});
