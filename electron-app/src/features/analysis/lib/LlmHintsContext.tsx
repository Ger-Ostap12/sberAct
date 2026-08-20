import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { LlmHint, llmHintsCancel, llmHintsStart, llmHintsStatus } from '../../../services/electronApi';
import { isLlmHintsEnabled } from '../../settings/settingsStore';

/**
 * Теневой LLM-слой: второй независимый способ разбора, работающий в фоне.
 *
 * Почему контекст, а не пропсы (в приложении это первый контекст вообще).
 * Подсказки приходят порциями по мере готовности блоков — четыре-пять раз за
 * документ — и нужны в пяти секциях сразу. Проброс пропсами перерисовывал бы
 * всю форму на каждое обновление, а сама раскладка пропсов уже заметна на
 * fieldQuality, который тянется через три секции.
 *
 * Слой НИЧЕГО не подставляет: молчание = согласие, расхождение = сигнал
 * юристу перепроверить конкретное поле.
 */

const POLL_INTERVAL_MS = 2000;
/** Опрос переживает несколько неудачных тиков: сайдкар мог ещё подниматься. */
const MAX_POLL_FAILURES = 3;

export interface LlmHintsValue {
  /** true — задача идёт; иконка ожидания у непроверенных полей. */
  running: boolean;
  blocksDone: number;
  blocksTotal: number;
  /** Подсказка по полю или undefined (согласие, ещё не проверено, закрыто). */
  hintFor: (field: string) => LlmHint | undefined;
  dismiss: (field: string) => void;
  /** Блок уже проверен — значит по его полям ждать больше нечего. */
  isBlockDone: (block: string) => boolean;
}

const EMPTY: LlmHintsValue = {
  running: false,
  blocksDone: 0,
  blocksTotal: 0,
  hintFor: () => undefined,
  dismiss: () => undefined,
  isBlockDone: () => false,
};

const LlmHintsContext = createContext<LlmHintsValue>(EMPTY);

export const useLlmHints = (): LlmHintsValue => useContext(LlmHintsContext);

interface ProviderProps {
  /** Полный текст документа. Пусто/undefined — слой не запускается. */
  rawText?: string;
  /** Текущие значения полей формы: `courtName`, `debtors[0].inn`, … */
  regexValues: Record<string, string>;
  /** Ипотека — единственный поддерживаемый вид на этой итерации. */
  enabled: boolean;
  children: React.ReactNode;
}

export const LlmHintsProvider: React.FC<ProviderProps> = ({
  rawText, regexValues, enabled, children,
}) => {
  const [hints, setHints] = useState<LlmHint[]>([]);
  const [doneBlocks, setDoneBlocks] = useState<string[]>([]);
  const [blocksDone, setBlocksDone] = useState(0);
  const [blocksTotal, setBlocksTotal] = useState(0);
  const [running, setRunning] = useState(false);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobId = useRef<string | null>(null);
  const failures = useRef(0);
  // Значения полей нужны только в момент старта; держим в ref, чтобы правка
  // поля юристом не перезапускала задачу.
  const valuesRef = useRef(regexValues);
  valuesRef.current = regexValues;

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !rawText || !isLlmHintsEnabled()) return undefined;

    let cancelled = false;
    setRunning(true);

    llmHintsStart(rawText, valuesRef.current)
      .then(({ job_id }) => {
        if (cancelled) {
          llmHintsCancel(job_id);
          return;
        }
        jobId.current = job_id;
        timer.current = setInterval(async () => {
          try {
            const s = await llmHintsStatus(job_id);
            failures.current = 0;
            setHints(s.hints || []);
            setBlocksDone(s.blocksDone || 0);
            setBlocksTotal(s.blocksTotal || 0);
            if (s.lastBlock) {
              setDoneBlocks((prev) => (prev.includes(s.lastBlock!) ? prev : [...prev, s.lastBlock!]));
            }
            if (s.status !== 'running' && s.status !== 'queued') {
              stop();
              setRunning(false);
            }
          } catch {
            failures.current += 1;
            if (failures.current >= MAX_POLL_FAILURES) {
              stop();
              setRunning(false);
            }
          }
        }, POLL_INTERVAL_MS);
      })
      .catch(() => {
        // Слой недоступен (нет модели, сайдкар не поднялся) — это штатная
        // ситуация, а не ошибка для пользователя: молча работаем без него.
        setRunning(false);
      });

    return () => {
      cancelled = true;
      stop();
      setRunning(false);
      if (jobId.current) {
        llmHintsCancel(jobId.current);
        jobId.current = null;
      }
    };
  }, [enabled, rawText, stop]);

  const dismiss = useCallback((field: string) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(field);
      return next;
    });
  }, []);

  const value = useMemo<LlmHintsValue>(() => {
    const byField = new Map(hints.map((h) => [h.field, h]));
    return {
      running,
      blocksDone,
      blocksTotal,
      hintFor: (field: string) => (dismissed.has(field) ? undefined : byField.get(field)),
      dismiss,
      isBlockDone: (block: string) => doneBlocks.includes(block),
    };
  }, [hints, running, blocksDone, blocksTotal, dismissed, dismiss, doneBlocks]);

  return <LlmHintsContext.Provider value={value}>{children}</LlmHintsContext.Provider>;
};
