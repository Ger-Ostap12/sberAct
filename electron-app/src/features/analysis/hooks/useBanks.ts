import { useState, useEffect } from 'react';
import { Bank } from '../../../shared/constants/banks';
import { getBanks } from '../../../services/electronApi';

/**
 * Загружает единый реестр банков с бэкенда (GET /banks) один раз при монтировании.
 * Пока грузится или если бэкенд недоступен — возвращает пустой массив (дропдаун
 * покажет только ручной ввод; document-first — ничего не ломается).
 */
export const useBanks = (): Bank[] => {
  const [banks, setBanks] = useState<Bank[]>([]);

  useEffect(() => {
    let active = true;
    getBanks()
      .then((list) => {
        if (active) setBanks(Array.isArray(list) ? list : []);
      })
      .catch((e) => {
        console.error('Не удалось загрузить реестр банков:', e);
      });
    return () => {
      active = false;
    };
  }, []);

  return banks;
};
