import { ExtractedData, TemplateType } from './types';

// Каталог доступных шаблонов судебных актов.
// Раньше жил в компоненте TemplateSelection; вынесен сюда, чтобы автоподбор
// можно было выполнять без отдельной страницы выбора (App → сразу предпросмотр).
export const ALL_TEMPLATES: TemplateType[] = [
  {
    id: 'rtk_single_obligation',
    name: 'Решение о включении в РТК (одно обязательство)',
    description: 'Шаблон для судебного акта о включении в реестр требований кредиторов по одному обязательству',
    category: 'РТК',
    fields: [
      { name: 'applicantName', label: 'ФИО заявителя', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'debtAmount', label: 'Сумма долга', type: 'number', required: true },
      { name: 'creditorName', label: 'Кредитор', type: 'text', required: true },
      { name: 'debtorName', label: 'Должник', type: 'text', required: true }
    ]
  },
  {
    id: 'rtk_multiple_obligations',
    name: 'Решение о включении в РТК (несколько обязательств)',
    description: 'Шаблон для судебного акта о включении в реестр требований кредиторов по нескольким обязательствам',
    category: 'РТК',
    fields: [
      { name: 'applicantName', label: 'ФИО заявителя', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalAmount', label: 'Общая сумма долга', type: 'number', required: true },
      { name: 'obligationsCount', label: 'Количество обязательств', type: 'number', required: true }
    ]
  },
  {
    id: 'mortgage',
    name: 'Решение по ипотеке',
    description: 'Шаблон решения суда по ипотечному иску с предметом залога',
    category: 'Ипотека',
    fields: [
      { name: 'mortgageCourtName002', label: 'Суд [002]', type: 'text', required: true },
      { name: 'mortgageCourtAddress001', label: 'Адрес суда [001]', type: 'text', required: false },
      { name: 'mortgageRepresentative22', label: 'Представитель истца [2.2]', type: 'text', required: false },
      { name: 'mortgageCreditAmount111', label: 'Сумма кредита [111]', type: 'text', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true },
      { name: 'mortgageStartingPrice1225', label: 'Начальная цена продажи [1225]', type: 'text', required: true }
    ]
  },
  {
    id: 'initiation_physical',
    name: 'Инициирование банкротства (физ лицо)',
    description: 'Комплект актов: принятие заявления, введение реструктуризации и введение реализации имущества',
    category: 'Инициирование',
    fields: [
      { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true }
    ]
  },
  {
    id: 'initiation_legal',
    name: 'Инициирование банкротства (юр лицо)',
    description: 'Комплект актов: принятие заявления и введение наблюдения',
    category: 'Инициирование',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true },
      { name: 'debtSnapshotDate88', label: 'Дата состояния задолженности [88]', type: 'text', required: false }
    ]
  },
  {
    id: 'initiation_legal_competition_absent',
    name: 'Инициирование ЮЛ конкурсное (отсутствующий)',
    description: 'Комплект актов: принятие заявления, наблюдение и конкурсное (отсутствующий должник)',
    category: 'Инициирование',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true },
      { name: 'debtSnapshotDate88', label: 'Дата состояния задолженности [88]', type: 'text', required: false }
    ]
  },
  {
    id: 'initiation_legal_competition_liquidation',
    name: 'Инициирование ЮЛ конкурсное (ликвидируемый)',
    description: 'Комплект актов: принятие заявления, наблюдение и конкурсное (ликвидируемый должник)',
    category: 'Инициирование',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true },
      { name: 'debtSnapshotDate88', label: 'Дата состояния задолженности [88]', type: 'text', required: false }
    ]
  },
  {
    id: 'observation_single',
    name: 'Наблюдение (одно обязательство)',
    description: 'Комплект актов по процедуре наблюдения для юридического лица с одним обязательством',
    category: 'Наблюдение',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
    ]
  },
  {
    id: 'observation_multiple',
    name: 'Наблюдение (несколько обязательств)',
    description: 'Комплект актов по процедуре наблюдения для юридического лица с несколькими обязательствами',
    category: 'Наблюдение',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
    ]
  },
  {
    id: 'observation_collateral',
    name: 'Наблюдение с залогом',
    description: 'Комплект актов по процедуре наблюдения для юридического лица с залогом',
    category: 'Наблюдение',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'competition_collateral',
    name: 'Конкурсное производство с залогом',
    description: 'Комплект актов по процедуре конкурсного производства для юридического лица с залогом',
    category: 'Конкурсное',
    fields: [
      { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'ip_enforcement_realization',
    name: 'ИП Реализация (без залога)',
    description: 'Комплект актов для взыскания с ИП в процедуре реализации (принятие иска и решение)',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'creditAmount', label: 'Сумма кредита', type: 'number', required: true },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true }
    ]
  },
  {
    id: 'ip_enforcement_realization_collateral',
    name: 'ИП Реализация (с залогом)',
    description: 'Комплект актов для взыскания с ИП в процедуре реализации с залогом',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'ip_enforcement_restructuring',
    name: 'ИП Реструктуризация (без залога)',
    description: 'Комплект актов для взыскания с ИП в процедуре реструктуризации (принятие иска и решение)',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'creditAmount', label: 'Сумма кредита', type: 'number', required: true },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true }
    ]
  },
  {
    id: 'ip_enforcement_restructuring_collateral',
    name: 'ИП Реструктуризация (с залогом)',
    description: 'Комплект актов для взыскания с ИП в процедуре реструктуризации с залогом',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'ip_collection',
    name: 'Взыскания ИП',
    description: 'Комплект актов для искового заявления о взыскании с ИП: принятие иска и решение',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'bankCommission', label: 'Комиссия Банка [122]', type: 'number', required: false },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true }
    ]
  },
  {
    id: 'ip_collection_collateral',
    name: 'Взыскания ИП + Залог',
    description: 'Комплект актов для искового заявления о взыскании с ИП с залогом: принятие иска и решение',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'bankCommission', label: 'Комиссия Банка [122]', type: 'number', required: false },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'date', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'ip_collection_collateral_auto',
    name: 'Взыскание ИП залог авто',
    description: 'Комплект актов для искового заявления о взыскании с ИП с залогом авто: принятие иска и решение. [1221] — описание авто (марка, модель, год, VIN).',
    category: 'ИП',
    fields: [
      { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
      { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
      { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
      { name: 'bankCommission', label: 'Комиссия Банка [122]', type: 'number', required: false },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'date', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога (авто) [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'legal_collection',
    name: 'Взыскание с ЮЛ',
    description: 'Комплект актов для искового заявления о взыскании с юридического лица: принятие иска и решение',
    category: 'ЮЛ',
    fields: [
      { name: 'applicantName', label: 'Название организации', type: 'text', required: true },
      { name: 'inn', label: 'ИНН', type: 'text', required: true },
      { name: 'ogrn', label: 'ОГРН', type: 'text', required: true },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true },
      { name: 'forfeit15', label: 'Неустойка', type: 'number', required: false },
      { name: 'totalDebt', label: 'Общая сумма долга', type: 'number', required: true }
    ]
  },
  {
    id: 'legal_collection_collateral',
    name: 'Взыскание с ЮЛ + Залог',
    description: 'Комплект актов для искового заявления о взыскании с ЮЛ с залогом: принятие иска и решение',
    category: 'ЮЛ',
    fields: [
      { name: 'applicantName', label: 'Название организации', type: 'text', required: true },
      { name: 'inn', label: 'ИНН', type: 'text', required: true },
      { name: 'ogrn', label: 'ОГРН', type: 'text', required: true },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true },
      { name: 'forfeit15', label: 'Неустойка', type: 'number', required: false },
      { name: 'totalDebt', label: 'Общая сумма долга', type: 'number', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'date', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'legal_collection_collateral_auto',
    name: 'Взыскание с ЮЛ залог авто',
    description: 'Комплект актов для искового заявления о взыскании с ЮЛ с залогом авто: принятие иска и решение. [1221] — описание авто (марка, модель, год, VIN).',
    category: 'ЮЛ',
    fields: [
      { name: 'applicantName', label: 'Название организации', type: 'text', required: true },
      { name: 'inn', label: 'ИНН', type: 'text', required: true },
      { name: 'ogrn', label: 'ОГРН', type: 'text', required: true },
      { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
      { name: 'interest14', label: 'Проценты', type: 'number', required: true },
      { name: 'forfeit15', label: 'Неустойка', type: 'number', required: false },
      { name: 'totalDebt', label: 'Общая сумма долга', type: 'number', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'date', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога (авто) [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'physical_realization_collateral',
    name: 'Реализация ФЛ с залогом',
    description: 'Комплект актов для реализации имущества физического лица с залогом',
    category: 'Реализация',
    fields: [
      { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'physical_restructuring_collateral',
    name: 'Реструктуризация ФЛ с залогом',
    description: 'Комплект актов для реструктуризации долгов физического лица с залогом',
    category: 'Реструктуризация',
    fields: [
      { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'kfh_observation',
    name: 'КФХ',
    description: 'Комплект актов для КФХ (наблюдение): принятие заявления и введение наблюдения',
    category: 'КФХ',
    fields: [
      { name: 'applicantName', label: 'Глава КФХ ИП (ФИО)', type: 'text', required: true },
      { name: 'kfhHeadName', label: 'ФИО главы КФХ', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
    ]
  },
  {
    id: 'kfh_observation_collateral',
    name: 'КФХ с залогом',
    description: 'Комплект актов для КФХ (наблюдение с залогом): принятие заявления и введение наблюдения',
    category: 'КФХ',
    fields: [
      { name: 'applicantName', label: 'Глава КФХ ИП (ФИО)', type: 'text', required: true },
      { name: 'kfhHeadName', label: 'ФИО главы КФХ', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
      { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
      { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
      { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
    ]
  },
  {
    id: 'deceased',
    name: 'Умерший',
    description: 'Комплект актов для процедуры банкротства умершего должника: принятие заявления и решение',
    category: 'Умерший',
    fields: [
      { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
      { name: 'courtName', label: 'Название суда', type: 'text', required: true },
      { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
      { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
    ]
  },
];

const getSourceDocumentType = (extractedData: ExtractedData): string =>
  (extractedData.fields && (extractedData.fields as any).sourceDocumentType) ||
  extractedData.documentType ||
  '';

const hasFilledCollaterals = (extractedData: ExtractedData): boolean => {
  const list = extractedData.collaterals;
  if (!list?.length) return false;
  return list.some(
    (c) =>
      (c.objectName && c.objectName.trim() !== '') ||
      (c.collateralValue && c.collateralValue.trim() !== '') ||
      (c.cadastralNumber && c.cadastralNumber.trim() !== '') ||
      (c.address && c.address.trim() !== '') ||
      (c.vin && c.vin.trim() !== '') ||
      (c.brandModel && c.brandModel.trim() !== '')
  );
};

/**
 * Определяет id рекомендуемого шаблона по результатам анализа.
 * Логика перенесена 1:1 из бывшего компонента TemplateSelection (loadTemplates).
 */
const pickTemplateId = (extractedData: ExtractedData): string => {
  let sourceDocumentType = getSourceDocumentType(extractedData);

  // Если приложение не определило залог, но пользователь заполнил блок залога — считаем акты с залогом
  if (hasFilledCollaterals(extractedData)) {
    const toCollateral: Record<string, string> = {
      competition: 'competition_collateral',
      ip_collection: 'ip_collection_collateral',
      legal_collection: 'legal_collection_collateral',
      ip_enforcement_realization: 'ip_enforcement_realization_collateral',
      ip_enforcement_restructuring: 'ip_enforcement_restructuring_collateral',
      physical_realization: 'physical_realization_collateral',
      physical_restructuring: 'physical_restructuring_collateral',
      ip_enforcement_statement: 'ip_enforcement_statement_collateral'
    };
    sourceDocumentType = toCollateral[sourceDocumentType] || sourceDocumentType;
  }

  if (sourceDocumentType === 'mortgage_claim') {
    return 'mortgage';
  } else if (sourceDocumentType === 'competition_collateral') {
    return 'competition_collateral';
  } else if (sourceDocumentType === 'physical_restructuring_collateral') {
    return 'physical_restructuring_collateral';
  } else if (sourceDocumentType === 'physical_realization_collateral') {
    return 'physical_realization_collateral';
  } else if (sourceDocumentType === 'ip_collection_collateral_auto') {
    return 'ip_collection_collateral_auto';
  } else if (sourceDocumentType === 'ip_collection_collateral') {
    return 'ip_collection_collateral';
  } else if (sourceDocumentType === 'ip_collection') {
    return 'ip_collection';
  } else if (sourceDocumentType === 'legal_collection_collateral_auto') {
    return 'legal_collection_collateral_auto';
  } else if (sourceDocumentType === 'legal_collection_collateral') {
    return 'legal_collection_collateral';
  } else if (sourceDocumentType === 'legal_collection') {
    return 'legal_collection';
  } else if (sourceDocumentType === 'ip_enforcement_realization') {
    return 'ip_enforcement_realization';
  } else if (sourceDocumentType === 'ip_enforcement_realization_collateral') {
    return 'ip_enforcement_realization_collateral';
  } else if (sourceDocumentType === 'ip_enforcement_restructuring') {
    return 'ip_enforcement_restructuring';
  } else if (sourceDocumentType === 'ip_enforcement_restructuring_collateral') {
    return 'ip_enforcement_restructuring_collateral';
  } else if (sourceDocumentType === 'ip_enforcement_statement' || sourceDocumentType === 'ip_enforcement_statement_collateral') {
    // Для обратной совместимости - по умолчанию реализация
    return sourceDocumentType === 'ip_enforcement_statement_collateral'
      ? 'ip_enforcement_realization_collateral'
      : 'ip_enforcement_realization';
  } else if (sourceDocumentType === 'initiation_physical') {
    return 'initiation_physical';
  } else if (sourceDocumentType === 'initiation_legal') {
    return 'initiation_legal_competition_absent';
  } else if ((extractedData.fields as any)?.procedureType === 'deceased' ||
             (extractedData.fields as any)?.procedureTypeRaw?.toLowerCase().includes('умер') ||
             (extractedData.fields as any)?.procedureTypeRaw?.toLowerCase().includes('умерший') ||
             (extractedData.fields as any)?.procedureTypeRaw?.toLowerCase().includes('смерть')) {
    return 'deceased';
  } else if (extractedData.fields?.isKfh || (extractedData.fields as any)?.isKfh) {
    const hasCollateral = extractedData.fields?.ipCollateralContractNumber ||
                          extractedData.fields?.mortgageCollateralDescription1221 ||
                          sourceDocumentType === 'observation_collateral' ||
                          hasFilledCollaterals(extractedData);
    return hasCollateral ? 'kfh_observation_collateral' : 'kfh_observation';
  } else if (extractedData.entityType === 'legal' || extractedData.fields?.entityType === 'legal') {
    const obligationsCount = extractedData.obligations?.length || 0;
    if (hasFilledCollaterals(extractedData)) {
      return 'observation_collateral';
    }
    return obligationsCount > 1 ? 'observation_multiple' : 'observation_single';
  } else if (sourceDocumentType === 'rtk_application' || extractedData.documentType === 'rtk_application') {
    const obligationsCount = extractedData.obligations?.length || 0;
    return obligationsCount > 1 ? 'rtk_multiple_obligations' : 'rtk_single_obligation';
  }

  // Фолбэк, если ни одна ветка не сработала: одиночное РТК (наиболее общий акт).
  return 'rtk_single_obligation';
};

/**
 * Возвращает полностью автоматически подобранный шаблон судебного акта.
 * Используется в App при переходе анализ → предпросмотр (страница выбора удалена).
 */
export const pickTemplate = (extractedData: ExtractedData): TemplateType => {
  const id = pickTemplateId(extractedData);
  const tpl = ALL_TEMPLATES.find((t) => t.id === id);
  if (!tpl) {
    // Теоретически недостижимо: pickTemplateId всегда возвращает существующий id.
    return ALL_TEMPLATES[0];
  }
  return tpl;
};
