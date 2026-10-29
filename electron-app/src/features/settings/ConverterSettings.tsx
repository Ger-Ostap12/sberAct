// Настройки конвертера PDF: ресурсный профиль и дефолт доочистки нейросетью.
// Живут в самом конвертере (его файл настроек), поэтому читаются и пишутся
// по сети и доступны только при запущенном сайдкаре.
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, MenuItem, Stack, Switch, TextField, Typography } from '@mui/material';
import {
  ConvertSettings,
  convertSaveSettings,
  convertSettings,
  converterStart,
} from '../../services/electronApi';
import { parseBackendError } from '../../shared/lib/convertErrors';

/** Подписи профилей. Замеры на корпусе из 8 сканов — в INTEGRATION.md конвертера. */
const PROFILE_LABELS: Record<string, string> = {
  auto: 'Автоматически',
  lean: 'Экономный',
  balanced: 'Средний',
  full: 'Полный',
};

const PROFILE_NOTES: Record<string, string> = {
  auto: 'Конвертер сам смотрит на память и число ядер этого компьютера.',
  lean: 'Меньше всего памяти, работает чуть дольше.',
  balanced: 'Середина между скоростью и памятью.',
  full: 'Быстрее всего, но памяти нужно больше.',
};

const ConverterSettings: React.FC<{ open: boolean }> = ({ open }) => {
  const [settings, setSettings] = useState<ConvertSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setSettings(await convertSettings());
    } catch (e) {
      setSettings(null);
      setError(parseBackendError(e, 'Настройки конвертера недоступны').message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const save = useCallback(
    async (patch: Parameters<typeof convertSaveSettings>[0]) => {
      setBusy(true);
      setError(null);
      try {
        setSettings(await convertSaveSettings(patch));
      } catch (e) {
        setError(parseBackendError(e, 'Не удалось сохранить настройку').message);
      } finally {
        setBusy(false);
      }
    },
    []
  );

  // Сайдкар поднимается только на шаге конвертации, поэтому из настроек его
  // приходится запускать вручную — иначе выбор профиля недоступен в принципе.
  const startConverter = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const started = await converterStart();
      if (!started.ok) {
        setError(parseBackendError(started.error, 'Конвертер не запустился').message);
        return;
      }
      await load();
    } finally {
      setBusy(false);
    }
  }, [load]);

  const choices = settings?.choices?.length ? settings.choices : ['auto', 'lean', 'balanced', 'full'];
  const selected = settings?.override?.profile || 'auto';
  const locked = settings?.locked_by_env === true;
  const llmOn = settings?.effective?.llm_default === true;
  const llmOverridden = settings?.override?.llm_default !== null && settings?.override?.llm_default !== undefined;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        Конвертация PDF
      </Typography>

      {!settings && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {error
              ? 'Настройки распознавания хранит сам конвертер. Он запускается на шаге конвертации — либо запустите его сейчас.'
              : 'Читаем настройки конвертера…'}
          </Typography>
          {error && (
            <Button size="small" onClick={startConverter} disabled={busy} sx={{ mt: 1 }}>
              {busy ? 'Запускаем…' : 'Запустить конвертер'}
            </Button>
          )}
        </Box>
      )}

      {settings && (
        <Stack spacing={1} sx={{ mt: 1 }}>
          <TextField
            select
            size="small"
            label="Режим использования ресурсов"
            value={selected}
            disabled={locked || busy}
            onChange={(e) => save({ profile: e.target.value })}
            sx={{ maxWidth: 320 }}
          >
            {choices.map((name) => (
              <MenuItem key={name} value={name}>
                {PROFILE_LABELS[name] || name}
              </MenuItem>
            ))}
          </TextField>

          <Typography variant="body2" color="text.secondary">
            {PROFILE_NOTES[selected] || ''}
          </Typography>

          {locked && (
            <Alert severity="info">
              Режим задан при установке приложения (переменная окружения CONVERTER_PROFILE) и
              выбор здесь не применится.
            </Alert>
          )}

          {settings.auto?.profile && (
            <Typography variant="body2" color="text.secondary">
              Определено по компьютеру: {PROFILE_LABELS[settings.auto.profile] || settings.auto.profile}
              {settings.auto.note ? ` — ${settings.auto.note}` : ''}
            </Typography>
          )}

          <Box>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Switch
                checked={llmOn}
                disabled={busy}
                onChange={(e) => save({ llm_default: e.target.checked })}
                inputProps={{ 'aria-label': 'Улучшать текст нейросетью по умолчанию' }}
              />
              <Typography variant="body2">Улучшать текст нейросетью по умолчанию</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ ml: 6 }}>
              Исправляет ошибки распознавания, но добавляет минуты работы и около 1,6 ГБ
              памяти. На шаге конвертации это можно менять для каждого файла.
            </Typography>
            {llmOverridden && (
              <Button
                size="small"
                onClick={() => save({ clear_llm_default: true })}
                disabled={busy}
                sx={{ ml: 5 }}
              >
                Вернуть как у режима
              </Button>
            )}
          </Box>
        </Stack>
      )}

      {settings && error && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
};

export default ConverterSettings;
