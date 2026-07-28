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
import AmountField from '../../../shared/components/AmountField';
import FieldQualityMark from '../../../shared/components/FieldQualityMark';
import { FieldQuality, MortgageKind } from '../../../types';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

/** Разбивка полей финансов на слагаемые (из нескольких обязательств): ключ поля →
 *  список форматированных сумм. Приходит из backend (result.financeBreakdown). */
export type FinanceBreakdown = Record<string, string[]> | null | undefined;

interface FinancesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  /** Разбивка «откуда число» для тултипа поля (только не-ФНС). */
  financeBreakdown?: FinanceBreakdown;
  /** Уровень доверия по полям (backend `fieldQuality`): поля уровня 'low'
   *  обводятся и получают тултип с причиной. Денежные поля — главная жертва
   *  чужого текста, поэтому подсветка здесь нужнее всего. */
  fieldQuality?: Record<string, FieldQuality>;
  /** Режим формы. В ипотеке добавляется вычисляемая «Итоговая сумма»
   *  (Общая сумма долга + банкротная госпошлина). */
  mode?: 'bankruptcy' | 'mortgage';
  /** Вид ипотеки. При 'military' блок финансов — поля военной ипотеки (ЦЖЗ). */
  mortgageKind?: MortgageKind;
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

/** Число из строки суммы/ставки (пробелы/запятая/знак). */
const milNum = (v?: string): number =>
  parseFloat((v ?? '').toString().replace(/\s/g, '').replace(',', '.')) || 0;
const milFmt = (n: number): string =>
  n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Дни просрочки = разница дат периода (по − с), в днях. 0, если даты пусты/некорректны. */
const milOverdueDays = (fromStr?: string, toStr?: string): number => {
  const fromIso = toInputDate(fromStr);
  const toIso = toInputDate(toStr);
  if (!fromIso || !toIso) return 0;
  const from = new Date(fromIso).getTime();
  const to = new Date(toIso).getTime();
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return 0;
  return Math.round((to - from) / 86400000);
};

// Стандартная база начисления процентов — 365 дней в году (при необходимости
// заменить на 365/366 по году периода).
const MIL_DAYS_IN_YEAR = 365;

/**
 * Справочная строка формульного расчёта (ориентировочно). НЕ сверка и НЕ ошибка:
 * приоритет — введённые из документа суммы. Формула — грубая прикидка (проценты по
 * дням/365; пени — 0,1%/день от всего долга), реальная база пени — просроченные
 * платежи по графику, которого у нас нет. Поэтому показываем расчёт нейтрально
 * (серым), без ⚠, чтобы не пугать ложным расхождением на верных данных.
 */
const MilReconcile: React.FC<{ computed: number; extra?: string }> = ({ computed, extra }) => {
  const tail = extra ? ` ${extra}` : '';
  return (
    <Grid item xs={12}>
      <Typography variant="body2" sx={{ mt: 0.25, color: 'text.secondary' }}>
        Расчёт по формуле (ориентировочно): {milFmt(computed)}.{tail}
      </Typography>
    </Grid>
  );
};

/** Ячейка суммы (полуширина) с overlap-меткой — для блока ЦЖЗ (военная ипотека).
 *  Ипотека → красивый формат по blur (AmountField). */
const MilAmountField: React.FC<{
  label: string;
  field: string;
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}> = ({ label, field, editedFields, onFieldChange }) => (
  <Grid item xs={12} sm={6}>
    <Box sx={LABEL_OVERLAP_BOX}>
      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{label}</Typography>
      <AmountField
        fullWidth
        value={editedFields[field] || ''}
        onValueChange={(v) => onFieldChange(field, v)}
        size="small"
        margin="dense"
        placeholder="0,00"
      />
    </Box>
  </Grid>
);

/**
 * Часть 2 военной ипотеки: «Взыскание в пользу ФГКУ «Росвоенипотека» (ЦЖЗ)».
 * Поля вводит пользователь (отдельные mil*-ключи, не пересекаются с «кредитной»
 * частью). ПРИОРИТЕТ — введённые значения; расчёт по формулам показывается как
 * СВЕРКА (✓/⚠). Формулы:
 *   дни просрочки = «Период по» − «с»;
 *   Проценты = Осн. долг ЦЖЗ × (Процентная ставка/100) × (дни / 365);
 *   Пени     = Осн. долг ЦЖЗ × (Ставка пени/100) × дни;
 *   Общая сумма взыскания = Осн. долг ЦЖЗ + Проценты + Пени.
 */
const CzzMilitaryFinances: React.FC<{
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}> = ({ editedFields, onFieldChange }) => {
  const principal = milNum(editedFields.milPrincipalCzz);
  const days = milOverdueDays(editedFields.milInterestPeriodFrom, editedFields.milInterestPeriodTo);
  const interestCalc = principal * (milNum(editedFields.milInterestRate) / 100) * (days / MIL_DAYS_IN_YEAR);
  const penaltyCalc = principal * (milNum(editedFields.milPenaltyRate) / 100) * days;

  // Итог сверяем со значениями, введёнными пользователем (не с формулой).
  const claim = milNum(editedFields.milTotalClaim);
  const totalFromInput = principal + milNum(editedFields.milLoanInterest) + milNum(editedFields.milPenaltySum);
  const totalDiff = Math.round((claim - totalFromInput) * 100) / 100;
  const totalOk = Math.abs(totalDiff) < 0.01;

  return (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Взыскание в пользу ФГКУ «Росвоенипотека» (ЦЖЗ)
    </Typography>
    <Grid container spacing={2}>
      <MilAmountField label="Основной долг по ЦЖЗ:" field="milPrincipalCzz" editedFields={editedFields} onFieldChange={onFieldChange} />
      <MilAmountField label="Процентная ставка (%):" field="milInterestRate" editedFields={editedFields} onFieldChange={onFieldChange} />
      <MilAmountField label="Ставка пени (%):" field="milPenaltyRate" editedFields={editedFields} onFieldChange={onFieldChange} />
      <Grid item xs={12} sm={6} />
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Период начисления процентов с:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.milInterestPeriodFrom)}
            onChange={(e) => onFieldChange('milInterestPeriodFrom', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Период начисления процентов по:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.milInterestPeriodTo)}
            onChange={(e) => onFieldChange('milInterestPeriodTo', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>

      {/* Проценты за пользование займом (ввод) + справочный расчёт. */}
      <MilAmountField label="Проценты за пользование займом:" field="milLoanInterest" editedFields={editedFields} onFieldChange={onFieldChange} />
      <MilReconcile computed={interestCalc} extra={`Дней просрочки: ${days}.`} />

      {/* Пени (ввод) + справочный расчёт. */}
      <MilAmountField label="Пени:" field="milPenaltySum" editedFields={editedFields} onFieldChange={onFieldChange} />
      <MilReconcile computed={penaltyCalc} extra={`Дней просрочки: ${days}.`} />

      {/* Общая сумма взыскания (ввод) + проверка = Осн. долг ЦЖЗ + Проценты + Пени. */}
      <MilAmountField label="Общая сумма взыскания:" field="milTotalClaim" editedFields={editedFields} onFieldChange={onFieldChange} />
      <Grid item xs={12}>
        <Typography variant="body2" sx={{ mt: 0.25, fontWeight: 500, color: totalOk ? 'success.main' : 'warning.main' }}>
          {totalOk
            ? '✓ Общая сумма взыскания сходится (Осн. долг ЦЖЗ + Проценты + Пени)'
            : `⚠ Общая сумма взыскания = ${milFmt(claim)}, а Осн. долг ЦЖЗ + Проценты + Пени = ${milFmt(totalFromInput)} (расхождение ${milFmt(totalDiff)}).`}
        </Typography>
      </Grid>
    </Grid>
  </Box>
  );
};

/**
 * Секция «Финансовые данные»: суммы долга + сверка (Общая = осн.долг + проценты +
 * неустойка + штрафы + ссудная ГП + комиссия) + даты ПП. Перенесено из
 * DocumentAnalysis 1:1 (мёртвый no-op onBlur убран).
 *
 * Для кредитора-ФНС (авто-детект или ручной выбор «ФНС») раскладка перестраивается
 * в 4 подблока по очередям реестра (FnsFinances). Военная ипотека — ДВА блока:
 * «Задолженность по кредитному договору» (поля обычной ипотеки) + «Взыскание в
 * пользу Росвоенипотеки» (ЦЖЗ, CzzMilitaryFinances).
 */
const FinancesSection: React.FC<FinancesSectionProps> = ({
  editedFields,
  onFieldChange,
  financeBreakdown,
  fieldQuality,
  mode = 'bankruptcy',
  mortgageKind = 'civil',
}) => {
  if (isFnsCreditor(editedFields.creditorName)) {
    return <FnsFinances editedFields={editedFields} onFieldChange={onFieldChange} />;
  }
  const isMortgage = mode === 'mortgage';
  // Военная ипотека: финблок из ДВУХ частей — «Задолженность по кредитному
  // договору» (поля обычной ипотеки, из заявления) + «Взыскание в пользу
  // Росвоенипотеки» (ЦЖЗ, вводит пользователь; отдельные mil*-ключи + формула).
  const isMilitary = isMortgage && mortgageKind === 'military';
  const brk = financeBreakdown || undefined;
  const q = (field: string) => fieldQuality?.[field];
  // Часть полей формы показывает одно из двух backend-полей («Ссудная
  // задолженность» = principalDebt OR loanDebt): претензия к любому из них
  // относится к тому, что видит юрист.
  const qAny = (...fields: string[]) =>
    fields.map((f) => fieldQuality?.[f]).find((item) => item?.level === 'low')
    || fieldQuality?.[fields[0]];

  const stateDutyLabel = isMortgage ? 'Госпошлина:' : 'Банкротная госпошлина:';
  // Длинная банкротная метка в overlap-стиле наезжает на инпут; в ипотеке —
  // короткий вариант (и по ТЗ в исковой части она так и называется).
  const principalLabel = isMortgage
    ? 'Просроченный основной долг:'
    : 'Ссудная задолженность (просроченный основной долг):';

  // Денежное поле: в ипотеке — красивый формат по blur (123 456,78, ввод через
  // запятую/точку); в банкротстве — прежний ввод (rawAmount) 1-в-1 (снапшот цел).
  const money = (value: string, onSet: (v: string) => void) =>
    isMortgage ? (
      <AmountField fullWidth size="small" margin="dense" placeholder="0,00" value={value} onValueChange={onSet} />
    ) : (
      <TextField
        fullWidth
        value={value}
        onChange={(e) => onSet(rawAmount(e.target.value))}
        size="small"
        margin="dense"
        placeholder="0.00"
      />
    );
  // В военной ипотеке первая часть озаглавлена по своему предмету.
  const blockTitle = isMilitary ? 'Задолженность по кредитному договору' : 'Финансовые данные';

  const civilBlock = (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      {blockTitle}
    </Typography>
    <Grid container spacing={2}>
      {/* Военная ипотека: реквизиты кредитного договора и период задолженности
          (из заявления) — «…по кредитному договору № от … за период с … по …». */}
      {isMilitary && (
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер кредитного договора:</Typography>
          <TextField
            fullWidth
            value={editedFields.creditContractNumber || ''}
            onChange={(e) => onFieldChange('creditContractNumber', e.target.value)}
            size="small"
            margin="dense"
          />
        </Box>
      </Grid>
      )}
      {isMilitary && (
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата кредитного договора:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.creditContractDate)}
            onChange={(e) => onFieldChange('creditContractDate', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      )}
      {isMilitary && (
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Период задолженности с:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.creditPeriodFrom)}
            onChange={(e) => onFieldChange('creditPeriodFrom', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      )}
      {isMilitary && (
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Период задолженности по:</Typography>
          <TextField
            fullWidth
            type="date"
            value={toInputDate(editedFields.creditPeriodTo)}
            onChange={(e) => onFieldChange('creditPeriodTo', fromInputDate(e.target.value))}
            size="small"
            margin="dense"
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Grid>
      )}
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Общая сумма долга:</Typography>
          <FieldQualityMark quality={q('totalDebt')}>
          {money(editedFields.totalDebt || '', (v) => onFieldChange('totalDebt', v))}
          </FieldQualityMark>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Проценты:</Typography>
          <BreakdownTip addends={brk?.interest} total={editedFields.interest}>
          <FieldQualityMark quality={q('interest')}>
          {money(editedFields.interest || '', (v) => onFieldChange('interest', v))}
          </FieldQualityMark>
          </BreakdownTip>
        </Box>
      </Grid>

      {/* Штрафные санкции — в ипотеке не нужны. */}
      {!isMortgage && (
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
      )}

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Неустойка:</Typography>
          <BreakdownTip addends={brk?.forfeit} total={editedFields.forfeit}>
          <FieldQualityMark quality={q('forfeit')}>
          {money(editedFields.forfeit || '', (v) => onFieldChange('forfeit', v))}
          </FieldQualityMark>
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{principalLabel}</Typography>
          <BreakdownTip addends={brk?.principalDebt} total={editedFields.principalDebt || editedFields.loanDebt}>
          <FieldQualityMark quality={qAny('principalDebt', 'loanDebt')}>
          {money(editedFields.principalDebt || editedFields.loanDebt || '', (value) => {
            onFieldChange('principalDebt', value);
            onFieldChange('loanDebt', value);
          })}
          </FieldQualityMark>
          </BreakdownTip>
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{stateDutyLabel}</Typography>
          {money(editedFields.stateDuty16 ?? editedFields.stateDuty ?? '', (value) => {
            onFieldChange('stateDuty16', value);
            onFieldChange('stateDuty', value);
          })}
        </Box>
      </Grid>

      {/* Ссудная госпошлина — банкротный реквизит, в ипотеке не нужен. */}
      {!isMortgage && (
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
      )}

      {/* Комиссия Банка — в ипотеке не нужна. */}
      {!isMortgage && (
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
      )}

      {/* Сверка финблока: Общая сумма = осн.долг + проценты + неустойка (+ в
          банкротстве: штрафные санкции + ссудная госпошлина + комиссия банка).
          В ипотеке эти три поля скрыты и в сверку не входят. */}
      <Grid item xs={12}>
        {(() => {
          const num = (v?: string) => parseFloat((v ?? '').toString().replace(/\s/g, '').replace(',', '.')) || 0;
          const sum = num(editedFields.principalDebt || editedFields.loanDebt)
            + num(editedFields.interest)
            + num(editedFields.forfeit)
            + (isMortgage ? 0 : num(editedFields.penalties))
            + (isMortgage ? 0 : num(editedFields.loanStateDuty17))
            + (isMortgage ? 0 : num(editedFields.bankCommission));
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

      {/* Итоговая сумма (ипотека) = Общая сумма долга + банкротная госпошлина.
          Вычисляется автоматически, поле только для чтения. */}
      {isMortgage && (
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Итоговая сумма:</Typography>
          {(() => {
            const num = (v?: string) => parseFloat((v ?? '').toString().replace(/\s/g, '').replace(',', '.')) || 0;
            const total = num(editedFields.totalDebt) + num(editedFields.stateDuty16 ?? editedFields.stateDuty);
            const fmt = total.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            return (
              <TextField
                fullWidth
                value={fmt}
                size="small"
                margin="dense"
                InputProps={{ readOnly: true }}
                aria-label="Итоговая сумма"
              />
            );
          })()}
        </Box>
      </Grid>
      )}

      {/* Даты платёжных поручений (депозит/ГП) — банкротные, в ипотеке скрыты. */}
      {!isMortgage && (
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
      )}

      {!isMortgage && (
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
      )}
    </Grid>
  </Box>
  );

  // Военная ипотека: к «кредитной» части добавляем блок взыскания по ЦЖЗ.
  // Два блока — в адаптивном ряду (side-by-side на широком экране, стопкой на
  // узком). Без обёртки родительский display:flex сжимал бы их в четверть ширины.
  if (isMilitary) {
    return (
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, width: '100%', alignItems: 'flex-start' }}>
        <Box sx={{ flex: '1 1 360px', minWidth: 0 }}>{civilBlock}</Box>
        <Box sx={{ flex: '1 1 360px', minWidth: 0 }}>
          <CzzMilitaryFinances editedFields={editedFields} onFieldChange={onFieldChange} />
        </Box>
      </Box>
    );
  }
  return civilBlock;
};

export default FinancesSection;
