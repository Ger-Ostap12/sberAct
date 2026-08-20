import React from 'react';
import { Typography } from '@mui/material';
import { useLlmHints } from '../lib/LlmHintsContext';

/**
 * Строка прогресса теневой LLM-проверки.
 *
 * Сознательно НЕ модальное окно, НЕ прогресс-бар и НЕ блокировка кнопок:
 * обычный разбор полон и пригоден к работе в момент появления формы, а
 * LLM-проверка только догоняет. Всё, что имеет право делать индикатор, —
 * объяснить, откуда позже возьмутся подсказки. По завершении исчезает.
 */
const LlmHintsProgress: React.FC = () => {
  const { running, blocksDone, blocksTotal } = useLlmHints();
  if (!running || !blocksTotal) return null;
  return (
    <Typography variant="caption" color="text.secondary" data-testid="llm-hints-progress">
      Проверка полей вторым способом: {blocksDone} из {blocksTotal} блоков
    </Typography>
  );
};

export default LlmHintsProgress;
