// Разбор отказов бэкенда и конвертера в текст для пользователя.
//
// Разбирать приходится на стороне интерфейса, потому что сетевых слоёв два:
// webApi.ts (браузер) отдаёт ошибку с разобранными полями, а preload.js
// (Electron, то есть прод) кладёт тело ответа прямо в текст: «HTTP 400: {…}».

/** Чем кончился запрос. Нужен интерфейсу: 404 задачи опрашивать больше незачем. */
export type FailureKind = 'offline' | 'server' | 'notfound' | 'gone' | 'http' | 'unknown';

export interface BackendFailure {
  /** Что показать пользователю. */
  message: string;
  /** Что с этим делать — отдельной строкой под сообщением. */
  hint?: string;
  /** Машинный код конвертера (NOT_A_PDF, CANCELLED и прочие). */
  code?: string;
  status?: number;
  kind: FailureKind;
  /** Техническая подробность для лога, пользователю не показывается. */
  raw?: string;
}

/** Сервера нет вовсе: «Failed to fetch» — сообщение браузера, по нему юристу нечего делать. */
export const OFFLINE_TEXT =
  'Сервер конвертера не отвечает. Проверьте, что программа запущена, и попробуйте снова.';

const OFFLINE_PATTERNS = [
  /failed to fetch/i,
  /all backend hosts failed/i,
  /backend недоступен/i,
  /networkerror/i,
  /err_connection/i,
  /load failed/i,
];

/** Тело ответа: «HTTP 404: {"detail": …}» — формат обоих наших слоёв. */
const HTTP_MESSAGE = /^HTTP (\d{3}):\s*([\s\S]*)$/;

function kindOf(status: number): FailureKind {
  if (status === 404) return 'notfound';
  if (status === 410) return 'gone';
  if (status >= 500) return 'server';
  return 'http';
}

/** Уже разобранный отказ: его собрал webApi, разбирать второй раз нечего. */
function asParsed(e: unknown): BackendFailure | null {
  if (!e || typeof e !== 'object') return null;
  const cand = e as Partial<BackendFailure> & { message?: string };
  if (!cand.kind || typeof cand.message !== 'string') return null;
  return { ...cand, message: cand.message, kind: cand.kind };
}

/**
 * Тело отказа. `detail` приходит в трёх видах, и это проверено на живом
 * конвертере: объектом ({code, message, hint}) у отказов конвертации, строкой
 * («Задача не найдена.») у 404, и отсутствует вовсе на 500 и на HTML от прокси.
 */
function fromBody(status: number, body: string, fallback: string): BackendFailure {
  const kind = kindOf(status);
  let detail: unknown;
  let isJson = true;
  try {
    detail = (JSON.parse(body) as { detail?: unknown })?.detail;
  } catch {
    isJson = false;
  }

  if (detail && typeof detail === 'object') {
    const d = detail as { code?: string; message?: string; hint?: string; detail?: string };
    return {
      message: d.message || fallback,
      hint: d.hint,
      code: d.code,
      status,
      kind,
      raw: d.detail,
    };
  }
  if (typeof detail === 'string' && detail.trim()) {
    return { message: detail.trim(), status, kind };
  }
  // Не JSON, а короткая строка — это объяснение от бэкенда («Конвертер не
  // запущен»), и терять его нельзя: других следов причины может не остаться.
  // HTML от прокси, обрывки JSON и длинные простыни наружу не показываем.
  const plain =
    !isJson && body.trim().length <= 200 && !/^\s*[<{[]/.test(body) ? body.trim() : '';
  const raw = body.slice(0, 500) || undefined;
  if (status >= 500) {
    return {
      message: `${fallback}: сервер ответил ошибкой ${status}. ${plain || 'Подробности — в логе программы.'}`,
      status,
      kind,
      raw,
    };
  }
  return {
    message: plain ? `${fallback} (${status}): ${plain}` : `${fallback} (${status})`,
    status,
    kind,
    raw,
  };
}

/**
 * Приводит что угодно, прилетевшее в catch, к показываемому отказу.
 * `fallback` — чем подписать отказ без объяснения от сервера («Конвертация не удалась»).
 */
export function parseBackendError(e: unknown, fallback = 'Запрос не удался'): BackendFailure {
  const parsed = asParsed(e);
  if (parsed) return parsed;

  const message = e instanceof Error ? e.message : typeof e === 'string' ? e : '';
  if (!message) return { message: fallback, kind: 'unknown' };

  if (OFFLINE_PATTERNS.some((p) => p.test(message))) {
    return { message: OFFLINE_TEXT, kind: 'offline', raw: message };
  }

  const http = HTTP_MESSAGE.exec(message);
  if (http) return fromBody(Number(http[1]), http[2], fallback);

  return { message, kind: 'unknown' };
}

/** Ошибка с разобранными полями — для слоя, который держит в руках сам ответ. */
export function backendError(status: number, body: string, fallback = 'Запрос не удался'): Error {
  const failure = fromBody(status, body, fallback);
  return Object.assign(new Error(failure.message), failure);
}
