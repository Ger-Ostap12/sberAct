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

export interface ExtractedData {
  documentType: string;
  confidence: number;
  entityType?: 'individual' | 'legal';
  fields: {
    applicantName?: string;
    applicantAddress?: string;
    applicationDate?: string;
    courtName?: string;
    caseNumber?: string;
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
