import React from 'react';
import { Alert, AlertTitle, Box, Tooltip } from '@mui/material';
import PendingIcon from '@mui/icons-material/HourglassEmpty';
import { useLlmHints } from '../../features/analysis/lib/LlmHintsContext';

/**
 * Подсказка теневого LLM-слоя у конкретного поля.
 *
 * Молчание — нормальный исход. Иконка ожидания появляется, пока блок ещё не
 * проверен, и ТИХО исчезает, если LLM согласилась с разбором: тревожить юриста
 * ради подтверждения того, что и так верно, — прямой путь к тому, что он
 * перестанет читать подсказки вообще.
 *
 * Ничего не подставляется автоматически. Тот же принцип, что у
 * DebtorNameWarning и FieldQualityMark: показать расхождение, решение оставить
 * человеку.
 */

interface LlmFieldHintProps {
  /** Ключ поля формы: `courtName`, `debtors[0].inn`, … */
  field: string;
  /** Блок, к которому поле относится — по нему понимаем, ждать ли ещё. */
  block: string;
  /** Юрист уже правил это поле руками — тогда подсказка только шумит. */
  edited?: boolean;
}

/** Маленькая иконка у метки поля: «проверяем». Без текста, без блокировки. */
export const LlmHintPending: React.FC<LlmFieldHintProps> = ({ field, block, edited }) => {
  const { running, hintFor, isBlockDone } = useLlmHints();
  if (edited || !running || isBlockDone(block) || hintFor(field)) return null;
  return (
    <Tooltip title="Идёт проверка поля вторым способом">
      <PendingIcon
        data-testid="llm-hint-pending"
        sx={{ fontSize: 14, opacity: 0.45, ml: 0.5, verticalAlign: 'middle' }}
      />
    </Tooltip>
  );
};

/** Баннер расхождения — под контролом, в том же Grid item. */
const LlmFieldHint: React.FC<LlmFieldHintProps> = ({ field, block, edited }) => {
  const { hintFor, dismiss } = useLlmHints();
  const hint = hintFor(field);
  if (edited || !hint) return null;
  return (
    <Box sx={{ mt: 0.5 }}>
      <Alert
        severity="warning"
        onClose={() => dismiss(field)}
        data-testid="llm-hint-alert"
        sx={{ mb: 1 }}
      >
        <AlertTitle>Перепроверьте «{hint.label}»</AlertTitle>
        {hint.llmValue && !hint.regexValue ? (
          <>
            Автоматический разбор не нашёл значение для этого поля, а второй
            способ проверки нашёл «{hint.llmValue}». Проверьте по документу и
            впишите вручную, если верно.
          </>
        ) : hint.llmValue ? (
          <>
            Автоматический разбор дал «{hint.regexValue}», но второй способ
            проверки нашёл «{hint.llmValue}». Сверьте значение с текстом
            документа вручную.
          </>
        ) : (
          <>
            Значение «{hint.regexValue}» не похоже на то, что должно быть в этом
            поле{hint.reason ? ` (${hint.reason})` : ''}. Сверьте с текстом
            документа вручную.
          </>
        )}
      </Alert>
    </Box>
  );
};

export default LlmFieldHint;
