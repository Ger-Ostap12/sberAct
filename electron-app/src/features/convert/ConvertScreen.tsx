import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  LinearProgress,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
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
  converterStop,
} from '../../services/electronApi';
import DocxPreviewEditor, { DocxPreviewEditorHandle } from './DocxPreviewEditor';
import PdfPanel from './PdfPanel';
import { extractPlainText } from './lib/extractPlainText';

type Phase =
  | 'starting' // подъём sidecar-процесса конвертера (холодный старт LLM — до минут)
  | 'classify' // POST /convert/analyze: скан или нативный
  | 'ready' // режим определён, ждём кнопку «Конвертировать»
  | 'converting' // задача в конвертере, поллинг статуса
  | 'preview' // DOCX готов: редактируемый предпросмотр + панель PDF
  | 'analyzing' // «Далее»: правленый текст ушёл в /analyze-text
  | 'error';

type ConvertMode = 'scan' | 'native';

const POLL_INTERVAL_MS = 1500;

interface ConvertScreenProps {
  /** Загруженный пользователем PDF. */
  file: File;
  /** Анализ завершён (правленый текст или skip-путь) — переход на шаг analysis. */
  onComplete: (result: AnalysisResult) => void;
  /** Возврат на загрузку (конвертер будет остановлен). */
  onBack: () => void;
}

/**
 * Convert-шаг: PDF → OCR-конвертер (sidecar) → Word-подобный предпросмотр с
 * правкой → «Далее» (плоский текст в /analyze-text). «Пропустить конвертацию» —
 * старый путь /analyze-document (годится для нативных PDF с текстовым слоем).
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
  const editorRef = useRef<DocxPreviewEditorHandle | null>(null);
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
      const started = await converterStart();
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
        mode === 'native' ? await convertNative(file) : await convertScan(file);
      pollTimer.current = setInterval(async () => {
        try {
          const status = await convertStatus(jobId);
          setProgress(status.progress ?? 0);
          setStage(status.stage || '');
          if (status.status === 'done') {
            stopPolling();
            const blob = await convertDownload(jobId);
            setDocxBlob(blob);
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
      converterStop().catch(() => undefined);
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
    const root = editorRef.current?.getRoot();
    if (!root) return;
    setPhase('analyzing');
    setError(null);
    try {
      const text = extractPlainText(root);
      const result = await analyzeText(text);
      converterStop().catch(() => undefined);
      onComplete(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка анализа текста');
      setPhase('preview');
    }
  }, [onComplete]);

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

  const handleDownloadEdited = useCallback(async () => {
    const root = editorRef.current?.getRoot();
    if (!root) return;
    // DOCX из правленого HTML: форматирование упрощённое (см. план §5),
    // оригинал конвертера доступен соседней кнопкой.
    const { asBlob } = await import('html-docx-js-typescript');
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>${root.innerHTML}</body></html>`;
    const result = await asBlob(html);
    const blob = result instanceof Blob ? result : new Blob([new Uint8Array(result as Buffer)]);
    triggerDownload(blob, `${baseName} (правки).docx`);
  }, [baseName, triggerDownload]);

  const handleBack = useCallback(() => {
    stopPolling();
    converterStop().catch(() => undefined);
    onBack();
  }, [onBack, stopPolling]);

  // ── Рендер по фазам ──

  if (phase === 'preview' && docxBlob) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 160px)' }}>
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
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <DocxPreviewEditor ref={editorRef} docx={docxBlob} />
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
