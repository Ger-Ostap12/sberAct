import { FieldInput } from '../components/FieldInput';
import React from 'react';
import { Alert, Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
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
  /** Предупреждение юристу: разбор дал больше одного должника. */
  notice?: string | null;
  dismissNotice?: () => void;
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
  notice,
  dismissNotice,
}) => {
  const isMortgage = mode === 'mortgage';
  const role = isMortgage ? 'ответчик' : 'должник';
  const Role = isMortgage ? 'Ответчик' : 'Должник';
  return (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      {isMortgage ? 'Данные ответчика' : 'Данные должника'}
    </Typography>
    {notice && (
      <Alert severity="warning" sx={{ mb: 2 }} onClose={dismissNotice}>
        {notice}
      </Alert>
    )}
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
              <FieldInput
                fullWidth
                value={debtor.name || ''}
                onChange={(значение) => onUpdate(index, 'name', значение)}
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
                <FieldInput
                  fullWidth
                  value={debtor.address || ''}
                  multiline
                  onChange={(значение) => onUpdate(index, 'address', значение)}
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
                <FieldInput
                  fullWidth
                  value={debtor.inn || ''}
                  onChange={(значение) => onUpdate(index, 'inn', значение)}
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
                  <FieldInput
                    fullWidth
                    value={(entityType === 'ip' ? debtor.ogrnip : debtor.ogrn) || ''}
                    onChange={(значение) => onUpdate(index, entityType === 'ip' ? 'ogrnip' : 'ogrn', значение)}
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
                <FieldInput
                  fullWidth
                  value={debtor.birthPlace ?? ''}
                  multiline
                  onChange={(значение) => onUpdate(index, 'birthPlace', значение)}
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
                <FieldInput
                  fullWidth
                  type="date"
                  value={toInputDate(debtor.birthDate)}
                  onChange={(значение) => onUpdate(index, 'birthDate', fromInputDate(значение))}
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
                  <FieldInput
                    fullWidth
                    value={debtor.passportSeries || ''}
                    onChange={(значение) => onUpdate(index, 'passportSeries', digitsOnly(значение, 4))}
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
                  <FieldInput
                    fullWidth
                    value={debtor.passportNumber || ''}
                    onChange={(значение) => onUpdate(index, 'passportNumber', digitsOnly(значение, 6))}
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
    {isMortgage && (
      <Button
        startIcon={<AddIcon />}
        onClick={onAdd}
        variant="outlined"
        size="small"
        sx={{ mt: 1 }}
      >
        Добавить ответчика
      </Button>
    )}
  </Box>
  );
};

export default DebtorsSection;
