import { buildMortgagePackage } from '../lib/mortgagePackage';

describe('buildMortgagePackage', () => {
  it('всегда 5 актов, четыре из них постоянные', () => {
    const acts = buildMortgagePackage({ mortgageKind: 'civil', fields: {} });
    expect(acts).toHaveLength(5);
    expect(acts.slice(0, 4).map((a) => a.id)).toEqual([
      'mortgage_summons',
      'mortgage_acceptance_short',
      'mortgage_acceptance_long',
      'mortgage_notice',
    ]);
    expect(acts[4].id).toBe('mortgage_decision');
  });

  it('военная ипотека — без ветвлений', () => {
    const acts = buildMortgagePackage({
      mortgageKind: 'military',
      fields: { solidaryLiability: 'true', representativeName: 'Иванов И.И.' },
    });
    expect(acts[4].name).toContain('военная');
  });

  it.each([
    [{}, 'обычная ипотека, должник, не солидарное'],
    [{ solidaryLiability: 'true' }, 'обычная ипотека, должник, солидарное'],
    [{ representativeName: 'Иванов И.И.' }, 'обычная ипотека, представители, не солидарное'],
    [
      { representativeName: 'Иванов И.И.', solidaryLiability: 'true' },
      'обычная ипотека, представители, солидарное',
    ],
  ])('обычная ипотека: %o → %s', (fields, expected) => {
    const acts = buildMortgagePackage({ mortgageKind: 'civil', fields });
    expect(acts[4].name).toBe(`Решение-резолютивка (${expected})`);
  });

  it('ДДУ ветвится так же', () => {
    const acts = buildMortgagePackage({ mortgageKind: 'ddu', fields: { solidaryLiability: 'true' } });
    expect(acts[4].name).toBe('Решение-резолютивка (ДДУ, должник, солидарное)');
  });

  it('представитель ответчика тоже считается («хотя бы один»)', () => {
    const acts = buildMortgagePackage({
      mortgageKind: 'civil',
      fields: { respondentRepresentativeName: 'Петров П.П.' },
    });
    expect(acts[4].name).toContain('представители');
  });

  it('снятая галочка солидарности — пустая строка, а не "false"', () => {
    const acts = buildMortgagePackage({ mortgageKind: 'civil', fields: { solidaryLiability: '' } });
    expect(acts[4].name).toContain('не солидарное');
  });
});
