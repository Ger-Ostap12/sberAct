import { ApplicationKind, DebtorStatus, EntityType } from '../../../types';

export type RtkVariant = 'realization' | 'restructuring' | 'competition' | 'observation' | 'registry';

/** Процедура, введённая судом (поле бэкенда introducedProcedure). */
export type IntroducedProcedure = 'realization' | 'restructuring' | 'competition' | 'observation';

export const RTK_VARIANT_LABEL: Record<RtkVariant, string> = {
  realization: 'Определение включение в РТК реализация',
  restructuring: 'Определение включение в РТК реструктуризация',
  competition: 'Определение включение в РТК конкурсное',
  observation: 'Определение включение в РТК наблюдение',
  registry: 'Определение ВКЛ в РТК «За реестр»',
};

const ЮРИДИЧЕСКОЕ = (entityType: EntityType | null): boolean =>
  entityType === 'legal' || entityType === 'kfh';

/**
 * Финальные акты инициирования, отмечаемые по типу лица и статусу.
 * У ликвидируемого и отсутствующего ЮЛ наблюдение не вводится — только конкурсное;
 * у умершего должника процедура одна — реализация.
 */
export const initiationFinalActs = (
  entityType: EntityType | null,
  debtorStatus: DebtorStatus | null,
): string[] => {
  if (debtorStatus === 'deceased') return ['final_realization'];
  if (debtorStatus === 'liquidation' || debtorStatus === 'absent') return ['final_competition'];
  if (!entityType) return [];
  return ЮРИДИЧЕСКОЕ(entityType)
    ? ['final_competition', 'final_observation']
    : ['final_realization', 'final_restructuring'];
};

/** Виды акта включения в РТК, доступные этому типу лица. «За реестр» доступен всем. */
export const rtkVariantsForEntity = (entityType: EntityType | null): RtkVariant[] =>
  ЮРИДИЧЕСКОЕ(entityType)
    ? ['competition', 'observation', 'registry']
    : ['realization', 'restructuring', 'registry'];

/** Вид акта по процедуре, введённой судом. Чужая типу лица процедура не подставляется. */
export const defaultRtkVariant = (
  introduced: IntroducedProcedure | undefined | null,
  entityType: EntityType | null,
): RtkVariant | null => {
  if (!introduced) return null;
  const доступные = rtkVariantsForEntity(entityType);
  return (доступные as string[]).includes(introduced) ? (introduced as RtkVariant) : null;
};

/** Ключ контекста: пересчёт финальных актов идёт на его смену, а не на каждый рендер. */
export const finalActsContextKey = (
  applicationKind: ApplicationKind,
  entityType: EntityType | null,
  debtorStatus: DebtorStatus | null,
): string => `${applicationKind}|${entityType || ''}|${debtorStatus || ''}`;
