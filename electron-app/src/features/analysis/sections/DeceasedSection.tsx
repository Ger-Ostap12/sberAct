import React from 'react';
import { Box, Typography, Grid, TextField, Card, IconButton, Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { Heir } from '../../../types';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';
import { maskDate, isValidDateStr } from '../../../shared/lib/dates';
import { maskDeathCertificate, isValidDeathCertificate } from '../../../shared/lib/deathCertificate';

interface DeceasedSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  heirs: Heir[];
  onHeirUpdate: (index: number, field: keyof Heir, value: string) => void;
  onHeirAdd: () => void;
  onHeirRemove: (index: number) => void;
}

/** ФИО и адрес нотариуса вводит пользователь: из заявления они не подтягиваются
 *  (решение Андрея) — банк нотариуса, как правило, не называет. */
const NOTARY_FIELDS: ReadonlyArray<[label: string, key: string]> = [
  ['ФИО нотариуса:', 'notaryName'],
  ['Адрес нотариуса:', 'notaryAddress'],
];

/** Секция «Сведения о смерти» — видна при статусе должника «Умерший».
 *  Дата смерти и наследники подтягиваются из заявления (ст. 223.1), остальное
 *  вводится вручную. Ошибки валидации генерацию не блокируют — как в
 *  «Информации по счетам». */
const DeceasedSection: React.FC<DeceasedSectionProps> = ({
  editedFields,
  onFieldChange,
  heirs,
  onHeirUpdate,
  onHeirAdd,
  onHeirRemove,
}) => {
  const deathDate = editedFields.deathDate || '';
  const deathDateInvalid = !isValidDateStr(deathDate);
  const certificate = editedFields.deathCertificate || '';
  const certificateInvalid = !isValidDeathCertificate(certificate);

  return (
    <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
      <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
        Сведения о смерти
      </Typography>
      <Grid container spacing={2}>
        {NOTARY_FIELDS.map(([label, key]) => (
          <Grid item xs={12} key={key}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{label}</Typography>
              <TextField
                fullWidth
                value={editedFields[key] || ''}
                onChange={(e) => onFieldChange(key, e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>
        ))}

        <Grid item xs={12}>
          <Box sx={LABEL_OVERLAP_BOX}>
            <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата смерти:</Typography>
            <TextField
              fullWidth
              value={deathDate}
              onChange={(e) => onFieldChange('deathDate', maskDate(e.target.value))}
              size="small"
              margin="dense"
              placeholder="дд.мм.гггг"
              inputProps={{ inputMode: 'numeric' }}
              error={deathDateInvalid}
              helperText={deathDateInvalid ? 'Введите существующую дату в формате дд.мм.гггг' : ''}
            />
          </Box>
        </Grid>

        <Grid item xs={12}>
          <Box sx={LABEL_OVERLAP_BOX}>
            <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Свидетельство о смерти:</Typography>
            <TextField
              fullWidth
              value={certificate}
              onChange={(e) => onFieldChange('deathCertificate', maskDeathCertificate(e.target.value))}
              size="small"
              margin="dense"
              placeholder="II-МЮ № 123456"
              error={certificateInvalid}
              helperText={
                certificateInvalid
                  ? 'Формат: римская серия, две русские буквы и шесть цифр — II-МЮ № 123456'
                  : ''
              }
            />
          </Box>
        </Grid>
      </Grid>

      <Typography variant="subtitle2" sx={{ mt: 3, mb: 1, fontWeight: 'bold' }}>
        Наследники
      </Typography>
      {heirs.map((heir: Heir, index: number) => (
        <Card key={heir.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
              Наследник {index + 1}
            </Typography>
            <IconButton
              size="small"
              onClick={() => onHeirRemove(index)}
              aria-label="Удалить наследника"
              sx={{ color: 'text.secondary' }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО:</Typography>
                <TextField
                  fullWidth
                  value={heir.name || ''}
                  onChange={(e) => onHeirUpdate(index, 'name', e.target.value)}
                  size="small"
                  margin="dense"
                />
              </Box>
            </Grid>
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:</Typography>
                <TextField
                  fullWidth
                  value={heir.address || ''}
                  multiline
                  onChange={(e) => onHeirUpdate(index, 'address', e.target.value)}
                  size="small"
                  margin="dense"
                />
              </Box>
            </Grid>
          </Grid>
        </Card>
      ))}
      <Button
        startIcon={<AddIcon />}
        onClick={onHeirAdd}
        variant="outlined"
        size="small"
        sx={{ mt: 1 }}
      >
        Добавить наследника
      </Button>
    </Box>
  );
};

export default DeceasedSection;
