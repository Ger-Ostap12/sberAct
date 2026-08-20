/**
 * Настройки приложения. Пока их ровно одна, но место для них нужно уже сейчас:
 * LLM-проверка нагружает процессор на минуты, и у юриста должна быть
 * возможность её отключить.
 *
 * localStorage в приложении до этого не использовался нигде. Заворачиваем
 * доступ, потому что падать из-за настройки нельзя: в Electron с нестандартным
 * профилем или при отключённом хранилище чтение бросает исключение, и без
 * try/catch это уронило бы весь экран анализа ради одного флага.
 */

const LLM_HINTS_KEY = 'sberact.llmHints.enabled';

/** По умолчанию включено: слой полезен, а выключатель — на случай слабой машины. */
export function isLlmHintsEnabled(): boolean {
  try {
    const raw = window.localStorage.getItem(LLM_HINTS_KEY);
    return raw === null ? true : raw === '1';
  } catch {
    return true;
  }
}

export function setLlmHintsEnabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(LLM_HINTS_KEY, enabled ? '1' : '0');
  } catch {
    /* настройка не сохранится — это не повод ломать работу */
  }
}
