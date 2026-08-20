import React from 'react';
import { Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import { Add as AddIcon, Close as CloseIcon } from '@mui/icons-material';
import { Debtor, EntityType, FieldQuality } from '../../../types';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { isValidPassportSeries, isValidPassportNumber, digitsOnly } from '../../../shared/lib/validators';
import FieldQualityMark from '../../../shared/components/FieldQualityMark';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';
import LlmFieldHint, { LlmHintPending } from '../../../shared/components/LlmFieldHint';

interface DebtorsSectionProps {
  debtors: Debtor[];
  entityType: EntityType | null;
  onUpdate: (index: number, field: keyof Debtor, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  /** Уровень доверия по полям (backend `fieldQuality`). Ключ записи —
   *  `debtors[N].address`: карточки строятся мимо `fields` (ловушка §J.3),
   *  поэтому у них СВОИ ключи, а не плоские имена полей. */
  fieldQuality?: Record<string, FieldQuality>;
  /** Режим формы. В ипотеке роль называется «Ответчик» и добавляется паспорт. */
  mode?: 'bankruptcy' | 'mortgage';
}

/**
 * Секция «Данные должника»/«Данные ответчика»: карточки лиц с реквизитами по типу
 * лица (ОГРН/ОГРНИП, место/дата рождения). В ипотеке — «Ответчик» + паспорт.
 */
const DebtorsSection: React.FC<DebtorsSectionProps> = ({
  debtors,
  entityType,
  onUpdate,
  onAdd,
  onRemove,
  fieldQuality,
  mode = 'bankruptcy',
}) => {
  const isMortgage = mode === 'mortgage';
  const role = isMortgage ? 'ответчик' : 'должник';
  const Role = isMortgage ? 'Ответчик' : 'Должник';
  return (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      {isMortgage ? 'Данные ответчика' : 'Данные должника'}
    </Typography>
    {debtors.map((debtor: Debtor, index: number) => (
      <Card key={debtor.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        {debtors.length > 1 && (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
              {Role} {index + 1}
            </Typography>
            <IconButton
              size="small"
              onClick={() => onRemove(index)}
              aria-label={`Удалить ${role}а`}
              sx={{ color: 'text.secondary' }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        )}
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>
                {isMortgage ? 'ФИО:' : 'ФИО/наименование:'}
                <LlmHintPending field={`debtors[${index}].name`} block="debtors" />
              </Typography>
              <TextField
                fullWidth
                value={debtor.name || ''}
                onChange={(e) => onUpdate(index, 'name', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
            <LlmFieldHint field={`debtors[${index}].name`} block="debtors" />
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>
                {isMortgage ? 'Адрес ответчика:' : 'Адрес должника:'}
                <LlmHintPending field={`debtors[${index}].address`} block="debtors" />
              </Typography>
              <FieldQualityMark quality={fieldQuality?.[`debtors[${index}].address`]}>
                <TextField
                  fullWidth
                  value={debtor.address || ''}
                  multiline
                  onChange={(e) => onUpdate(index, 'address', e.target.value)}
                  size="small"
                  margin="dense"
                />
              </FieldQualityMark>
            </Box>
            <LlmFieldHint field={`debtors[${index}].address`} block="debtors" />
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>
                ИНН:<LlmHintPending field={`debtors[${index}].inn`} block="debtors" />
              </Typography>
              <FieldQualityMark quality={fieldQuality?.[`debtors[${index}].inn`]}>
                <TextField
                  fullWidth
                  value={debtor.inn || ''}
                  onChange={(e) => onUpdate(index, 'inn', e.target.value)}
                  size="small"
                  margin="dense"
                />
              </FieldQualityMark>
            </Box>
            <LlmFieldHint field={`debtors[${index}].inn`} block="debtors" />
          </Grid>
          {/* Реквизит должника по типу лица: ФЛ — нет ОГРН/ОГРНИП;
              ИП — ОГРНИП; ЮЛ/КФХ (и неопределённый тип) — ОГРН. */}
          {entityType !== 'individual' && (
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>
                  {entityType === 'ip' ? 'ОГРНИП:' : 'ОГРН:'}
                </Typography>
                <FieldQualityMark
                  quality={fieldQuality?.[`debtors[${index}].${entityType === 'ip' ? 'ogrnip' : 'ogrn'}`]}
                >
                  <TextField
                    fullWidth
                    value={(entityType === 'ip' ? debtor.ogrnip : debtor.ogrn) || ''}
                    onChange={(e) => onUpdate(index, entityType === 'ip' ? 'ogrnip' : 'ogrn', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </FieldQualityMark>
              </Box>
            </Grid>
          )}
          {/* Город/место рождения — только для физлица (ЮЛ/ИП/КФХ не имеют). */}
          {entityType === 'individual' && (
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Город/место рождения:</Typography>
                <TextField
                  fullWidth
                  value={debtor.birthPlace ?? ''}
                  multiline
                  onChange={(e) => onUpdate(index, 'birthPlace', e.target.value)}
                  size="small"
                  margin="dense"
                  placeholder="например: г. Москва"
                />
              </Box>
            </Grid>
          )}
          {/* Дата рождения — для всех, кроме юрлица. */}
          {entityType !== 'legal' && (
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата рождения:<LlmHintPending field={`debtors[${index}].birthDate`} block="debtors" /></Typography>
                <TextField
                  fullWidth
                  type="date"
                  value={toInputDate(debtor.birthDate)}
                  onChange={(e) => onUpdate(index, 'birthDate', fromInputDate(e.target.value))}
                  size="small"
                  margin="dense"
                  InputLabelProps={{ shrink: true }}
                />
              </Box>
            <LlmFieldHint field={`debtors[${index}].birthDate`} block="debtors" />
            </Grid>
          )}
          {/* Паспорт — только в ипотеке (роль «Ответчик»). Серия 4 / номер 6 цифр. */}
          {isMortgage && (
            <>
              <Grid item xs={6}>
                <Box sx={LABEL_OVERLAP_BOX}>
                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Паспорт (серия):</Typography>
                  <TextField
                    fullWidth
                    value={debtor.passportSeries || ''}
                    onChange={(e) => onUpdate(index, 'passportSeries', digitsOnly(e.target.value, 4))}
                    size="small"
                    margin="dense"
                    inputProps={{ inputMode: 'numeric', maxLength: 4 }}
                    error={!isValidPassportSeries(debtor.passportSeries)}
                    helperText={!isValidPassportSeries(debtor.passportSeries) ? '4 цифры' : undefined}
                    placeholder="6018"
                  />
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box sx={LABEL_OVERLAP_BOX}>
                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Паспорт (номер):</Typography>
                  <TextField
                    fullWidth
                    value={debtor.passportNumber || ''}
                    onChange={(e) => onUpdate(index, 'passportNumber', digitsOnly(e.target.value, 6))}
                    size="small"
                    margin="dense"
                    inputProps={{ inputMode: 'numeric', maxLength: 6 }}
                    error={!isValidPassportNumber(debtor.passportNumber)}
                    helperText={!isValidPassportNumber(debtor.passportNumber) ? '6 цифр' : undefined}
                    placeholder="123456"
                  />
                </Box>
              </Grid>
            </>
          )}
        </Grid>
      </Card>
    ))}
    <Button
      startIcon={<AddIcon />}
      onClick={onAdd}
      variant="outlined"
      size="small"
      sx={{ mt: 1 }}
    >
      {isMortgage ? 'Добавить ответчика' : 'Добавить должника'}
    </Button>
  </Box>
  );
};

export default DebtorsSection;
