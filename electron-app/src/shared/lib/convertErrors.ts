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
  incidentId?: string;
  kind: FailureKind;
  /** Техническая подробность для лога, пользователю не показывается. */
  raw?: string;
}

/** Сервера нет вовсе: «Failed to fetch» — сообщение браузера, по нему юристу нечего делать. */
export const OFFLINE_TEXT =
  'Сервис приложения не отвечает. Проверьте, что программа запущена, и повторите действие.';

const OFFLINE_PATTERNS = [
  /failed to fetch/i,
  /all backend hosts failed/i,
  /backend недоступен/i,
  /networkerror/i,
  /err_connection/i,
  /load failed/i,
  /ECONNREFUSED|ENOTFOUND|fetch failed/i,
];

/** Тело ответа: «HTTP 404: {"detail": …}» — формат обоих наших слоёв. */
const HTTP_MESSAGE = /^HTTP (\d{3}):\s*([\s\S]*)$/;

function kindOf(status: number): FailureKind {
  if (status === 404) return 'notfound';
  if (status === 410) return 'gone';
  if (status >= 500) return 'server';
  return 'http';
}

function localFailure(message: string): BackendFailure | null {
  if (/EACCES|EPERM|Permission denied|WinError (?:5|32)\b/i.test(message))
    return { message: 'Нет доступа к файлу или папке.', hint: 'Проверьте права доступа. Если документ открыт в Word, закройте его.', code: 'ACCESS_DENIED', kind: 'unknown', raw: message };
  if (/ENOENT|FileNotFoundError|No such file|WinError 2\b/i.test(message))
    return { message: 'Не найден необходимый файл.', hint: 'Проверьте наличие документа или компонентов приложения.', code: 'FILE_NOT_FOUND', kind: 'unknown', raw: message };
  if (/ENOSPC|No space left|WinError 112\b/i.test(message))
    return { message: 'Недостаточно свободного места на диске.', hint: 'Освободите место или выберите другой диск.', code: 'DISK_FULL', kind: 'unknown', raw: message };
  return null;
}

/** Уже разобранный отказ: его собрал webApi, разбирать второй раз нечего. */
function asParsed(e: unknown): BackendFailure | null {
  if (!e || typeof e !== 'object') return null;
  if (e instanceof Error && !(e as Partial<BackendFailure>).kind) return null;
  const object = e as Partial<BackendFailure> & { error?: string };
  const message = typeof object.message === 'string' ? object.message : object.error;
  if (!message || /^HTTP\b|^HTTP error!|failed to fetch|fetch failed/i.test(message)) return null;
  return { message, kind: object.kind || 'unknown', hint: object.hint, code: object.code,
    incidentId: object.incidentId, status: object.status, raw: object.raw };
}

/**
 * Тело отказа. `detail` приходит в трёх видах, и это проверено на живом
 * конвертере: объектом ({code, message, hint}) у отказов конвертации, строкой
 * («Задача не найдена.») у 404, и отсутствует вовсе на 500 и на HTML от прокси.
 */
const CODE_TEXT: Record<string, [string, string]> = {
  NOT_A_PDF: ['Выбранный файл не является PDF.', 'Выберите документ в формате PDF.'],
  PDF_CORRUPTED: ['PDF повреждён или имеет неподдерживаемую структуру.', 'Сохраните документ заново и повторите попытку.'],
  PDF_ENCRYPTED: ['PDF защищён паролем.', 'Снимите защиту или выберите другой документ.'],
  OUT_OF_MEMORY: ['Недостаточно оперативной памяти.', 'Закройте другие программы и повторите операцию.'],
  CANCELLED: ['Конвертация отменена.', 'При необходимости запустите её заново.'],
  INTERRUPTED: ['Конвертация была прервана.', 'Повторите конвертацию.'],
};
function publicText(text: string | undefined, fallback: string): string {
  return text && /[А-ЯЁа-яё]/.test(text) && !/Traceback|^HTTP|^TypeError:|^Error:/.test(text) ? text : fallback;
}

function fromBody(status: number, body: string, fallback: string): BackendFailure {
  const kind = kindOf(status);
  const statusMessage: Record<number, string> = {
    413: 'Файл слишком большой. Выберите файл меньшего размера.',
    415: 'Формат файла не поддерживается.',
    422: 'Проверьте заполнение обязательных полей.',
    504: 'Сервис не успел выполнить операцию. Повторите попытку позже.',
  };
  let detail: unknown;
  let isJson = true;
  try {
    detail = (JSON.parse(body) as { detail?: unknown })?.detail;
  } catch {
    isJson = false;
  }

  if (Array.isArray(detail)) return {
    message: 'Проверьте заполнение обязательных полей.', hint: 'Повторите действие после исправления формы.',
    code: 'INVALID_REQUEST', status, kind,
  };
  if (detail && typeof detail === 'object') {
    const d = detail as { code?: string; message?: string; hint?: string; detail?: string; incidentId?: string };
    return {
      message: localFailure(d.message || '')?.message || publicText(d.message, CODE_TEXT[d.code || '']?.[0] || statusMessage[status] || fallback),
      hint: publicText(d.hint, CODE_TEXT[d.code || '']?.[1] || 'Откройте «Подробности» и сохраните отчёт.'),
      code: d.code,
      status,
      kind,
      raw: d.detail || (d.message && !/[А-ЯЁа-яё]/.test(d.message) ? d.message : undefined),
      incidentId: d.incidentId,
    };
  }
  if (typeof detail === 'string' && detail.trim()) {
    return { ...(localFailure(detail) || { message: publicText(detail.trim(), statusMessage[status] || fallback),
      raw: !/[А-ЯЁа-яё]/.test(detail) ? detail : undefined }), status, kind };
  }
  // Не JSON, а короткая строка — это объяснение от бэкенда («Конвертер не
  // запущен»), и терять его нельзя: других следов причины может не остаться.
  // HTML от прокси, обрывки JSON и длинные простыни наружу не показываем.
  const plain =
    !isJson && body.trim().length <= 200 && !/^\s*[<{[]/.test(body) ? body.trim() : '';
  const raw = body.slice(0, 500) || undefined;
  if (status >= 500) {
    return {
      message: publicText(plain, statusMessage[status] || fallback),
      hint: 'Откройте «Подробности» и сохраните отчёт об ошибке.',
      status,
      kind,
      raw,
    };
  }
  return {
    message: publicText(plain, statusMessage[status] || fallback),
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
  if (parsed) {
    const known = localFailure(parsed.message);
    if (known) return { ...parsed, ...known };
    if (!/[А-ЯЁа-яё]/.test(parsed.message) || /Traceback|WinError|ENOENT|EACCES/.test(parsed.message))
      return { ...parsed, message: fallback, raw: parsed.raw || parsed.message,
        hint: parsed.hint || 'Откройте «Подробности» и сохраните отчёт.' };
    return parsed;
  }

  const object = e && typeof e === 'object' ? e as { message?: string; error?: string } : undefined;
  const message = e instanceof Error ? e.message : typeof e === 'string' ? e : object?.message || object?.error || '';
  if (!message) return { message: fallback, kind: 'unknown' };

  if (OFFLINE_PATTERNS.some((p) => p.test(message))) {
    return { message: OFFLINE_TEXT, kind: 'offline', raw: message };
  }

  const legacy = /HTTP error! status: (\d{3})(?:, message: ([\s\S]*))?/.exec(message);
  if (legacy) return fromBody(Number(legacy[1]), legacy[2] || '', fallback);
  const http = HTTP_MESSAGE.exec(message.replace(/^Error invoking remote method [^:]+:\s*(?:Error:\s*)?/, ''));
  if (http) return fromBody(Number(http[1]), http[2], fallback);

  const local = localFailure(message);
  if (local) return local;
  const technical = !/[А-ЯЁа-яё]/.test(message) || /Traceback|WinError|ENOENT|EACCES|ECONN|^Error:|^TypeError:|^Internal Server Error|<html/i.test(message);
  if (technical) return { message: fallback, hint: 'Откройте «Подробности» и сохраните отчёт.', kind: 'unknown', raw: message };
  return { message, kind: 'unknown' };
}

/** Ошибка с разобранными полями — для слоя, который держит в руках сам ответ. */
export function backendError(status: number, body: string, fallback = 'Запрос не удался'): Error {
  const failure = fromBody(status, body, fallback);
  return Object.assign(new Error(failure.message), failure);
}
