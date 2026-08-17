import { DocumentCategory } from '../../../types';

/**
 * Деривирует категорию дела из documentType классификатора backend.
 * Категории верхнего уровня в backend нет — она закодирована в префиксах
 * documentType: `*_collection*` = взыскание, `mortgage_claim` = ипотека,
 * всё остальное (rtk/initiation/competition/observation/…) = банкротство.
 * Используется как РЕКОМЕНДАЦИЯ в меню; пользователь может выбрать иное.
 */
export const deriveCategory = (documentType?: string | null): DocumentCategory => {
  const type = (documentType || '').toLowerCase();
  if (!type) return 'bankruptcy';
  if (type === 'mortgage_claim') return 'mortgage';
  if (type.includes('collection')) return 'collection';
  return 'bankruptcy';
};
