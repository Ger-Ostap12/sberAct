import React from 'react';
import { Box, Tooltip } from '@mui/material';
import { FieldQuality } from '../../types';

/**
 * Помечает поле, к которому у разбора есть претензия (backend `field_contract`).
 *
 * Зачем. Разбор умеет уверенно класть в поле чужой текст: «Арбитражный суд
 * Ростовской области» приезжал в «Ссудную задолженность» и печатался в акте как
 * «основной долг в размере Арбитражный суд Ростовской области руб.». Документный
 * `confidence` такие случаи не различает (три значения на весь корпус), поэтому
 * подозрительное поле должно быть видно прямо в форме, а не только в списке сверху.
 *
 * Показываем ТОЛЬКО уровень 'low' — рамка + причина в тултипе. 'medium' — обычное
 * состояние почти всех полей, его подсветка была бы шумом; 'high' не требует
 * внимания юриста по определению.
 */
interface FieldQualityMarkProps {
  quality?: FieldQuality;
  /** Контрол поля (TextField/Select) — оборачивается как есть. */
  children: React.ReactElement;
}

/**
 * ⚠️ Обязательно forwardRef + проброс props: компонент вкладывается ВНУТРЬ
 * `BreakdownTip` (тултип «откуда число»), а MUI Tooltip вешает на своего ребёнка
 * ref и обработчики наведения. Обычная функция-компонент их проглатывала — тултип
 * разбивки молча переставал открываться (поймано его же тестами).
 */
const FieldQualityMark = React.forwardRef<unknown, FieldQualityMarkProps>(
  ({ quality, children, ...rest }, ref) => {
    if (!quality || quality.level !== 'low') {
      return React.cloneElement(children, { ref, ...rest });
    }

    const title = quality.cleared
      ? `Поле очищено: ${quality.reasons.join('; ')}. Введите верное значение.`
      : `Проверьте по документу: ${quality.reasons.join('; ')}`;

    return (
      <Tooltip arrow placement="top" title={title}>
        {/* Рамка красится через дочерний OutlinedInput — так не нужно менять сами
            секции, где поля собраны вручную из Box + Typography + TextField. */}
        <Box
          {...rest}
          ref={ref as React.Ref<HTMLDivElement>}
          data-testid="field-quality-low"
          sx={{
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: 'warning.main',
              borderWidth: 2,
            },
          }}
        >
          {children}
        </Box>
      </Tooltip>
    );
  },
);

FieldQualityMark.displayName = 'FieldQualityMark';

export default FieldQualityMark;
