export interface DocumentData {
  filePath: string;
  fileName: string;
  fileSize: number;
  uploadDate: Date;
}

export interface Obligation {
  id: string;
  contractNumber: string;
  contractDate: string;
  obligationType: string;
  /** Период взыскания по обязательству (режим «Ипотека»): даты с / по. */
  collectionPeriodFrom?: string;
  collectionPeriodTo?: string;
}

export interface ThirdParty {
  id: string;
  name: string;
  birthDate?: string;
  address?: string;
  inn?: string;
  /** ОГРН (режим «Ипотека»): третье лицо — юрлицо. */
  ogrn?: string;
  snils?: string;
}

export interface Heir {
  id: string;
  name: string;
  address?: string;
}

export interface Debtor {
  id: string;
  name: string;
  address?: string;
  inn?: string;
  ogrn?: string;
  ogrnip?: string;
  birthDate?: string;
  birthPlace?: string;
  snils?: string;
  /** Паспорт (режим «Ипотека», роль «Ответчик»): серия 4 цифры, номер 6 цифр. */
  passportSeries?: string;
  passportNumber?: string;
}

/** Категория дела верхнего уровня — выбирается пользователем в меню после анализа.
 *  'bankruptcy' — банкротство (полный функционал), 'collection' — взыскание
 *  (заглушка, в разработке), 'mortgage' — ипотека (форма без банкротных блоков,
 *  с созаёмщиком/поручителем/недвижимостью). Деривируется из documentType. */
export type DocumentCategory = 'bankruptcy' | 'collection' | 'mortgage';

/** Вид ипотеки: 'civil' — обычная (гражданская), 'military' — военная (ЦЖЗ,
 *  добавляет ставки/период и формульную сверку в финблок), 'ddu' — договор
 *  долевого участия (финблок как у обычной, доп. поля в «Предмете ипотеки»). */
export type MortgageKind = 'civil' | 'military' | 'ddu';

/** Лёгкая сторона дела с одинаковым набором полей: созаёмщик / поручитель
 *  (ипотека). ТЗ: ФИО, ИНН, адрес проживания. */
export interface PartyLite {
  id: string;
  name: string;
  inn?: string;
  address?: string;
}

/** Предмет ипотеки (режим «Ипотека»): реквизиты одного заложенного объекта.
 *  Поля повторяют плоские ключи извлечения (mortgageCollateral*), но в списке —
 *  чтобы поддержать несколько объектов в одном деле. */
export interface MortgageProperty {
  id: string;
  description?: string;
  cadastralNumber?: string;
  address?: string;
  value?: string;
  startingPrice?: string;
  appraisalReport?: string;
  /** Запись в ЕГРН (номер) и её дата. */
  egrnRecord?: string;
  egrnRecordDate?: string;
  /** Стратегия определения начальной продажной цены (НПЦ). */
  npcStrategy?: string;
  /** ДДУ (вид ипотеки 'ddu'): номер договора долевого участия и его дата. */
  dduContract?: string;
  dduDate?: string;
}

export type CollateralType = 'real_estate' | 'auto' | 'other';

export interface Collateral {
  id: string;
  collateralType: CollateralType;
  objectName: string;
  collateralValue: string;
  /** Для недвижимости */
  cadastralNumber?: string;
  address?: string;
  /** Для авто */
  vin?: string;
  brandModel?: string;
  /** Для иного */
  otherDescription?: string;
}

export interface RecommendedActs {
  entityType?: EntityType;
  collateralOption?: CollateralOption;
  recommendedActIds?: string[];
}

/** Претензия контракта поля к извлечённому значению (backend: field_contract). */
export interface FieldIssue {
  field: string;
  /** Человекочитаемая причина — показывается юристу как есть. */
  reason: string;
  /** Что стояло в поле до чистки. */
  value: string;
  /** true — поле вычищено (значение было чужим), false — оставлено с пометкой. */
  cleared: boolean;
}

/** Уровень доверия к полю (backend: field_contract.assess_quality). */
export interface FieldQuality {
  /** 'low' — есть претензия; 'high' — подтверждено независимо (справочник,
   *  контрольная сумма); 'medium' — извлечено паттерном, подтвердить нечем. */
  level: 'low' | 'medium' | 'high';
  reasons: string[];
  /** Откуда значение, если слой это знает: 'registry' — справочник,
   *  'document' — текст заявления. */
  source?: 'registry' | 'document';
  /** Для 'low': вычищено ли поле. */
  cleared?: boolean;
}

export interface ExtractedData {
  documentType: string;
  confidence: number;
  entityType?: 'individual' | 'legal';
  recommendedActs?: RecommendedActs;
  fields: {
    applicantName?: string;
    applicantAddress?: string;
    applicationDate?: string;
    courtName?: string;
    caseNumber?: string;
    // Ранее вынесенное решение другого суда (взыскание по делу до банкротства)
    priorCourtName?: string;
    priorCaseNumber?: string;
    priorAmount?: string;
    priorDecisionDate?: string;
    priorStateDuty?: string;
    debtAmount?: string;
    creditorName?: string;
    debtorName?: string;
    contractNumber?: string;
    contractDate?: string;
    obligationType?: string;
    principalDebt?: string;
    loanDebt?: string;
    interest?: string;
    penalties?: string;
    forfeit?: string;
    totalDebt?: string;
    principalDebt13?: string;
    interest14?: string;
    forfeit15?: string;
    stateDuty16?: string;
    creditAmount?: string;
    creditTermMonths?: string;
    creditInterestRate?: string;
    creditPenaltyRate?: string;
    ogrnip?: string;
    ipHasCollateral?: string;
    sourceDocumentType?: string;
    additionalInfo?: string;
    // Дополнительные поля для финансового управляющего
    managerName?: string;
    managerBirthDate?: string;
    managerAddress?: string;
    managerInn?: string;
    managerSnils?: string;
    // Поля для третьих лиц
    thirdPartyName?: string;
    thirdPartyBirthDate?: string;
    thirdPartyAddress?: string;
    thirdPartyInn?: string;
    thirdPartySnils?: string;
    [key: string]: string | undefined;
  };
  obligations?: Obligation[];
  collaterals?: Collateral[];
 
  financeBreakdown?: Record<string, string[]> | null;

  fieldIssues?: FieldIssue[];

  fieldQuality?: Record<string, FieldQuality>;

  applicationKind?: 'self_bankruptcy' | null;

  debtorStatusHint?: 'liquidation' | 'absent' | 'deceased' | null;

  documentTypeWarning?: {
    documentType: string;
    regexFamily: 'rtk' | 'initiation';
    semanticFamily: 'rtk' | 'initiation';
    message: string;
  } | null;
  /** Предупреждение: имя должника, найденное вторым способом (NER-харвест +
   *  ролевой якорь «Должник/Ответчик»), не совпало с извлечённым regex
   *  `debtorName`. Та же идея, что documentTypeWarning; `debtorName` не меняется
   *  (источник истины — regex), только сигнал перепроверить вручную. */
  debtorNameWarning?: {
    regexName: string;
    semanticName: string;
    message: string;
  } | null;
  /** Предупреждение: тип лица, который подразумевает regex-тип документа, не
   *  совпал с типом лица, определённым по реквизитам (ИНН/ОГРНИП формат, орг.-
   *  форма в имени должника). Та же идея, что и documentTypeWarning, но без
   *  эмбеддингов — оба сигнала уже вычислены пайплайном. */
  entityTypeWarning?: {
    documentType: string;
    expectedEntityType: 'individual' | 'legal' | 'ip';
    actualEntityType: string;
    message: string;
  } | null;
  /** Предупреждение: тип документа подразумевает наличие/отсутствие залога
   *  (по суффиксу *_collateral / mortgage_claim), но извлечённый список
   *  collaterals[] говорит обратное. Та же идея, что entityTypeWarning —
   *  сверка уже вычисленных сигналов, без новой модели. */
  collateralWarning?: {
    documentType: string;
    expectedCollateral: boolean;
    actualCollateral: boolean;
    message: string;
  } | null;
  thirdParties?: ThirdParty[];
  /** Наследники умершего должника — заполняется только для статуса «Умерший». */
  heirs?: Heir[];
  debtors?: Debtor[];
  /** Созаёмщики (режим «Ипотека»). Предзаполняются из со-должников, правятся вручную. */
  coborrowers?: PartyLite[];
  /** Поручители (режим «Ипотека»). Предзаполняются из третьих лиц, правятся вручную. */
  guarantors?: PartyLite[];
  /** Предметы ипотеки (режим «Ипотека»). Заложенных объектов может быть несколько —
   *  храним массивом, как третьих лиц. Первый засевается из извлечённых полей. */
  mortgageProperties?: MortgageProperty[];
  /** Вид ипотеки, авто-детект бэкендом ('military' — если ФГКУ «Росвоенипотека»/
   *  продукт «Военная ипотека»). Инициализирует переключатель, пользователь может сменить. */
  mortgageKind?: MortgageKind;
  rawText: string;
  metadata: {
    pageCount: number;
    wordCount: number;
    language: string;
  };
}

export interface TemplateType {
  id: string;
  name: string;
  description: string;
  category: string;
  fields: TemplateField[];
  previewImage?: string;
}

export interface TemplateField {
  name: string;
  label: string;
  type: 'text' | 'date' | 'number' | 'select' | 'textarea';
  required: boolean;
  defaultValue?: string;
  options?: string[];
  validation?: {
    minLength?: number;
    maxLength?: number;
    pattern?: string;
  };
}

export interface GeneratedDocument {
  id: string;
  templateType: string;
  fileName: string;
  filePath: string;
  generationDate: Date;
  status: 'generated' | 'error';
  errorMessage?: string;
}

export interface AnalysisResult {
  success: boolean;
  data?: ExtractedData;
  error?: string;
  suggestions?: string[];
}

export interface GenerationRequest {
  templateType: string;
  data: ExtractedData;
  outputFormat?: 'docx' | 'pdf';
}

export interface GenerationResult {
  success: boolean;
  documentId?: string;
  filePath?: string;
  error?: string;
}

// Специфичные типы для РТК
export interface RTKApplication {
  type: 'single_obligation' | 'multiple_obligations';
  applicant: {
    name: string;
    address: string;
    inn?: string;
    ogrn?: string;
  };
  court: {
    name: string;
    address: string;
  };
  case: {
    number: string;
    date: string;
  };
  obligations: RTKObligation[];
  totalAmount: number;
  currency: string;
}

export interface RTKObligation {
  id: string;
  type: string;
  amount: number;
  currency: string;
  contractNumber?: string;
  contractDate?: string;
  creditor: string;
  debtor: string;
  basis: string;
}

export interface RTKDecision {
  type: 'single_obligation' | 'multiple_obligations';
  court: {
    name: string;
    address: string;
  };
  case: {
    number: string;
    date: string;
  };
  decision: {
    date: string;
    number: string;
  };
  applicant: {
    name: string;
    address: string;
  };
  obligations: RTKObligation[];
  totalAmount: number;
  currency: string;
  inclusionDate: string;
  registryNumber: string;
}

// Типы для выбора судебных актов
export type EntityType = 'individual' | 'legal' | 'ip' | 'kfh';
export type CollateralOption = 'collateral' | 'collateral_auto' | 'no_collateral';

export type DebtorStatus = 'absent' | 'liquidation' | 'deceased';


export type ApplicationKind = 'rtk' | 'other' | 'self';

export interface SelectedAct {
  id: string;
  name: string;
  category: 'final' | 'acceptance' | 'intermediate';
  selected: boolean;

  rtkVariant?: 'realization' | 'restructuring' | 'competition' | 'observation' | 'registry';
  additionalFields?: {
    reason?: string;
    forParties?: string;
    courtRequests?: string;  // Запросы суда (для актов "Отложение", "Определение о принятии", "Принятие после Б/Д")
  };
}

export interface ActSelection {
  entityType: EntityType | null;
  collateralOption: CollateralOption | null;
  selectedActs: SelectedAct[];
}
