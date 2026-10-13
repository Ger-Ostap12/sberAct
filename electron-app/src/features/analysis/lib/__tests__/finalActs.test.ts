import {
  defaultRtkVariant,
  finalActsContextKey,
  initiationFinalActs,
  rtkVariantsForEntity,
} from '../finalActs';

describe('initiationFinalActs', () => {
  it('физлицо и ИП — реализация и реструктуризация', () => {
    expect(initiationFinalActs('individual', null)).toEqual(['final_realization', 'final_restructuring']);
    expect(initiationFinalActs('ip', null)).toEqual(['final_realization', 'final_restructuring']);
  });

  it('юрлицо и КФХ — конкурсное и наблюдение', () => {
    expect(initiationFinalActs('legal', null)).toEqual(['final_competition', 'final_observation']);
    expect(initiationFinalActs('kfh', null)).toEqual(['final_competition', 'final_observation']);
  });

  it('у ликвидируемого и отсутствующего ЮЛ наблюдения не бывает', () => {
    expect(initiationFinalActs('legal', 'liquidation')).toEqual(['final_competition']);
    expect(initiationFinalActs('legal', 'absent')).toEqual(['final_competition']);
  });

  it('у умершего должника процедура одна — реализация', () => {
    expect(initiationFinalActs('individual', 'deceased')).toEqual(['final_realization']);
  });

  it('статус старше типа лица: умерший не получает реструктуризацию', () => {
    expect(initiationFinalActs('ip', 'deceased')).toEqual(['final_realization']);
  });

  it('без типа лица не отмечаем ничего', () => {
    expect(initiationFinalActs(null, null)).toEqual([]);
  });
});

describe('rtkVariantsForEntity', () => {
  it('физлицу и ИП — реализация, реструктуризация, за реестр', () => {
    expect(rtkVariantsForEntity('individual')).toEqual(['realization', 'restructuring', 'registry']);
    expect(rtkVariantsForEntity('ip')).toEqual(['realization', 'restructuring', 'registry']);
  });

  it('юрлицу и КФХ — конкурсное, наблюдение, за реестр', () => {
    expect(rtkVariantsForEntity('legal')).toEqual(['competition', 'observation', 'registry']);
    expect(rtkVariantsForEntity('kfh')).toEqual(['competition', 'observation', 'registry']);
  });

  it('«За реестр» есть в обоих наборах — его юрист выбирает сам', () => {
    expect(rtkVariantsForEntity('individual')).toContain('registry');
    expect(rtkVariantsForEntity('legal')).toContain('registry');
  });
});

describe('defaultRtkVariant', () => {
  it('подставляет процедуру, введённую судом', () => {
    expect(defaultRtkVariant('realization', 'individual')).toBe('realization');
    expect(defaultRtkVariant('restructuring', 'individual')).toBe('restructuring');
    expect(defaultRtkVariant('competition', 'legal')).toBe('competition');
    expect(defaultRtkVariant('observation', 'legal')).toBe('observation');
  });

  it('процедуру, чужую типу лица, не подставляет', () => {
    // Документ сказал «конкурсное», а юрист выбрал физлицо — молчим, пусть решит сам.
    expect(defaultRtkVariant('competition', 'individual')).toBeNull();
    expect(defaultRtkVariant('realization', 'legal')).toBeNull();
  });

  it('без процедуры из документа не подставляет ничего', () => {
    expect(defaultRtkVariant(undefined, 'individual')).toBeNull();
    expect(defaultRtkVariant(null, 'legal')).toBeNull();
  });
});

describe('finalActsContextKey', () => {
  it('ключ меняется на смену любой из трёх кнопок', () => {
    const базовый = finalActsContextKey('initiation', 'legal', null);
    expect(finalActsContextKey('rtk', 'legal', null)).not.toBe(базовый);
    expect(finalActsContextKey('initiation', 'individual', null)).not.toBe(базовый);
    expect(finalActsContextKey('initiation', 'legal', 'liquidation')).not.toBe(базовый);
  });

  it('тот же контекст даёт тот же ключ', () => {
    expect(finalActsContextKey('rtk', 'ip', 'deceased')).toBe(finalActsContextKey('rtk', 'ip', 'deceased'));
  });
});
