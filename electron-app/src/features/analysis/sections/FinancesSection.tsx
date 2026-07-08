import React from 'react';
import {
  Box,
  Typography,
  Grid,
  TextField,
  Tooltip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import { ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { isFnsCreditor } from '../../../shared/lib/banks';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

/** Разбивка полей финансов на слагаемые (из нескольких обязательств): ключ поля →
 *  список форматированных сумм. Приходит из backend (result.financeBreakdown). */
export type FinanceBreakdown = Record<string, string[]> | null | undefined;

interface FinancesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  /** Разбивка «откуда число» для тултипа поля (только не-ФНС). */
  financeBreakdown?: FinanceBreakdown;
}

/** Оставляет только цифры/точку/запятую (сырое значение суммы). */
const rawAmount = (value: string) => value.replace(/[^\d.,]/g, '').replace(',', '.');

/**
 * Оборачивает поле в тултип «откуда число»: слагаемые из документа и итог «= a + b»,
 * при одном слагаемом — «Из документа: N» (сумма взята как есть). Без разбивки отдаёт
 * ребёнка как есть. Тултип — при наведении.
 */
const BreakdownTip: React.FC<{ addends?: string[]; total?: string; children: React.ReactElement }> = ({
  addends,
  total,
  children,
}) => {
  if (!addends || addends.length < 1) return children;
  return (
    <Tooltip
      arrow
      placement="top"
      title={
        <Box sx={{ fontSize: '0.8rem', lineHeight: 1.6, py: 0.5, fontVariantNumeric: 'tabular-nums' }}>
          {addends.length === 1 ? (
            // Одно слагаемое: сумма взята из документа как есть — без «= итог».
            <div>Из документа: {addends[0]}</div>
          ) : (
            <>
              {addends.map((a, i) => (
                <div key={i}>{i === 0 ? '  ' : '+ '}{a}</div>
              ))}
              <Box sx={{ borderTop: '1px solid rgba(255,255,255,0.45)', mt: 0.5, pt: 0.5, fontWeight: 600 }}>
                = {total || ''}
              </Box>
            </>
          )}
        </Box>
      }
    >
      {children}
    </Tooltip>
  );
};

// --- ФНС-раскладка: подблок очереди — 9 строк (порядок = бэкенд FNS_QUEUE_FIELD_ORDER).
//     Ключ поля = `fnsQ{n}{suffix}`. «налог/осн.долг» → LoanDebt, «недоимка» → Arrears
//     (см. память fns-queue-finances). Знак «-» (отриц. взносы) приходит в значении.
const FNS_QUEUE_FIELDS: { suffix: string; label: string }[] = [
  { suffix: 'Total', label: 'Общая сумма долга в очереди:' },
  { suffix: 'Arrears', label: 'Недоимка:' },
  { suffix: 'Penalties', label: 'Штрафные санкции:' },
  { suffix: 'Forfeit', label: 'Неустойка/пени:' },
  { suffix: 'Ndfl', label: 'НДФЛ:' },
  { suffix: 'Insurance', label: 'Страховые взносы:' },
  { suffix: 'LoanDebt', label: 'Ссудная задолженность (просроченный основной долг):' },
  { suffix: 'LoanDuty', label: 'Ссудная ГП:' },
  { suffix: 'Commission', label: 'Комиссия банка:' },
];
const FNS_QUEUE_TITLES = ['Первая очередь', 'Вторая очередь', 'Третья очередь'];
// Суффиксы полей-компонентов очереди (всё, кроме подытога Total) — для сверки.
const FNS_COMPONENT_SUFFIXES = FNS_QUEUE_FIELDS.filter((f) => f.suffix !== 'Total').map((f) => f.suffix);

/** Строка суммы → число (учёт пробелов/неразрывных пробелов/запятой/знака «-»). */
const fnsNum = (v?: string): number =>
  parseFloat((v ?? '').toString().replace(/\s/g, '').replace(',', '.')) || 0;
const fnsFmt = (n: number): string =>
  n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Строка сверки: указанный подытог (`expected`) против суммы слагаемых (`sum`).
 * Пустой блок (обе величины по нулям) не показываем — чтобы не пугать «✓» там,
 * где ничего не заполнено. Логика ⚠/✓ — как в общем (не-ФНС) блоке.
 */
const FnsReconcile: React.FC<{ label: string; expected: number; sum: number }> = ({ label, expected, sum }) => {
  if (expected === 0 && sum === 0) return null;
  const diff = Math.round((expected - sum) * 100) / 100;
  const ok = Math.abs(diff) < 0.01;
  return (
    <Grid item xs={12}>
      <Typography variant="body2" sx={{ mt: 0.5, fontWeight: 500, color: ok ? 'success.main' : 'error.main' }}>
        {ok
          ? `✓ ${label}: сходится`
          : `⚠ ${label}: Σ строк = ${fnsFmt(sum)}, указано ${fnsFmt(expected)} (расхождение ${fnsFmt(diff)}). Проверьте числа или документ.`}
      </Typography>
    </Grid>
  );
};

// Метка ФНС-ячеек — в ОБЫЧНОМ потоке над полем (не overlap): часть подписей длинные
// («Ссудная задолженность (просроченный основной долг)») и при абсолютном наложении
// переносятся на 2–3 строки и наезжают на инпут. Обычная метка переносится чисто.
const FNS_FIELD_LABEL_SX = {
  display: 'block',
  mb: 0.5,
  fontSize: '0.875rem',
  color: 'text.secondary',
  lineHeight: 1.2,
} as const;

/** Ячейка суммы (полуширина) — переиспользуется в ФНС-раскладке. */
const FnsAmountField: React.FC<{
  label: string;
  field: string;
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}> = ({ label, field, editedFields, onFieldChange }) => (
  <Grid item xs={12} sm={6}>
    <Typography variant="body2" sx={FNS_FIELD_LABEL_SX}>{label}</Typography>
    <TextField
      fullWidth
      value={editedFields[field] || ''}
      onChange={(e) => onFieldChange(field, rawAmount(e.target.value))}
      size="small"
      margin="none"
      placeholder="0.00"
    />
  </Grid>
);

/** Ячейка даты (полуширина) — переиспользуется в ФНС-раскладке. */
const FnsDateField: React.FC<{
  label: string;
  field: string;
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}> = ({ label, field, editedFields, onFieldChange }) => (
  <Grid item xs={12} sm={6}>
    <Typography variant="body2" sx={FNS_FIELD_LABEL_SX}>{label}</Typography>
    <TextField
      fullWidth
      type="date"
      value={toInputDate(editedFields[field])}
      onChange={(e) => onFieldChange(field, fromInputDate(e.target.value))}
      size="small"
      margin="none"
      InputLabelProps={{ shrink: true }}
    />
  </Grid>
);

/**
 * ФНС-раскладка «Финансовых данных»: 4 подблока (Общая информация + 1/2/3 очередь).
 * Задолженность уполномоченного органа структурирована по очередям реестра требований
 * кредиторов, поэтому плоский общий блок для ФНС не подходит. Банкротной ГП у ФНС нет.
 * Подблоки — Accordion (развёрнуты по умолчанию). См. память fns-queue-finances.
 */
const FnsFinances: React.FC<FinancesSectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Финансовые данные
    </Typography>

    <Accordion defaultExpanded disableGutters sx={{ mb: 1 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-label="Общая информация">
        <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          Общая информация
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Grid container spacing={2}>
          <FnsAmountField label="Общая сумма долга:" field="totalDebt" editedFields={editedFields} onFieldChange={onFieldChange} />
          {editedFields.fnsTotalComputed === '1' && (
            <Grid item xs={12}>
              <Typography variant="body2" sx={{ color: 'warning.main', fontWeight: 500 }}>
                ⚠ Общая сумма долга не указана в заявлении — вычислена как сумма подытогов трёх очередей. Проверьте значение.
              </Typography>
            </Grid>
          )}
          <FnsDateField label="Дата ПП депозит:" field="ppDepositDate80" editedFields={editedFields} onFieldChange={onFieldChange} />
          <FnsDateField label="Дата ПП ГП:" field="ppStateDutyDate81" editedFields={editedFields} onFieldChange={onFieldChange} />
          {/* Сверка: Общая сумма долга = Σ подытогов трёх очередей. */}
          <FnsReconcile
            label="Общая сумма долга"
            expected={fnsNum(editedFields.totalDebt)}
            sum={[1, 2, 3].reduce((acc, n) => acc + fnsNum(editedFields[`fnsQ${n}Total`]), 0)}
          />
        </Grid>
      </AccordionDetails>
    </Accordion>

    {[1, 2, 3].map((n) => (
      <Accordion key={n} defaultExpanded disableGutters sx={{ mb: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-label={FNS_QUEUE_TITLES[n - 1]}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            {FNS_QUEUE_TITLES[n - 1]}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2}>
            {FNS_QUEUE_FIELDS.map((f) => (
              <FnsAmountField
                key={f.suffix}
                label={f.label}
                field={`fnsQ${n}${f.suffix}`}
                editedFields={editedFields}
                onFieldChange={onFieldChange}
              />
            ))}
            {/* Сверка: подытог очереди = Σ её слагаемых (недоимка+штраф+пени+НДФЛ+
                взносы+ссудная задолж.+ссудная ГП+комиссия). */}
            <FnsReconcile
              label="Итог очереди"
              expected={fnsNum(editedFields[`fnsQ${n}Total`])}
              sum={FNS_COMPONENT_SUFFIXES.reduce((acc, suf) => acc + fnsNum(editedFields[`fnsQ${n}${suf}`]), 0)}
            />
          </Grid>
        </AccordionDetails>
      </Accordion>
    ))}
  </Box>
);

/**
 * Секция «Финансовые данные»: суммы долга + сверка (Общая = осн.долг + проценты +
 * неустойка + штрафы + ссудная ГП + комиссия) + даты ПП. Перенесено из
 * DocumentAnalysis 1:1 (мёртвый no-op onBlur убран).
 *
 * Для кредитора-ФНС (авто-детект или ручной выбор «ФНС») раскладка перестраивается
 * в 4 подблока по очередям реестра (FnsFinances).
 */
const FinancesSection: React.FC<FinancesSectionProps> = ({ editedFields, onFieldChange, financeBreakdown }) => {
  if (isFnsCreditor(editedFields.creditorName)) {
    return <FnsFinances editedFields={editedFields} onFieldChange={onFieldChange} />;
  }
  const brk = financeBreakdown || undefined;
  return (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Финансовые данные
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Общая сумма долга:</Typography>
          <TextField
            fullWidth
            value={editedFields.totalDebt || ''}
            onChange={(e) => onFieldChange('totalDebt', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Проценты:</Typography>
          <BreakdownTip addends={brk?.interest} total={editedFields.interest}>
          <TextField
            fullWidth
            value={editedFields.interest || ''}
            onChange={(e) => onFieldChange('interest', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Штрафные санкции:</Typography>
          <BreakdownTip addends={brk?.penalties} total={editedFields.penalties}>
          <TextField
            fullWidth
            value={editedFields.penalties || ''}
            onChange={(e) => onFieldChange('penalties', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Неустойка:</Typography>
          <BreakdownTip addends={brk?.forfeit} total={editedFields.forfeit}>
          <TextField
            fullWidth
            value={editedFields.forfeit || ''}
            onChange={(e) => onFieldChange('forfeit', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Ссудная задолженность (просроченный основной долг):</Typography>
          <BreakdownTip addends={brk?.principalDebt} total={editedFields.principalDebt || editedFields.loanDebt}>
          <TextField
            fullWidth
            value={editedFields.principalDebt || editedFields.loanDebt || ''}
            onChange={(e) => {
              const value = rawAmount(e.target.value);
              onFieldChange('principalDebt', value);
              onFieldChange('loanDebt', value);
            }}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Банкротная госпошлина:</Typography>
          <TextField
            fullWidth
            value={editedFields.stateDuty16 ?? editedFields.stateDuty ?? ''}
            onChange={(e) => {
              const value = rawAmount(e.target.value);
              onFieldChange('stateDuty16', value);
              onFieldChange('stateDuty', value);
            }}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Ссудная госпошлина:</Typography>
          <BreakdownTip addends={brk?.loanStateDuty17} total={editedFields.loanStateDuty17}>
          <TextField
            fullWidth
            value={editedFields.loanStateDuty17 ?? ''}
            onChange={(e) => onFieldChange('loanStateDuty17', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Комиссия Банка:</Typography>
          <TextField
            fullWidth
            value={editedFields.bankCommission || ''}
            onChange={(e) => onFieldChange('bankCommission', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>

      {/* Сверка финблока: Общая сумма = осн.долг + проценты + неустойка +
          штрафные санкции + ссудная госпошлина + комиссия банка. */}
      <Grid item xs={12}>
        {(() => {
          const num = (v?: string) => parseFloat((v ?? '').toString().replace(/\s/g, '').replace(',', '.')) || 0;
          const sum = num(editedFields.principalDebt || editedFields.loanDebt)
            + num(editedFields.interest)
            + num(editedFields.forfeit)
            + num(editedFields.penalties)
            + num(editedFields.loanStateDuty17)
            + num(editedFields.bankCommission);
          const total = num(editedFields.totalDebt);
          const diff = Math.round((total - sum) * 100) / 100;
          const ok = Math.abs(diff) < 0.01;
          const fmt = (n: number) => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
          return (
            <Typography variant="body2" sx={{ mt: 1, fontWeight: 500, color: ok ? 'success.main' : 'error.main' }}>
              {ok
                ? '✓ Расчеты корректны'
                : `⚠ Не сходится: Σ компонентов = ${fmt(sum)}, Общая сумма = ${fmt(total)} (расхождение ${fmt(diff)}). Проверьте числа или документ.`}
            </Typography>
          );
        })()}
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ПП депозит:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.ppDepositDate80)}
            onChange={(e) => onFieldChange('ppDepositDate80', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{
              shrink: true,
            }}
          />
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ПП ГП:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.ppStateDutyDate81)}
            onChange={(e) => onFieldChange('ppStateDutyDate81', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{
              shrink: true,
            }}
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
  );
};

export default FinancesSection;
