import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  FormGroup,
  LinearProgress,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  AutoFixHigh as ConvertIcon,
  Download as DownloadIcon,
  NavigateNext as NextIcon,
  SkipNext as SkipIcon,
} from '@mui/icons-material';
import { AnalysisResult } from '../../types';
import {
  analyzeDocument,
  analyzeText,
  convertAnalyze,
  convertDownload,
  convertNative,
  convertScan,
  convertStatus,
  converterStart,
  ConvertScanFlags,
  DocxSection,
  docxApplyEdits,
  docxText,
} from '../../services/electronApi';
import PdfPanel from './PdfPanel';
import SectionedEditor from './SectionedEditor';

type Phase =
  | 'starting' // подъём sidecar-процесса конвертера (холодный старт LLM — до минут)
  | 'classify' // POST /convert/analyze: скан или нативный
  | 'ready' // режим определён, ждём кнопку «Конвертировать»
  | 'converting' // задача в конвертере, поллинг статуса
  | 'preview' // текст готов: правка + панель исходного PDF
  | 'analyzing' // «Далее»: правленый текст ушёл в /analyze-text
  | 'error';

type ConvertMode = 'scan' | 'native';

const POLL_INTERVAL_MS = 1500;

// Дефолты скан-режима — РОВНО как у родного фронта конвертера
// (converter/frontend/src/ScanConverter.tsx DEFAULT_FLAGS). Критично:
// no_highlight=false включает подсветку сомнительных слов и их LLM-доочистку;
// без явных флагов API-дефолт no_highlight=true ОТКЛЮЧАЛ доочистку — качество
// распознавания падало (баг, найденный Андреем).
const SCAN_DEFAULT_FLAGS: ConvertScanFlags = {
  no_highlight: false,
  word_order: false,
  iim: true,
  ink_bold: false,
  ocr_preprocess: false,
};

// Настройки распознавания — те же, что в родном фронте конвертера (FLAG_DEFS
// из ScanConverter.tsx): названия, описания и дефолты совпадают, чтобы
// пользователь получал одинаковый результат в обеих программах.
//   invert: галочка показывает обратное значение флага («галочка = включено»).
const SCAN_FLAG_DEFS: {
  key: keyof ConvertScanFlags;
  title: string;
  desc: string;
  invert?: boolean;
}[] = [
  {
    key: 'no_highlight',
    invert: true,
    title: 'Подсвечивать сомнительные слова',
    desc: 'Выделяет жёлтым слова, в распознавании которых программа не уверена. Включено по умолчанию.',
  },
  {
    key: 'iim',
    title: 'Улучшать текст нейросетью (ИИ)',
    desc: 'Локальная нейросеть исправляет ошибки распознавания. Работает чуть дольше. Включено по умолчанию.',
  },
  {
    key: 'ocr_preprocess',
    title: 'Улучшать качество плохих сканов',
    desc: 'Выравнивает наклон и повышает контраст. Помогает тёмным и перекошенным сканам, но может ухудшить чёткие.',
  },
  {
    key: 'word_order',
    title: 'Восстанавливать порядок строк на сложных сканах',
    desc: 'Помогает, когда колонки или строки распознаются вперемешку. Обычно не требуется.',
  },
  {
    key: 'ink_bold',
    title: 'Определять жирный шрифт по толщине букв',
    desc: 'Экспериментальная функция, может ошибаться. По умолчанию выключено.',
  },
];

interface ConvertScreenProps {
  /** Загруженный пользователем PDF. */
  file: File;
  /** Анализ завершён (правленый текст или skip-путь) — переход на шаг analysis. */
  onComplete: (result: AnalysisResult) => void;
  /** Возврат на загрузку (конвертер будет остановлен). */
  onBack: () => void;
}

/**
 * Convert-шаг: PDF → OCR-конвертер (sidecar) → правка распознанного ТЕКСТА
 * (тот же текст, что уходит в анализ — извлечён бэкендом из DOCX полным
 * экстрактором, без потерь HTML-предпросмотра) → «Далее» (/analyze-text).
 * «Скачать DOCX» — оригинальная вёрстка конвертера; «Скачать с правками» —
 * бэкенд вставляет правки в оригинальную вёрстку (/docx-apply-edits).
 */
const ConvertScreen: React.FC<ConvertScreenProps> = ({ file, onComplete, onBack }) => {
  const [phase, setPhase] = useState<Phase>('starting');
  const [mode, setMode] = useState<ConvertMode>('scan');
  const [detectedMode, setDetectedMode] = useState<ConvertMode | null>(null);
  const [detectReason, setDetectReason] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [docxBlob, setDocxBlob] = useState<Blob | null>(null);
  const [editedText, setEditedText] = useState('');
  const [sections, setSections] = useState<DocxSection[]>([]);
  const [scanFlags, setScanFlags] = useState<ConvertScanFlags>(SCAN_DEFAULT_FLAGS);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  // Подъём конвертера + классификация PDF (авто, при входе на шаг)
  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      setPhase('starting');
      setError(null);
      // Холодный старт конвертера — до минуты, плюс бэкенд мог сам ещё подниматься
      // при первом запуске приложения. Тихо ретраим, показывая «запускается», и
      // только после нескольких неудач показываем ошибку — чтобы транзиентные сбои
      // старта не пугали пользователя.
      let started: { ok: boolean; error?: string } = { ok: false };
      for (let attempt = 0; attempt < 5 && !cancelled; attempt++) {
        started = await converterStart();
        if (cancelled) return;
        if (started.ok) break;
        await new Promise((r) => setTimeout(r, 3000));
      }
      if (cancelled) return;
      if (!started.ok) {
        setError(started.error || 'Конвертер недоступен');
        setPhase('error');
        return;
      }
      setPhase('classify');
      try {
        const verdict = await convertAnalyze(file);
        if (cancelled) return;
        const detected: ConvertMode = verdict.suggested === 'native' ? 'native' : 'scan';
        setDetectedMode(detected);
        setMode(detected);
        setDetectReason(typeof verdict.reason === 'string' ? verdict.reason : null);
      } catch {
        // Классификация — удобство, не обязательность: даём выбрать руками
        if (!cancelled) setDetectedMode(null);
      }
      if (!cancelled) setPhase('ready');
    };
    boot();
    return () => {
      cancelled = true;
    };
  }, [file]);

  const failWith = useCallback(
    (message: string) => {
      stopPolling();
      setError(message);
      setPhase('error');
    },
    [stopPolling]
  );

  const handleConvert = useCallback(async () => {
    setPhase('converting');
    setProgress(0);
    setStage('Отправляем документ…');
    setError(null);
    try {
      const { job_id: jobId } =
        mode === 'native'
          ? await convertNative(file)
          : await convertScan(file, scanFlags);
      pollTimer.current = setInterval(async () => {
        try {
          const status = await convertStatus(jobId);
          setProgress(status.progress ?? 0);
          setStage(status.stage || '');
          if (status.status === 'done') {
            stopPolling();
            const blob = await convertDownload(jobId);
            // Текст для правки — с бэкенда, тем же экстрактором, что анализ
            const extracted = await docxText(blob);
            setDocxBlob(blob);
            setEditedText(extracted.text || '');
            setSections(extracted.sections || []);
            setPhase('preview');
          } else if (status.status === 'error') {
            failWith(status.error || 'Ошибка конвертации');
          }
        } catch (e) {
          failWith(e instanceof Error ? e.message : 'Потеряна связь с конвертером');
        }
      }, POLL_INTERVAL_MS);
    } catch (e) {
      failWith(e instanceof Error ? e.message : 'Не удалось запустить конвертацию');
    }
  }, [file, mode, failWith, stopPolling]);

  // Старый путь без конвертера: pypdf вытащит текст нативного PDF
  const handleSkip = useCallback(async () => {
    setPhase('analyzing');
    setError(null);
    try {
      const result = await analyzeDocument(file);
      onComplete(result);
    } catch (e) {
      failWith(
        e instanceof Error
          ? `Анализ без конвертации не удался: ${e.message}`
          : 'Анализ без конвертации не удался'
      );
    }
  }, [file, onComplete, failWith]);

  const handleNext = useCallback(async () => {
    setPhase('analyzing');
    setError(null);
    try {
      const result = await analyzeText(editedText);
      onComplete(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка анализа текста');
      setPhase('preview');
    }
  }, [editedText, onComplete]);

  const triggerDownload = useCallback((blob: Blob, fileName: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, []);

  const baseName = file.name.replace(/\.pdf$/i, '');

  const handleDownloadOriginal = useCallback(() => {
    if (docxBlob) triggerDownload(docxBlob, `${baseName}.docx`);
  }, [docxBlob, baseName, triggerDownload]);

  // Правки вставляются в ОРИГИНАЛЬНУЮ вёрстку на бэкенде (/docx-apply-edits)
  const handleDownloadEdited = useCallback(async () => {
    if (!docxBlob) return;
    try {
      const blob = await docxApplyEdits(docxBlob, editedText);
      triggerDownload(blob, `${baseName} (правки).docx`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось собрать DOCX с правками');
    }
  }, [docxBlob, editedText, baseName, triggerDownload]);

  // Конвертер намеренно НЕ гасим: его убивает сторож простоя на бэкенде
  // (CONVERTER_IDLE_TIMEOUT_S). Иначе каждый следующий PDF платил холодным
  // стартом с загрузкой LLM.
  const handleBack = useCallback(() => {
    stopPolling();
    onBack();
  }, [onBack, stopPolling]);

  // ── Рендер по фазам ──

  if (phase === 'preview' && docxBlob) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 130px)' }}>
        <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Проверьте распознанный текст{' '}
            <Typography component="span" variant="body2" color="text.secondary">
              (слева — исходный PDF, справа — текст с возможностью правки)
            </Typography>
          </Typography>
          <Button size="small" startIcon={<DownloadIcon />} onClick={handleDownloadOriginal}>
            Скачать DOCX
          </Button>
          <Button size="small" startIcon={<DownloadIcon />} onClick={handleDownloadEdited}>
            Скачать с правками
          </Button>
          <Button size="small" onClick={handleBack}>
            Назад
          </Button>
          <Button variant="contained" endIcon={<NextIcon />} onClick={handleNext}>
            Далее
          </Button>
        </Stack>
        {error && (
          <Alert severity="error" sx={{ mb: 1 }}>
            {error}
          </Alert>
        )}
        <Box sx={{ display: 'flex', gap: 1, flexGrow: 1, minHeight: 0 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <PdfPanel file={file} />
          </Box>
          <Box
            sx={{
              flex: 1,
              minWidth: 0,
              backgroundColor: 'grey.200',
              p: sections.length > 0 ? 1 : 2,
              overflow: 'hidden',
              display: 'flex',
            }}
          >
            {sections.length > 0 ? (
              // Посекционный редактор: те же строки extract_text, сгруппированы
              // по меткам; на выходе — канонический текст в исходном порядке.
              <SectionedEditor sections={sections} onChange={setEditedText} />
            ) : (
              // Fallback (не-DOCX/старый бэкенд): единый «лист» с плоским текстом.
              <Box
                component="textarea"
                value={editedText}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  setEditedText(e.target.value)
                }
                data-testid="text-editor"
                sx={{
                  flex: 1,
                  width: '100%',
                  border: 'none',
                  resize: 'none',
                  outline: 'none',
                  backgroundColor: 'white',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
                  px: 4,
                  py: 3,
                  fontFamily: '"Times New Roman", Times, serif',
                  fontSize: '12pt',
                  lineHeight: 1.5,
                }}
              />
            )}
          </Box>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 700, mx: 'auto' }}>
      <Typography variant="h4" component="h1" gutterBottom align="center" sx={{ mb: 3 }}>
        Конвертация PDF
      </Typography>

      <Card>
        <CardContent>
          <Typography variant="body1" sx={{ mb: 2 }}>
            Файл: <strong>{file.name}</strong>{' '}
            <Typography component="span" variant="body2" color="text.secondary">
              ({(file.size / 1024 / 1024).toFixed(2)} MB)
            </Typography>
          </Typography>

          {phase === 'starting' && (
            <Box sx={{ textAlign: 'center', py: 3 }}>
              <CircularProgress sx={{ mb: 1 }} />
              <Typography variant="body1">Запускаем конвертер…</Typography>
              <Typography variant="body2" color="text.secondary">
                Первый запуск загружает модель распознавания — это может занять до минуты
              </Typography>
            </Box>
          )}

          {phase === 'classify' && (
            <Box sx={{ textAlign: 'center', py: 3 }}>
              <CircularProgress sx={{ mb: 1 }} />
              <Typography variant="body1">Определяем тип PDF…</Typography>
            </Box>
          )}

          {phase === 'ready' && (
            <Stack spacing={2}>
              {detectedMode && (
                <Alert severity="info">
                  {detectReason ||
                    (detectedMode === 'scan'
                      ? 'Похоже, это скан (без текстового слоя) — рекомендуем режим «Скан (OCR)».'
                      : 'В PDF есть текстовый слой — подойдёт быстрый режим «Нативный PDF».')}
                </Alert>
              )}
              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Режим конвертации:
                </Typography>
                <ToggleButtonGroup
                  exclusive
                  value={mode}
                  onChange={(_, value: ConvertMode | null) => value && setMode(value)}
                  size="small"
                >
                  <ToggleButton value="scan">Скан (OCR)</ToggleButton>
                  <ToggleButton value="native">Нативный PDF</ToggleButton>
                </ToggleButtonGroup>
              </Box>

              {mode === 'scan' && (
                <Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Настройки распознавания:
                  </Typography>
                  <FormGroup>
                    {SCAN_FLAG_DEFS.map(({ key, title, desc, invert }) => {
                      const raw = Boolean(scanFlags[key]);
                      const checked = invert ? !raw : raw;
                      return (
                        <Tooltip key={key} title={desc} placement="right" arrow>
                          <FormControlLabel
                            control={
                              <Checkbox
                                size="small"
                                checked={checked}
                                onChange={(e) =>
                                  setScanFlags((prev) => ({
                                    ...prev,
                                    [key]: invert ? !e.target.checked : e.target.checked,
                                  }))
                                }
                              />
                            }
                            label={<Typography variant="body2">{title}</Typography>}
                          />
                        </Tooltip>
                      );
                    })}
                  </FormGroup>
                </Box>
              )}
              <Stack direction="row" spacing={1}>
                <Button variant="contained" startIcon={<ConvertIcon />} onClick={handleConvert}>
                  Конвертировать
                </Button>
                <Button startIcon={<SkipIcon />} onClick={handleSkip}>
                  Пропустить конвертацию
                </Button>
                <Box sx={{ flexGrow: 1 }} />
                <Button onClick={handleBack}>Назад</Button>
              </Stack>
            </Stack>
          )}

          {phase === 'converting' && (
            <Box sx={{ py: 2 }}>
              <Typography variant="body1" sx={{ mb: 1 }}>
                Конвертируем документ…
              </Typography>
              <LinearProgress
                variant={progress > 0 ? 'determinate' : 'indeterminate'}
                value={Math.round(progress * 100)}
                sx={{ mb: 1 }}
              />
              <Typography variant="body2" color="text.secondary">
                {stage || 'Распознавание может занять несколько минут'}
              </Typography>
            </Box>
          )}

          {phase === 'analyzing' && (
            <Box sx={{ textAlign: 'center', py: 3 }}>
              <CircularProgress sx={{ mb: 1 }} />
              <Typography variant="body1">Анализируем документ…</Typography>
            </Box>
          )}

          {phase === 'error' && (
            <Stack spacing={2}>
              <Alert severity="error">{error || 'Что-то пошло не так'}</Alert>
              <Stack direction="row" spacing={1}>
                <Button variant="contained" onClick={handleConvert}>
                  Повторить
                </Button>
                <Button startIcon={<SkipIcon />} onClick={handleSkip}>
                  Пропустить конвертацию
                </Button>
                <Box sx={{ flexGrow: 1 }} />
                <Button onClick={handleBack}>Назад</Button>
              </Stack>
            </Stack>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default ConvertScreen;
