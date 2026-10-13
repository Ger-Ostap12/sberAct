import { ApplicationKind } from '../../../types';

/** Акты упрощённого производства: при инициировании их не бывает. */
export const SIMPLIFIED_ACT_IDS = [
  'intermediate_extend_simplified',
  'intermediate_simplified_to_main',
];

/** Отмечены ли акты упрощёнки по умолчанию. Юрист может поставить их руками. */
export const simplifiedActsSelected = (applicationKind: ApplicationKind): boolean =>
  applicationKind === 'rtk';

/** Возврат без госпошлины. У самобанкрота такого акта нет: пошлину платит сам должник. */
export const RETURN_NO_DUTY_ID = 'intermediate_return_no_duty';

export const returnNoDutyAvailable = (selfBankruptcy: boolean): boolean => !selfBankruptcy;
