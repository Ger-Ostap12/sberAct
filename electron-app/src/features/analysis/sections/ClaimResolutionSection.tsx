import { MILITARY_FLAGS, militaryAmountActive } from '../lib/militaryMortgageAwards';
import React from 'react';
import {
  Alert, Box, Checkbox, FormControlLabel, Grid, Radio, RadioGroup, TextField, Typography,
} from '@mui/material';
import { BLOCK_BOX_SX } from '../../../shared/styles/formStyles';
import { MortgageKind } from '../../../types';
import {
  awardAmounts, AWARD_OPTIONS, awardChecked, awardNumber, awardTotal, awardValue,
  mortgageAwardsError,
} from '../lib/mortgageAwards';

interface ClaimResolutionSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  mortgageKind?: MortgageKind;
}

const ClaimResolutionSection: React.FC<ClaimResolutionSectionProps> = ({
  editedFields, onFieldChange, mortgageKind = 'civil',
}) => {
  const partial = editedFields.claimResolution === 'partial';
  const debt = awardChecked(editedFields, 'mortgageAwardDebt');
  const error = mortgageAwardsError(editedFields, mortgageKind);
  const total = partial ? awardTotal(editedFields, mortgageKind) : null;

  return (
    <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
      <Typography variant="h6" gutterBottom sx={{ mb: 1, color: 'primary.main' }}>
        Удовлетворение иска
      </Typography>
      <RadioGroup
        value={editedFields.claimResolution || ''}
        onChange={(e) => onFieldChange('claimResolution', e.target.value)}
        sx={{ pl: 1 }}
      >
        <FormControlLabel value="full" control={<Radio size="small" />} label="Удовлетворить полностью" />
        <FormControlLabel value="partial" control={<Radio size="small" />} label="Удовлетворить частично" />
        <FormControlLabel value="deny" control={<Radio size="small" />} label="Отказать в удовлетворении" />
      </RadioGroup>
      {partial && (
        <Box sx={{ mt: 2 }} role="group" aria-label="Частичное удовлетворение">
          <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 600 }}>
            Какие требования удовлетворены
          </Typography>
          {(mortgageKind === 'military' ? MILITARY_FLAGS : AWARD_OPTIONS).map(({ key, label }) => (
            <FormControlLabel
              key={key}
              sx={{ display: 'flex', ml: 0 }}
              control={<Checkbox size="small" checked={awardChecked(editedFields, key)}
                onChange={(event) => onFieldChange(key, event.target.checked ? 'true' : 'false')} />}
              label={label}
            />
          ))}
          <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>
            Укажите присуждённые суммы. Суммы заявления в финансовых данных сохраняются.
            Продажа залога и начальная цена включаются вместе с обращением взыскания.
          </Typography>
          <Grid container spacing={2}>
            {awardAmounts(mortgageKind).filter(({ key }) => mortgageKind === 'military'
              ? militaryAmountActive(editedFields, key) : debt || key === 'mortgageAwardDuty')
              .map(({ key, label }) => (
                <Grid item xs={12} sm={mortgageKind === 'ddu' && key.includes('Penalty') ? 12 : 6} key={key}>
                  <TextField
                    fullWidth size="small" label={label}
                    value={awardValue(editedFields, key, mortgageKind)}
                    onChange={(event) => onFieldChange(key, event.target.value)}
                    inputProps={{ inputMode: 'decimal' }}
                    error={awardNumber(awardValue(editedFields, key, mortgageKind)) === null}
                    placeholder="0,00"
                  />
                </Grid>
              ))}
            <Grid item xs={12}>
              <TextField
                fullWidth size="small" label="Итого присуждено"
                value={total === null ? '' : total.toLocaleString('ru-RU', {
                  minimumFractionDigits: 2, maximumFractionDigits: 2,
                })}
                InputProps={{ readOnly: true }}
              />
            </Grid>
          </Grid>
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        </Box>
      )}
    </Box>
  );
};

export default ClaimResolutionSection;
