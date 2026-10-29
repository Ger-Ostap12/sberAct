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

// Настройки конвертера держим у себя, а не в его файле настроек: сайдкар живёт
// только на шаге конвертации, и в диалоге настроек его обычно нет. Выбор
// передаётся полем `profile` при запуске конвертации — конвертер принимает его
// как разовое переопределение.
const CONVERTER_PROFILE_KEY = 'sberact.converter.profile';
const CONVERTER_LLM_KEY = 'sberact.converter.llmDefault';

export type ConverterProfileChoice = 'auto' | 'lean' | 'balanced' | 'full';
/** 'auto' — как решит профиль конвертера по этой машине. */
export type ConverterLlmChoice = 'auto' | 'on' | 'off';

const PROFILE_CHOICES: ConverterProfileChoice[] = ['auto', 'lean', 'balanced', 'full'];
const LLM_CHOICES: ConverterLlmChoice[] = ['auto', 'on', 'off'];

function read<T extends string>(key: string, allowed: T[], fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key) as T | null;
    return raw && allowed.includes(raw) ? raw : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* настройка не сохранится — это не повод ломать работу */
  }
}

export function getConverterProfile(): ConverterProfileChoice {
  return read(CONVERTER_PROFILE_KEY, PROFILE_CHOICES, 'auto');
}

export function setConverterProfile(value: ConverterProfileChoice): void {
  write(CONVERTER_PROFILE_KEY, value);
}

export function getConverterLlm(): ConverterLlmChoice {
  return read(CONVERTER_LLM_KEY, LLM_CHOICES, 'auto');
}

export function setConverterLlm(value: ConverterLlmChoice): void {
  write(CONVERTER_LLM_KEY, value);
}
