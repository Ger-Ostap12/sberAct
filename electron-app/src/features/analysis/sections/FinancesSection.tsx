import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface FinancesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

/** Оставляет только цифры/точку/запятую (сырое значение суммы). */
const rawAmount = (value: string) => value.replace(/[^\d.,]/g, '').replace(',', '.');

/**
 * Секция «Финансовые данные»: суммы долга + сверка (Общая = осн.долг + проценты +
 * неустойка + штрафы + ссудная ГП + комиссия) + даты ПП. Перенесено из
 * DocumentAnalysis 1:1 (мёртвый no-op onBlur убран).
 */
const FinancesSection: React.FC<FinancesSectionProps> = ({ editedFields, onFieldChange }) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Финансовые данные
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Ссудная задолженность (просроченный основной долг):</Typography>
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
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Проценты:</Typography>
          <TextField
            fullWidth
            value={editedFields.interest || ''}
            onChange={(e) => onFieldChange('interest', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Штрафные санкции:</Typography>
          <TextField
            fullWidth
            value={editedFields.penalties || ''}
            onChange={(e) => onFieldChange('penalties', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>

      <Grid item xs={12} sm={6}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Неустойка:</Typography>
          <TextField
            fullWidth
            value={editedFields.forfeit || ''}
            onChange={(e) => onFieldChange('forfeit', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
        </Box>
      </Grid>

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
          <TextField
            fullWidth
            value={editedFields.loanStateDuty17 ?? ''}
            onChange={(e) => onFieldChange('loanStateDuty17', rawAmount(e.target.value))}
            size="small"
            margin="dense"
            placeholder="0.00"
          />
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
                ? '✓ Расчеты коррекны'
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

export default FinancesSection;
