import { deriveCategory } from '../deriveCategory';

describe('deriveCategory', () => {
  it('ипотека для mortgage_claim', () => {
    expect(deriveCategory('mortgage_claim')).toBe('mortgage');
  });

  it('взыскание для всех *_collection*', () => {
    expect(deriveCategory('legal_collection')).toBe('collection');
    expect(deriveCategory('legal_collection_collateral')).toBe('collection');
    expect(deriveCategory('legal_collection_collateral_auto')).toBe('collection');
    expect(deriveCategory('ip_collection')).toBe('collection');
    expect(deriveCategory('ip_collection_collateral')).toBe('collection');
  });

  it('банкротство для банкротных типов', () => {
    expect(deriveCategory('rtk_application')).toBe('bankruptcy');
    expect(deriveCategory('initiation_physical')).toBe('bankruptcy');
    expect(deriveCategory('initiation_legal')).toBe('bankruptcy');
    expect(deriveCategory('competition_collateral')).toBe('bankruptcy');
    expect(deriveCategory('observation_collateral')).toBe('bankruptcy');
    expect(deriveCategory('ip_enforcement_realization')).toBe('bankruptcy');
    expect(deriveCategory('unknown')).toBe('bankruptcy');
  });

  it('банкротство по умолчанию для пустого/невалидного типа', () => {
    expect(deriveCategory('')).toBe('bankruptcy');
    expect(deriveCategory(undefined)).toBe('bankruptcy');
    expect(deriveCategory(null)).toBe('bankruptcy');
  });

  it('регистронезависим', () => {
    expect(deriveCategory('MORTGAGE_CLAIM')).toBe('mortgage');
    expect(deriveCategory('Legal_Collection')).toBe('collection');
  });
});
