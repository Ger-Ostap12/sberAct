import React, { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, FormControlLabel, Switch, Typography, Box,
} from '@mui/material';
import { isLlmHintsEnabled, setLlmHintsEnabled } from './settingsStore';

interface SettingsDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Настройки приложения. Пока одна — выключатель LLM-проверки.
 *
 * Выключатель нужен именно как выключатель НАГРУЗКИ, а не как скрытие
 * интерфейса: при выключенной настройке задача не создаётся вообще и сайдкар
 * с моделью не поднимается. На слабой машине это разница между «работает» и
 * «всё подтормаживает пару минут».
 */
const SettingsDialog: React.FC<SettingsDialogProps> = ({ open, onClose }) => {
  const [llmEnabled, setLlm] = useState(true);

  // Читаем при каждом открытии: настройка могла измениться в другом окне.
  useEffect(() => {
    if (open) setLlm(isLlmHintsEnabled());
  }, [open]);

  const handleToggle = (checked: boolean) => {
    setLlm(checked);
    setLlmHintsEnabled(checked);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Настройки</DialogTitle>
      <DialogContent>
        <FormControlLabel
          control={
            <Switch
              checked={llmEnabled}
              onChange={(e) => handleToggle(e.target.checked)}
              inputProps={{ 'aria-label': 'Проверка полей через LLM' }}
            />
          }
          label="Проверка полей через LLM"
        />
        <Box sx={{ ml: 6, mt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Второй независимый способ разбора. Работает в фоне и ничего не
            подставляет автоматически — только отмечает поля, где его результат
            разошёлся с обычным разбором.
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Нагружает процессор на 1–3 минуты после загрузки документа. На
            слабых компьютерах проверку лучше отключить.
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Закрыть</Button>
      </DialogActions>
    </Dialog>
  );
};

export default SettingsDialog;
