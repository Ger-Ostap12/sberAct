// Состав ипотечного пакета для предпросмотра.
//
// Генерация ипотеки не спрашивает каталог актов (тот — банкротный, лежит в
// selectedActsData): пакет всегда фиксированный — 4 акта одинаковых плюс
// решение-резолютивка, которая ветвится по виду ипотеки, солидарности и
// наличию представителей.
//
// Ветвление ДУБЛИРУЕТ бэкенд (templates_resolver_mixin._mortgage_decision_file).
// Здесь только имя для показа юристу; файл выбирает бэкенд. Если правишь
// таблицу там — поправь и здесь, иначе предпросмотр начнёт врать.
import { MortgageKind } from '../../../types';

export interface MortgagePackageAct {
  id: string;
  name: string;
}

const ALWAYS: MortgagePackageAct[] = [
  { id: 'mortgage_summons', name: 'Судебная повестка' },
  { id: 'mortgage_acceptance_short', name: 'Определение о принятии (короткое)' },
  { id: 'mortgage_acceptance_long', name: 'Определение о принятии (длинное)' },
  { id: 'mortgage_notice', name: 'Извещение' },
];

const KIND_LABEL: Record<string, string> = {
  civil: 'обычная ипотека',
  ddu: 'ДДУ',
};

export interface MortgagePackageInput {
  mortgageKind?: MortgageKind;
  fields?: Record<string, string | undefined>;
}

export const buildMortgagePackage = ({ mortgageKind, fields }: MortgagePackageInput): MortgagePackageAct[] => {
  const f = fields || {};
  const kind = mortgageKind || 'civil';

  if (kind === 'military') {
    return [...ALWAYS, { id: 'mortgage_decision', name: 'Решение-резолютивка (военная ипотека)' }];
  }

  const solidary = f.solidaryLiability === 'true';
  // «Хотя бы один» — то же правило, что на бэкенде.
  const representatives = Boolean(f.representativeName || f.respondentRepresentativeName);

  const parts = [
    KIND_LABEL[kind] || KIND_LABEL.civil,
    representatives ? 'представители' : 'должник',
    solidary ? 'солидарное' : 'не солидарное',
  ];
  return [...ALWAYS, { id: 'mortgage_decision', name: `Решение-резолютивка (${parts.join(', ')})` }];
};
