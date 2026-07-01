import { buildSubmitData, SubmitDataInput } from '../buildSubmitData';
import { ExtractedData } from '../../../../types';

const baseAnalysis = (fields: Record<string, string> = {}): ExtractedData => ({
  documentType: 'rtk_application',
  confidence: 1,
  entityType: 'individual',
  fields: { ...fields },
  obligations: [],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

const run = (over: Partial<SubmitDataInput>): ExtractedData =>
  buildSubmitData({
    analysisResult: baseAnalysis(),
    editedFields: {},
    entityType: null,
    collateralOption: null,
    debtorStatus: null,
    selectedActs: [],
    ...over,
  });

describe('buildSubmitData — приоритет editedFields', () => {
  it('editedFields перекрывают analysisResult.fields', () => {
    const r = buildSubmitData({
      analysisResult: baseAnalysis({ courtName: 'Старый суд', caseNumber: 'A-1' }),
      editedFields: { courtName: 'Новый суд' },
      entityType: null,
      collateralOption: null,
      debtorStatus: null,
      selectedActs: [],
    });
    expect(r.fields.courtName).toBe('Новый суд');
    expect(r.fields.caseNumber).toBe('A-1');
  });
});

describe('buildSubmitData — finalEntityType', () => {
  it('ip и kfh → individual', () => {
    expect(run({ entityType: 'ip' }).entityType).toBe('individual');
    expect(run({ entityType: 'kfh' }).entityType).toBe('individual');
  });
  it('legal → legal, individual → individual', () => {
    expect(run({ entityType: 'legal' }).entityType).toBe('legal');
    expect(run({ entityType: 'individual' }).entityType).toBe('individual');
  });
  it('null → берётся из analysisResult.entityType', () => {
    const r = buildSubmitData({
      analysisResult: { ...baseAnalysis(), entityType: 'legal' },
      editedFields: {},
      entityType: null,
      collateralOption: null,
      debtorStatus: null,
      selectedActs: [],
    });
    expect(r.entityType).toBe('legal');
  });
});

describe('buildSubmitData — ФИО судьи', () => {
  it('приводит judge к «Фамилия И.О.»', () => {
    const r = run({ editedFields: { judge: 'Иванов Иван Иванович' } });
    expect(r.fields.judge).toBe('Иванов И.И.');
  });
});

describe('buildSubmitData — синхронизация сумм', () => {
  it('loanDebt → principalDebt(+13), если principalDebt пуст', () => {
    const r = run({ editedFields: { loanDebt: '100' } });
    expect(r.fields.principalDebt).toBe('100');
    expect(r.fields.principalDebt13).toBe('100');
  });
  it('principalDebt → loanDebt, если loanDebt пуст', () => {
    const r = run({ editedFields: { principalDebt: '200' } });
    expect(r.fields.loanDebt).toBe('200');
  });
  it('interest ↔ interest14', () => {
    expect(run({ editedFields: { interest: '5' } }).fields.interest14).toBe('5');
    expect(run({ editedFields: { interest14: '6' } }).fields.interest).toBe('6');
  });
  it('forfeit ↔ forfeit15', () => {
    expect(run({ editedFields: { forfeit: '7' } }).fields.forfeit15).toBe('7');
    expect(run({ editedFields: { forfeit15: '8' } }).fields.forfeit).toBe('8');
  });
  it('penalties → forfeit15 и forfeit, если forfeit15 пуст', () => {
    const r = run({ editedFields: { penalties: '9' } });
    expect(r.fields.forfeit15).toBe('9');
    expect(r.fields.forfeit).toBe('9');
  });
  it('stateDuty ↔ stateDuty16', () => {
    expect(run({ editedFields: { stateDuty: '3' } }).fields.stateDuty16).toBe('3');
    expect(run({ editedFields: { stateDuty16: '4' } }).fields.stateDuty).toBe('4');
  });
  it('не перезаписывает уже заполненные парные поля', () => {
    const r = run({ editedFields: { loanDebt: '100', principalDebt: '999' } });
    expect(r.fields.principalDebt).toBe('999');
    expect(r.fields.loanDebt).toBe('100');
  });
});

describe('buildSubmitData — выбранные акты', () => {
  it('сериализует только выбранные акты', () => {
    const r = run({
      selectedActs: [
        { id: 'a1', name: 'Акт 1', category: 'final', selected: true },
        { id: 'a2', name: 'Акт 2', category: 'final', selected: false },
      ],
    });
    expect(r.fields.selectedActsIds).toBe('a1');
    const data = JSON.parse(r.fields.selectedActsData as string);
    expect(data).toHaveLength(1);
    expect(data[0].id).toBe('a1');
  });

  it('передаёт выбор пользователя (entityType/collateralOption/debtorStatus)', () => {
    const r = run({ entityType: 'legal', collateralOption: 'no_collateral', debtorStatus: 'absent' });
    expect(r.fields.selectedEntityType).toBe('legal');
    expect(r.fields.selectedCollateralOption).toBe('no_collateral');
    expect(r.fields.selectedDebtorStatus).toBe('absent');
  });
});
