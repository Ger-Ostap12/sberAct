import { Collateral } from '../../../../types';
import {
  anyKind,
  hasCardOfKind,
  isCardFilled,
  kindsFromCollaterals,
  kindsWithoutCards,
  NO_COLLATERAL,
} from '../collateralSync';

// Галки блока «Выбор залога» производны от карточек: карточки — источник истины.

const card = (over: Partial<Collateral>): Collateral => ({
  id: 'c1',
  collateralType: 'real_estate',
  objectName: '',
  collateralValue: '',
  cadastralNumber: '',
  address: '',
  vin: '',
  brandModel: '',
  otherDescription: '',
  ...over,
});

describe('kindsFromCollaterals', () => {
  it('без карточек — «Без залога»', () => {
    expect(kindsFromCollaterals([])).toEqual(NO_COLLATERAL);
  });

  it('каждый тип карточки поднимает свою галку', () => {
    expect(kindsFromCollaterals([card({ collateralType: 'auto' })]))
      .toEqual({ realEstate: false, auto: true, other: false });
    expect(kindsFromCollaterals([card({ collateralType: 'other' })]))
      .toEqual({ realEstate: false, auto: false, other: true });
  });

  it('несколько карточек поднимают несколько галок', () => {
    const kinds = kindsFromCollaterals([
      card({ id: 'c1', collateralType: 'real_estate' }),
      card({ id: 'c2', collateralType: 'auto' }),
    ]);
    expect(kinds).toEqual({ realEstate: true, auto: true, other: false });
  });

  it('пустая карточка тоже поднимает галку: тип уже выбран', () => {
    expect(kindsFromCollaterals([card({})]).realEstate).toBe(true);
  });
});

describe('isCardFilled', () => {
  it('карточка без описания не заполнена', () => {
    expect(isCardFilled(card({}))).toBe(false);
  });

  it('пробелы не считаются описанием', () => {
    expect(isCardFilled(card({ objectName: '   ' }))).toBe(false);
  });

  it('любое непустое поле делает карточку заполненной', () => {
    expect(isCardFilled(card({ objectName: 'Квартира' }))).toBe(true);
    expect(isCardFilled(card({ vin: 'XTA21' }))).toBe(true);
    expect(isCardFilled(card({ otherDescription: 'оборудование' }))).toBe(true);
    expect(isCardFilled(card({ collateralValue: '1000' }))).toBe(true);
  });
});

describe('kindsWithoutCards', () => {
  it('галка без единой карточки — в списке', () => {
    expect(kindsWithoutCards({ realEstate: true, auto: false, other: false }, []))
      .toEqual(['Залог недвижимость']);
  });

  it('галка с пустой карточкой — тоже в списке: заполнять всё равно надо', () => {
    expect(kindsWithoutCards({ realEstate: true, auto: false, other: false }, [card({})]))
      .toEqual(['Залог недвижимость']);
  });

  it('галка с заполненной карточкой — не в списке', () => {
    const список = kindsWithoutCards(
      { realEstate: true, auto: false, other: false },
      [card({ objectName: 'Квартира' })]);
    expect(список).toEqual([]);
  });

  it('карточка чужого вида не подтверждает галку', () => {
    const список = kindsWithoutCards(
      { realEstate: false, auto: true, other: false },
      [card({ collateralType: 'real_estate', objectName: 'Квартира' })]);
    expect(список).toEqual(['Залог ТС']);
  });

  it('перечисляет все неподтверждённые виды разом', () => {
    expect(kindsWithoutCards({ realEstate: true, auto: true, other: true }, []))
      .toEqual(['Залог недвижимость', 'Залог ТС', 'Залог иное']);
  });

  it('«Без залога» ничего не требует', () => {
    expect(kindsWithoutCards(NO_COLLATERAL, [])).toEqual([]);
  });
});

describe('hasCardOfKind', () => {
  it('видит карточку своего вида и не видит чужого', () => {
    const карточки = [card({ collateralType: 'auto' })];
    expect(hasCardOfKind('auto', карточки)).toBe(true);
    expect(hasCardOfKind('realEstate', карточки)).toBe(false);
  });

  it('пустая карточка считается: юрист уже выбрал вид', () => {
    expect(hasCardOfKind('realEstate', [card({})])).toBe(true);
  });
});

describe('anyKind', () => {
  it('отличает «есть залог» от «Без залога»', () => {
    expect(anyKind(NO_COLLATERAL)).toBe(false);
    expect(anyKind({ realEstate: false, auto: true, other: false })).toBe(true);
  });
});
