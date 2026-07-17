import React from 'react';
import { Alert, AlertTitle, Box, Chip, Typography } from '@mui/material';
import { FieldIssue } from '../../../types';

/**
 * Панель «поля, требующие внимания» — то, что контракт поля (backend
 * `field_contract`) счёл чужим или подозрительным.
 *
 * Зачем. Разбор может уверенно положить в поле мусор: «Арбитражный суд Ростовской
 * области» приезжал в «Ссудную задолженность» и печатался в акте как «основной долг
 * в размере Арбитражный суд Ростовской области руб.», а документ при этом получал
 * общую уверенность 0.95. Документный `confidence` такие случаи не различает
 * (три значения на весь корпус), поэтому юристу нужен адресный список: вот эти
 * поля посмотри первыми.
 */

/** Человекочитаемые названия полей. Только те, которые контракт может пометить, —
 *  единой карты «поле → метка» в проекте нет, метки живут по секциям формы. */
const FIELD_LABELS: Record<string, string> = {
  totalDebt: 'Общая сумма задолженности',
  debtAmount: 'Сумма долга',
  requirementsSum: 'Сумма требований',
  principalDebt: 'Основной долг',
  loanDebt: 'Ссудная задолженность',
  interest: 'Проценты',
  forfeit: 'Неустойка',
  penalties: 'Штрафы',
  stateDuty: 'Госпошлина',
  creditAmount: 'Сумма кредита',
  priorAmount: 'Взыскано ранее',
  priorStateDuty: 'Госпошлина по прежнему взысканию',
  inn: 'ИНН должника',
  companyInn: 'ИНН организации',
  creditorInn: 'ИНН кредитора',
  managerInn: 'ИНН управляющего',
  thirdPartyInn: 'ИНН третьего лица',
  ogrn: 'ОГРН',
  ogrnip: 'ОГРНИП',
  creditorOgrn: 'ОГРН кредитора',
  applicantAddress: 'Адрес должника',
  creditorAddress: 'Адрес кредитора',
  debtorAddress: 'Адрес должника',
  managerAddress: 'Адрес управляющего',
  thirdPartyAddress: 'Адрес третьего лица',
  creditorName: 'Кредитор',
  sroName: 'СРО управляющего',
  courtName: 'Суд',
};

/** Поля записей списков приходят как «debtors[0].address» — у них свои метки:
 *  эти записи строятся отдельным путём, мимо fields (см. backend §J.3). */
const ENTRY_LABELS: Record<string, string> = {
  'debtors.name': 'Должник',
  'debtors.address': 'Адрес должника',
  'thirdParties.name': 'Третье лицо',
  'thirdParties.address': 'Адрес третьего лица',
  'heirs.name': 'Наследник',
  'heirs.address': 'Адрес наследника',
};

const ENTRY_FIELD_RE = /^(\w+)\[(\d+)\]\.(\w+)$/;

const fieldLabel = (field: string): string => {
  const entry = ENTRY_FIELD_RE.exec(field);
  if (entry) {
    const [, list, index, sub] = entry;
    const label = ENTRY_LABELS[`${list}.${sub}`];
    if (!label) return field;
    // Номер показываем только со второй записи: «Должник» понятнее, чем «Должник №1».
    return Number(index) > 0 ? `${label} №${Number(index) + 1}` : label;
  }
  return FIELD_LABELS[field] || field;
};

interface FieldIssuesPanelProps {
  issues?: FieldIssue[];
}

const FieldIssuesPanel: React.FC<FieldIssuesPanelProps> = ({ issues }) => {
  if (!issues || issues.length === 0) return null;

  // Вычищенные — сверху: там поле пустое, его надо заполнить, это блокирует акт.
  // Помеченные — ниже: значение на месте, но его стоит сверить с документом.
  const cleared = issues.filter((i) => i.cleared);
  const flagged = issues.filter((i) => !i.cleared);

  const renderIssue = (issue: FieldIssue, idx: number) => (
    <Box key={`${issue.field}-${idx}`} sx={{ mb: 0.75 }}>
      <Typography variant="body2" component="span" sx={{ fontWeight: 600 }}>
        {fieldLabel(issue.field)}
      </Typography>
      <Typography variant="body2" component="span" sx={{ ml: 0.5 }}>
        — {issue.reason}
      </Typography>
      {issue.value && (
        <Chip
          size="small"
          variant="outlined"
          label={`было: ${issue.value.length > 60 ? `${issue.value.slice(0, 60)}…` : issue.value}`}
          sx={{ ml: 1, maxWidth: '100%' }}
        />
      )}
    </Box>
  );

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <AlertTitle>Поля, требующие внимания</AlertTitle>
      {cleared.length > 0 && (
        <Box sx={{ mb: flagged.length ? 1 : 0 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
            Очищены — значение принадлежало другому полю, введите верное:
          </Typography>
          {cleared.map(renderIssue)}
        </Box>
      )}
      {flagged.length > 0 && (
        <Box>
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
            Оставлены, но проверьте по документу:
          </Typography>
          {flagged.map(renderIssue)}
        </Box>
      )}
    </Alert>
  );
};

export default FieldIssuesPanel;
