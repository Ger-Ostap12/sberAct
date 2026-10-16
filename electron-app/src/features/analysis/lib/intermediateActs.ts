import { ApplicationKind } from '../../../types';

/** Акты упрощённого производства: при инициировании их не бывает. */
export const SIMPLIFIED_ACT_IDS = [
  'intermediate_extend_simplified',
  'intermediate_simplified_to_main',
];

/** Отмечены ли акты упрощёнки по умолчанию. Юрист может поставить их руками. */
export const simplifiedActsSelected = (applicationKind: ApplicationKind): boolean =>
  applicationKind === 'rtk';

/** Возврат без госпошлины. Есть у всех, включая самобанкрота. */
export const RETURN_NO_DUTY_ID = 'intermediate_return_no_duty';

/** Залоговый акт «Б/Д нет ГП» есть только у включения в РТК: в инициировании
 *  залоговость задана папкой, отдельного акта нет. */
export const COLLATERAL_NO_DUTY_ID = 'acceptance_no_motion_no_duty_collateral';

export const collateralNoDutyAvailable = (applicationKind: ApplicationKind): boolean =>
  applicationKind === 'rtk';

/** Отложение — два разных акта: обычное и с привлечением третьего лица. */
export const POSTPONEMENT_GENERAL_ID = 'intermediate_postponement';
export const POSTPONEMENT_THIRD_PARTY_ID = 'intermediate_postponement_third_party';
export const POSTPONEMENT_IDS = [POSTPONEMENT_GENERAL_ID, POSTPONEMENT_THIRD_PARTY_ID];

export type GroupState = 'all' | 'some' | 'none';

/** Состояние родительской галки группы: отмечены все, часть или ни одного. */
export const groupState = (selectedIds: string[], groupIds: string[] = POSTPONEMENT_IDS): GroupState => {
  const отмечено = groupIds.filter(id => selectedIds.includes(id)).length;
  if (отмечено === 0) return 'none';
  return отмечено === groupIds.length ? 'all' : 'some';
};

/** Клик по родителю: любое частичное состояние сначала доводим до «все». */
export const nextGroupSelection = (state: GroupState): boolean => state !== 'all';
