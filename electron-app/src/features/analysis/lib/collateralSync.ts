import { Collateral, CollateralType } from '../../../types';

/** Галки блока «Выбор залога». Производны от карточек залога. */
export interface CollateralKinds {
  realEstate: boolean;
  auto: boolean;
  other: boolean;
}

export const KIND_BY_TYPE: Record<CollateralType, keyof CollateralKinds> = {
  real_estate: 'realEstate',
  auto: 'auto',
  other: 'other',
};

export const KIND_LABEL: Record<keyof CollateralKinds, string> = {
  realEstate: 'Залог недвижимость',
  auto: 'Залог ТС',
  other: 'Залог иное',
};

export const NO_COLLATERAL: CollateralKinds = { realEstate: false, auto: false, other: false };

/** Карточка считается заполненной, если названо хоть что-то, кроме типа. */
export const isCardFilled = (card: Collateral): boolean =>
  [card.objectName, card.collateralValue, card.cadastralNumber, card.address,
    card.vin, card.brandModel, card.otherDescription]
    .some(v => String(v || '').trim() !== '');

/** Виды, подтверждённые карточками: карточка есть — галка стоит. */
export const kindsFromCollaterals = (collaterals: Collateral[]): CollateralKinds => {
  const kinds: CollateralKinds = { ...NO_COLLATERAL };
  for (const card of collaterals || []) {
    const kind = KIND_BY_TYPE[(card.collateralType || 'real_estate') as CollateralType];
    if (kind) kinds[kind] = true;
  }
  return kinds;
};

/** Есть ли под этим видом хоть одна карточка (пустая тоже считается). */
export const hasCardOfKind = (kind: keyof CollateralKinds, collaterals: Collateral[]): boolean =>
  (collaterals || []).some(c => KIND_BY_TYPE[(c.collateralType || 'real_estate') as CollateralType] === kind);

/** Отмеченные виды, под которыми нет ни одной ЗАПОЛНЕННОЙ карточки. */
export const kindsWithoutCards = (kinds: CollateralKinds, collaterals: Collateral[]): string[] => {
  const заполненные = (collaterals || []).filter(isCardFilled);
  return (Object.keys(KIND_LABEL) as (keyof CollateralKinds)[])
    .filter(kind => kinds[kind] && !hasCardOfKind(kind, заполненные))
    .map(kind => KIND_LABEL[kind]);
};

export const anyKind = (kinds: CollateralKinds): boolean =>
  kinds.realEstate || kinds.auto || kinds.other;
