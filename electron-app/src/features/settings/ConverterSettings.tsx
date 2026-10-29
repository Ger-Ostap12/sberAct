// Настройки конвертера PDF: ресурсный профиль и доочистка нейросетью.
//
// Выбор хранится в настройках приложения, а не в файле конвертера: сайдкар
// живёт только на шаге конвертации, и в диалоге настроек его обычно нет.
// Профиль уходит полем `profile` при запуске конвертации (конвертер принимает
// его как разовое переопределение), поэтому выбор действует всегда.
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { ConvertSettings, convertSaveSettings, convertSettings } from '../../services/electronApi';
import {
  ConverterLlmChoice,
  ConverterProfileChoice,
  getConverterLlm,
  getConverterProfile,
  setConverterLlm,
  setConverterProfile,
} from './settingsStore';

/** Подписи профилей. Замеры на корпусе из 8 сканов — в INTEGRATION.md конвертера. */
const PROFILES: { value: ConverterProfileChoice; label: string; note: string }[] = [
  {
    value: 'auto',
    label: 'Автоматически',
    note: 'Конвертер сам смотрит на память и число ядер этого компьютера.',
  },
  { value: 'lean', label: 'Экономный', note: 'Меньше всего памяти, работает чуть дольше.' },
  { value: 'balanced', label: 'Средний', note: 'Середина между скоростью и памятью.' },
  { value: 'full', label: 'Полный', note: 'Быстрее всего, но памяти нужно больше.' },
];

const LLM_CHOICES: { value: ConverterLlmChoice; label: string }[] = [
  { value: 'auto', label: 'Как решит режим' },
  { value: 'on', label: 'Всегда включать' },
  { value: 'off', label: 'Всегда выключать' },
];

const PROFILE_LABELS: Record<string, string> = Object.fromEntries(
  PROFILES.map((p) => [p.value, p.label])
);

const ConverterSettings: React.FC<{ open: boolean }> = ({ open }) => {
  const [profile, setProfile] = useState<ConverterProfileChoice>('auto');
  const [llm, setLlm] = useState<ConverterLlmChoice>('auto');
  // Вердикт конвертера о машине — только пояснение. Нет сайдкара — нет строки.
  const [remote, setRemote] = useState<ConvertSettings | null>(null);

  useEffect(() => {
    if (!open) return;
    setProfile(getConverterProfile());
    setLlm(getConverterLlm());
    // Сайдкар может быть не запущен — это нормально, молча обходимся без него.
    convertSettings()
      .then(setRemote)
      .catch(() => setRemote(null));
  }, [open]);

  // Конвертеру выбор тоже отдаём, если он на связи: тогда его собственный
  // llm_default совпадёт с выбранным и не будет спорить с интерфейсом.
  const pushToConverter = useCallback(
    (patch: Parameters<typeof convertSaveSettings>[0]) => {
      convertSaveSettings(patch)
        .then(setRemote)
        .catch(() => {
          /* сайдкара нет — настройка всё равно применится полем запроса */
        });
    },
    []
  );

  const changeProfile = (value: ConverterProfileChoice) => {
    setProfile(value);
    setConverterProfile(value);
    pushToConverter({ profile: value });
  };

  const changeLlm = (value: ConverterLlmChoice) => {
    setLlm(value);
    setConverterLlm(value);
    pushToConverter(value === 'auto' ? { clear_llm_default: true } : { llm_default: value === 'on' });
  };

  const locked = remote?.locked_by_env === true;
  const note = PROFILES.find((p) => p.value === profile)?.note || '';

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        Конвертация PDF
      </Typography>

      <Stack spacing={1} sx={{ mt: 1 }}>
        <TextField
          select
          size="small"
          label="Режим использования ресурсов"
          value={profile}
          disabled={locked}
          onChange={(e) => changeProfile(e.target.value as ConverterProfileChoice)}
          sx={{ maxWidth: 320 }}
        >
          {PROFILES.map((p) => (
            <MenuItem key={p.value} value={p.value}>
              {p.label}
            </MenuItem>
          ))}
        </TextField>

        <Typography variant="body2" color="text.secondary">
          {note}
        </Typography>

        {locked && (
          <Alert severity="info">
            Режим задан при установке приложения (переменная окружения CONVERTER_PROFILE) и
            выбор здесь не применится.
          </Alert>
        )}

        {remote?.auto?.profile && (
          <Typography variant="body2" color="text.secondary">
            Определено по компьютеру: {PROFILE_LABELS[remote.auto.profile] || remote.auto.profile}
            {remote.auto.note ? ` — ${remote.auto.note}` : ''}
          </Typography>
        )}

        <TextField
          select
          size="small"
          label="Улучшать текст нейросетью"
          value={llm}
          onChange={(e) => changeLlm(e.target.value as ConverterLlmChoice)}
          sx={{ maxWidth: 320, mt: 1 }}
        >
          {LLM_CHOICES.map((c) => (
            <MenuItem key={c.value} value={c.value}>
              {c.label}
            </MenuItem>
          ))}
        </TextField>

        <Typography variant="body2" color="text.secondary">
          Исправляет ошибки распознавания, но добавляет минуты работы и около 1,6 ГБ памяти.
          На шаге конвертации это можно менять для каждого файла.
        </Typography>
      </Stack>
    </Box>
  );
};

export default ConverterSettings;
