import {
  POSTPONEMENT_GENERAL_ID,
  POSTPONEMENT_IDS,
  POSTPONEMENT_THIRD_PARTY_ID,
  groupState,
  nextGroupSelection,
} from '../intermediateActs';

// Родительская галка «Отложение» над двумя актами подсписка.

describe('состояние группы отложений', () => {
  it('оба отмечены — «all»', () => {
    expect(groupState([POSTPONEMENT_GENERAL_ID, POSTPONEMENT_THIRD_PARTY_ID])).toBe('all');
  });

  it('один отмечен — «some»', () => {
    expect(groupState([POSTPONEMENT_GENERAL_ID])).toBe('some');
    expect(groupState([POSTPONEMENT_THIRD_PARTY_ID])).toBe('some');
  });

  it('ни одного — «none»', () => {
    expect(groupState([])).toBe('none');
    expect(groupState(['intermediate_return_general'])).toBe('none');
  });

  it('посторонние акты на состояние не влияют', () => {
    const ids = [...POSTPONEMENT_IDS, 'intermediate_return_general', 'final_realization'];
    expect(groupState(ids)).toBe('all');
  });
});

describe('клик по родительской галке', () => {
  it('из «none» включает оба', () => {
    expect(nextGroupSelection('none')).toBe(true);
  });

  it('из «some» доводит до «all», а не гасит', () => {
    expect(nextGroupSelection('some')).toBe(true);
  });

  it('из «all» гасит оба', () => {
    expect(nextGroupSelection('all')).toBe(false);
  });
});

describe('состав группы', () => {
  it('в группе ровно два акта', () => {
    expect(POSTPONEMENT_IDS).toHaveLength(2);
    expect(POSTPONEMENT_IDS).toContain(POSTPONEMENT_GENERAL_ID);
    expect(POSTPONEMENT_IDS).toContain(POSTPONEMENT_THIRD_PARTY_ID);
  });

  it('общий акт сохранил прежний id — бэкенд его уже знает', () => {
    expect(POSTPONEMENT_GENERAL_ID).toBe('intermediate_postponement');
  });
});
