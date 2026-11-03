import { BackendFailure, parseBackendError } from './convertErrors';
import { getBackendDiagnostics } from '../../services/webApi';

export interface DiagnosticEvent {
  time: string;
  component: string;
  level: string;
  message: string;
  code?: string;
  operation?: string;
  hint?: string;
  incidentId?: string;
}
const entries: DiagnosticEvent[] = [];
const listeners = new Set<() => void>();
let sequence = 0;

export function redact(text: string): string {
  text = text.split('\n').map(line =>
    /requestData\s*:|(?:debtorName|applicantName|rawText|passportNumber|edited_text)["']?\s*[:=]|Данные для замены|Очищенные данные|Полученные данные/i.test(line)
      ? '[содержимое заявления скрыто]' : line).join('\n');
  text = text.replace(/([\\/]Users[\\/])[^\\/\s]+/gi, '$1[пользователь]')
    .replace(/\b\d{10,19}\b/g, '[реквизит скрыт]')
    .replace(/(^|[^А-ЯЁа-яё])[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?=[^А-ЯЁа-яё]|$)/g, '$1[ФИО скрыто]');
  return text.length > 12000 ? text.slice(0, 2000) + '\n[часть журнала сокращена]\n' + text.slice(-9000) : text;
}
export function appendEvent(entry: DiagnosticEvent, forward = true): boolean {
  const safe = { ...entry, message: redact(entry.message) };
  if (entries.some(e => e.time === safe.time && e.message === safe.message && e.incidentId === safe.incidentId)) return false;
  entries.push(safe);
  if (entries.length > 500) entries.splice(0, entries.length - 500);
  listeners.forEach(listener => { try { listener(); } catch { /* Ошибка панели не мешает операции. */ } });
  if (forward) {
    try { void window.electronAPI?.diagnosticsRecord?.(safe)?.catch(() => undefined); } catch { /* Диагностика не прерывает операцию. */ }
  }
  return true;
}
export const diagnosticEntries = (): DiagnosticEvent[] => [...entries];
export function subscribeDiagnostics(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function recordFailure(error: unknown, operation = 'Операция не выполнена'): BackendFailure {
  const failure = parseBackendError(error, operation);
  const recent = [...entries].reverse().find(e => e.level === 'error' && e.message === redact(failure.message)
    && Date.now() - Date.parse(e.time) < 3000);
  failure.hint = failure.hint || recent?.hint;
  failure.code = failure.code || recent?.code;
  const incidentId = failure.incidentId || recent?.incidentId
    || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : 'ui-' + Date.now() + '-' + ++sequence);
  appendEvent({ time: new Date().toISOString(), component: 'interface', level: 'error',
    message: failure.message, hint: failure.hint, code: failure.code, operation, incidentId });
  const raw = failure.raw || (error instanceof Error ? error.stack : undefined);
  if (raw) appendEvent({ time: new Date().toISOString(), component: 'interface', level: 'error',
    message: raw, code: failure.code, operation, incidentId });
  return { ...failure, incidentId };
}
export async function guarded<T>(operation: string, action: () => Promise<T>): Promise<T> {
  try {
    const result = await action();
    if (result && typeof result === 'object') {
      const data = result as Record<string, unknown>;
      if (typeof data.error === 'string' && /отмен[её]н.*пользовател/i.test(data.error)) return result;
      if (data.ok === false || data.success === false || data.status === 'error') {
        const failure = recordFailure({
          message: data.message || data.error || operation,
          code: data.code || data.error_code, hint: data.hint || data.error_hint,
          incidentId: data.incidentId, kind: 'unknown',
        }, operation);
        return { ...data, error: failure.message, message: failure.message,
          hint: failure.hint, code: failure.code, incidentId: failure.incidentId } as T;
      }
    }
    return result;
  } catch (cause) {
    const failure = recordFailure(cause, operation);
    throw Object.assign(new Error(failure.message), failure);
  }
}
export function initializeDiagnostics(): () => void {
  const originals = { warn: console.warn, error: console.error, info: console.info };
  const warn = (...args: unknown[]) => {
    originals.warn(...args);
    appendEvent({ time: new Date().toISOString(), component: 'interface', level: 'warning',
      message: args.map(item => item instanceof Error ? item.stack || item.message : String(item)).join(' ') });
  };
  const error = (...args: unknown[]) => {
    originals.error(...args);
    appendEvent({ time: new Date().toISOString(), component: 'interface', level: 'error',
      message: args.map(item => item instanceof Error ? item.stack || item.message : String(item)).join(' ') });
  };
  console.warn = warn;
  console.error = error;
  const onError = (event: ErrorEvent) => { recordFailure(event.error || event.message, 'Ошибка интерфейса'); };
  const onReject = (event: PromiseRejectionEvent) => { recordFailure(event.reason, 'Не удалось выполнить действие'); };
  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onReject);
  const stop = window.electronAPI?.onDiagnostic?.(entry => {
    if (!appendEvent(entry, false)) return;
    const print = entry.level === 'error' ? originals.error : entry.level === 'warning' ? originals.warn : originals.info;
    print('[' + entry.component + '] ' + (entry.incidentId || '') + ' ' + entry.message);
  });
  return () => {
    window.removeEventListener('error', onError);
    window.removeEventListener('unhandledrejection', onReject);
    stop?.();
    if (console.warn === warn) console.warn = originals.warn;
    if (console.error === error) console.error = originals.error;
  };
}
export async function collectReport(): Promise<string> {
  let remote: unknown;
  let version = '';
  try {
    remote = window.electronAPI?.diagnosticsSnapshot
      ? await window.electronAPI.diagnosticsSnapshot() : await getBackendDiagnostics();
    version = await window.electronAPI?.getAppVersion?.() || '';
    if (remote && typeof remote === 'object' && 'events' in remote) {
      const events = (remote as { events?: unknown }).events;
      if (Array.isArray(events)) for (const event of events) {
        if (event && typeof event.time === 'string' && typeof event.message === 'string')
          appendEvent(event as DiagnosticEvent, false);
      }
    }
  } catch (error) {
    remote = { collectionError: redact(String(error)) };
  }
  return JSON.stringify({ time: new Date().toISOString(), appVersion: version, platform: navigator.platform,
    events: diagnosticEntries(), services: remote },
    (key, item) => typeof item === 'string' && key !== 'incidentId' && key !== 'time' ? redact(item) : item, 2);
}
export async function copyReport(text: string): Promise<void> {
  if (window.electronAPI?.diagnosticsCopy) {
    const result = await window.electronAPI.diagnosticsCopy(text);
    if (result && result.error) throw Object.assign(new Error(result.error), result, { kind: 'unknown', message: result.error });
  } else await navigator.clipboard.writeText(text);
}
export async function saveReport(text: string): Promise<boolean> {
  if (window.electronAPI?.diagnosticsSave) {
    const result = await window.electronAPI.diagnosticsSave(text);
    if (result.error) throw Object.assign(new Error(result.error), result, { kind: 'unknown', message: result.error });
    return result.saved;
  }
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url; link.download = 'SberAct-diagnostics-' + Date.now() + '.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}
