import {
  ExtractedData,
  EntityType,
  CollateralOption,
  DebtorStatus,
  ApplicationKind,
  SelectedAct,
  DocumentCategory,
} from '../../../types';
import { formatJudgeName } from '../../../shared/lib/judges';

export interface SubmitDataInput {
  analysisResult: ExtractedData;
  editedFields: Record<string, string>;
  entityType: EntityType | null;
  collateralOption: CollateralOption | null;
  debtorStatus: DebtorStatus | null;
  applicationKind: ApplicationKind;
  selectedActs: SelectedAct[];
  /** Чекбокс «Короткий текст»: доп. генерация резолютивки основной процедуры. */
  shortText?: boolean;
  /** Категория дела: 'bankruptcy' (по умолчанию) или 'mortgage'. */
  documentCategory?: DocumentCategory;
}

/**
 * Готовит итоговые данные для передачи на генерацию (бывшая логика handleContinue).
 * Перенесено 1:1: приоритет editedFields, ФИО судьи → «Фамилия И.О.», синхронизация
 * пар полей сумм (loanDebt↔principalDebt, interest↔interest14, forfeit↔forfeit15,
 * penalties→forfeit, stateDuty↔stateDuty16). Чистая функция — тестируется напрямую.
 */
export const buildSubmitData = (input: SubmitDataInput): ExtractedData => {
  const { analysisResult, editedFields, entityType, collateralOption, debtorStatus, applicationKind, selectedActs, shortText, documentCategory } =
    input;

  // Финальный тип лица: выбранный пользователем (с приведением) или автоопределённый
  const finalEntityType: 'individual' | 'legal' = entityType
    ? entityType === 'ip' || entityType === 'kfh'
      ? 'individual'
      : entityType === 'legal'
        ? 'legal'
        : 'individual'
    : analysisResult.entityType || 'individual';

  const selected = selectedActs.filter((a) => a.selected);

  const updatedData: ExtractedData = {
    ...analysisResult,
    entityType: finalEntityType,
    fields: {
      ...analysisResult.fields,
      ...editedFields,
      // Оригинальный выбор пользователя — в поля для передачи в backend
      selectedEntityType: entityType || undefined,
      selectedCollateralOption: collateralOption || undefined,
      selectedDebtorStatus: debtorStatus || undefined,
      selectedApplicationKind: applicationKind || undefined,
      selectedActsIds: selected.map((a) => a.id).join(',') || undefined,
      selectedActsData: JSON.stringify(selected) || undefined,
      selectedShortText: shortText ? 'true' : undefined,
      documentCategory: documentCategory || undefined,
    },
    collaterals: analysisResult.collaterals || [],
    thirdParties: analysisResult.thirdParties || [],
    debtors: analysisResult.debtors || [],
    heirs: analysisResult.heirs || [],
    coborrowers: analysisResult.coborrowers || [],
    guarantors: analysisResult.guarantors || [],
  };

  // ФИО судьи → «Фамилия И.О.»
  if (updatedData.fields && updatedData.fields.judge) {
    updatedData.fields.judge = formatJudgeName(updatedData.fields.judge);
  }

  // Синхронизация полей сумм (перенесено 1:1)
  const f = updatedData.fields;
  if (f) {
    if (f.loanDebt && !f.principalDebt) {
      f.principalDebt = f.loanDebt;
      f.principalDebt13 = f.loanDebt;
    } else if (f.principalDebt && !f.loanDebt) {
      f.loanDebt = f.principalDebt;
    }

    if (f.interest && !f.interest14) {
      f.interest14 = f.interest;
    }
    if (f.interest14 && !f.interest) {
      f.interest = f.interest14;
    }

    if (f.forfeit && !f.forfeit15) {
      f.forfeit15 = f.forfeit;
    }
    if (f.forfeit15 && !f.forfeit) {
      f.forfeit = f.forfeit15;
    }

    if (f.penalties && !f.forfeit15) {
      f.forfeit15 = f.penalties;
      f.forfeit = f.penalties;
    }

    if (f.stateDuty && !f.stateDuty16) {
      f.stateDuty16 = f.stateDuty;
    }
    if (f.stateDuty16 && !f.stateDuty) {
      f.stateDuty = f.stateDuty16;
    }
  }

  return updatedData;
};
