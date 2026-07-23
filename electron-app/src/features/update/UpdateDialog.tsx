import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  LinearProgress,
  Box,
  Alert,
  Stack,
  Divider
} from '@mui/material';
import {
  updateCheck,
  updatePickSource,
  updateDownload,
  updateApply,
  onUpdateProgress,
  onConverterProgress,
  onUpdateError,
  UpdateCheckResult
} from '../../services/electronApi';

interface UpdateDialogProps {
  open: boolean;
  onClose: () => void;
  currentVersion: string;
}

type Phase = 'idle' | 'checking' | 'checked' | 'working' | 'error';

function formatBytes(bytes: number): string {
  if (!bytes) return '0 Б';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

const UpdateDialog: React.FC<UpdateDialogProps> = ({ open, onClose, currentVersion }) => {
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<UpdateCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dlPercent, setDlPercent] = useState(0);
  const [convProgress, setConvProgress] = useState<{ done: number; total: number } | null>(null);

  const check = useCallback(async (chosen?: string) => {
    setPhase('checking');
    setError(null);
    try {
      const r = await updateCheck(chosen);
      if (!r.ok) {
        setError(r.error || 'Не удалось проверить обновления');
        setPhase('error');
        return;
      }
      setResult(r);
      setPhase('checked');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('error');
    }
  }, []);

  // Подписки на прогресс/ошибки апдейтера (только пока диалог открыт).
  useEffect(() => {
    if (!open) return undefined;
    const offProgress = onUpdateProgress((p) => setDlPercent(Math.round(p.percent)));
    const offConv = onConverterProgress((p) => setConvProgress(p));
    const offErr = onUpdateError((m) => {
      setError(m);
      setPhase('error');
    });
    return () => {
      offProgress();
      offConv();
      offErr();
    };
  }, [open]);

  // Автопроверка при открытии; сброс при закрытии.
  useEffect(() => {
    if (open) {
      setPhase((prev) => {
        if (prev === 'idle') void check();
        return prev;
      });
    } else {
      setPhase('idle');
      setResult(null);
      setError(null);
      setDlPercent(0);
      setConvProgress(null);
    }
  }, [open, check]);

  const pick = useCallback(async () => {
    const r = await updatePickSource();
    if (r.ok && r.path) await check(r.path);
  }, [check]);

  const install = useCallback(async () => {
    if (!result) return;
    setPhase('working');
    setError(null);
    setDlPercent(0);
    setConvProgress(null);
    try {
      let appDownloaded = false;
      if (result.app.available) {
        const d = await updateDownload();
        if (!d.ok) {
          setError(d.error || 'Не удалось скачать обновление приложения');
          setPhase('error');
          return;
        }
        appDownloaded = true;
      }
      const applyRes = await updateApply({
        appDownloaded,
        converterPlan: result._converterPlan || null
      });
      if (!applyRes.ok) {
        setError(applyRes.error || 'Не удалось применить обновление');
        setPhase('error');
        return;
      }
      // При успехе приложение перезапустится само (applyRes.restarting).
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('error');
    }
  }, [result]);

  const working = phase === 'working';
  const canInstall =
    phase === 'checked' &&
    !!result &&
    (result.app.available || result.converter.available);
  const nothingToDo =
    phase === 'checked' &&
    !!result &&
    !result.app.available &&
    !result.converter.available;

  return (
    <Dialog open={open} onClose={working ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Обновление с флешки</DialogTitle>
      <DialogContent dividers>
        {phase === 'checking' && (
          <Box sx={{ py: 2 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              Поиск обновления…
            </Typography>
            <LinearProgress />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {result && (phase === 'checked' || phase === 'working') && (
          <Stack spacing={2}>
            {result.source && (
              <Typography variant="caption" color="text.secondary">
                Источник: {result.source}
              </Typography>
            )}

            {/* Канал app+backend */}
            <Box>
              <Typography variant="subtitle2">Приложение</Typography>
              {result.app.available ? (
                <Typography variant="body2" color="success.main">
                  Доступно: v{currentVersion} → v{result.app.version}
                </Typography>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  {result.app.error ? `Не проверено: ${result.app.error}` : 'Актуальная версия'}
                </Typography>
              )}
            </Box>

            <Divider />

            {/* Канал converter */}
            <Box>
              <Typography variant="subtitle2">Модуль конвертации (OCR)</Typography>
              {result.converter.available ? (
                <Typography variant="body2" color="success.main">
                  Изменённых файлов: {result.converter.filesChanged}
                  {result.converter.filesDeleted ? `, удаляемых: ${result.converter.filesDeleted}` : ''}
                  {' '}({formatBytes(result.converter.bytes || 0)})
                </Typography>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Актуальная версия
                </Typography>
              )}
            </Box>

            {nothingToDo && (
              <Alert severity="info">Установлена последняя версия — обновлять нечего.</Alert>
            )}

            {working && (
              <Box>
                {result.app.available && (
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      Скачивание приложения… {dlPercent}%
                    </Typography>
                    <LinearProgress variant="determinate" value={dlPercent} />
                  </Box>
                )}
                {convProgress && (
                  <Box>
                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      Обновление конвертера… {convProgress.done}/{convProgress.total}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={convProgress.total ? (convProgress.done / convProgress.total) * 100 : 0}
                    />
                  </Box>
                )}
                {!result.app.available && !convProgress && <LinearProgress />}
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                  После установки приложение перезапустится автоматически. Не закрывайте его.
                </Typography>
              </Box>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={pick} disabled={working}>
          Выбрать папку…
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose} disabled={working}>
          Закрыть
        </Button>
        {phase === 'error' && (
          <Button onClick={() => check()} variant="outlined">
            Повторить
          </Button>
        )}
        {canInstall && (
          <Button onClick={install} variant="contained">
            Установить и перезапустить
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default UpdateDialog;
