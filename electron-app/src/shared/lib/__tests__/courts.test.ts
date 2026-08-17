import { findCourtDefaults } from '../courts';

describe('findCourtDefaults', () => {
  it('Ворошиловский суд → email и сайт по умолчанию', () => {
    const d = findCourtDefaults('Ворошиловский районный суд г. Ростова-на-Дону');
    expect(d).not.toBeNull();
    expect(d!.email).toBe('voroshilovsky.ros@sudrf.ru');
    expect(d!.site).toBe('https://voroshilovsky--ros.sudrf.ru/');
    expect(d!.genitive).toBe('Ворошиловского районного суда г. Ростова-на-Дону');
  });

  it('распознаёт по алиасу-подстроке (регистр/ё игнорируются)', () => {
    expect(findCourtDefaults('ВОРОШИЛОВСКИЙ РАЙОННЫЙ СУД')).not.toBeNull();
    expect(findCourtDefaults('в Ворошиловский районный суд города Ростова')).not.toBeNull();
  });

  it('прочие суды → null', () => {
    expect(findCourtDefaults('Арбитражный суд Ростовской области')).toBeNull();
    expect(findCourtDefaults('Кировский районный суд')).toBeNull();
    expect(findCourtDefaults('')).toBeNull();
    expect(findCourtDefaults(undefined)).toBeNull();
  });
});
