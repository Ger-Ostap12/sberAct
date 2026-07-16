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
}

export interface ThirdParty {
  id: string;
  name: string;
  birthDate?: string;
  address?: string;
  inn?: string;
  snils?: string;
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
    // ФНС-финансы по очередям реестра: ключи вида `fnsQ{1|2|3}{Suffix}`, где Suffix ∈
    // Total/Arrears/Penalties/Forfeit/Ndfl/Insurance/LoanDebt/LoanDuty/Commission.
    // Валидны по индекс-сигнатуре ниже; заполняются backend только для кредитора-ФНС
    // и рендерятся 4-мя подблоками в FinancesSection (см. память fns-queue-finances).
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
  /** Разбивка полей финансов на слагаемые (ключ поля → суммы), когда итог сложился
   *  из нескольких обязательств. Для тултипа «откуда число» в FinancesSection. */
  financeBreakdown?: Record<string, string[]> | null;
  /** Вид заявления: 'self_bankruptcy' — на банкротство подаёт САМ должник
   *  (заявитель = должник, кредитора-заявителя нет). Фронт автопроставляет
   *  статус должника «Самобанкрот» и скрывает блок «Информация о кредиторе». */
  applicationKind?: 'self_bankruptcy' | null;
  /** Подсказка статуса должника из backend: 'liquidation' — в заявлении есть
   *  сведения о ликвидации ЮЛ; 'absent' — заявление по упрощённой процедуре
   *  отсутствующего должника (§ 2 гл. XI Закона о банкротстве). Фронт
   *  автопроставляет соответствующий статус. */
  debtorStatusHint?: 'liquidation' | 'absent' | null;
  thirdParties?: ThirdParty[];
  debtors?: Debtor[];
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
// Статус должника (банкротство): отсутствующий / ликвидируемый ЮЛ, умерший ФЛ.
// Взаимоисключающий, но ОПЦИОНАЛЬНЫЙ (может быть не задан) и НЕЗАВИСИМЫЙ от вида
// заявления — выбирается отдельным блоком «Статус лица». Влияет на рекомендацию
// финального СА. «Самобанкрот» сюда НЕ входит — он в ApplicationKind.
export type DebtorStatus = 'absent' | 'liquidation' | 'deceased';

// Вид заявления — независимый от статуса лица взаимоисключающий блок:
// ВКЛ в РТК / рядовое инициирование / самобанкрот. «rtk» скрывает поле СРО;
// «self» (заявление подал сам должник) скрывает блок кредитора.
export type ApplicationKind = 'rtk' | 'other' | 'self';

export interface SelectedAct {
  id: string;
  name: string;
  category: 'final' | 'acceptance' | 'intermediate';
  selected: boolean;
  /**
   * Дополнительный выбор варианта для актов "Определение ВКЛ в РТК"
   * (реализация / реструктуризация / конкурсное / наблюдение / зареестр).
   * Используется только на UI, но целиком передаётся в backend в selectedActsData.
   */
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
