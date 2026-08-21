import React from 'react';
import { Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { ThirdParty } from '../../../types';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';
import LlmFieldHint, { LlmHintPending } from '../../../shared/components/LlmFieldHint';

interface ThirdPartiesSectionProps {
  thirdParties: ThirdParty[];
  onUpdate: (index: number, field: keyof ThirdParty, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  /** Режим формы. В ипотеке добавляется поле ОГРН (третье лицо — юрлицо). */
  mode?: 'bankruptcy' | 'mortgage';
}

/** Секция «Третьи лица»: карточки третьих лиц. Перенесено из DocumentAnalysis 1:1. */
const ThirdPartiesSection: React.FC<ThirdPartiesSectionProps> = ({
  thirdParties,
  onUpdate,
  onAdd,
  onRemove,
  mode = 'bankruptcy',
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Третьи лица
    </Typography>
    {thirdParties.map((thirdParty: ThirdParty, index: number) => (
      <Card key={thirdParty.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            Третье лицо {index + 1}
          </Typography>
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            aria-label="Удалить третье лицо"
            sx={{ color: 'text.secondary' }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО/наименование :<LlmHintPending field={`thirdParties[${index}].name`} block="thirdParties" /></Typography>
              <TextField
                fullWidth
                value={thirdParty.name || ''}
                onChange={(e) => onUpdate(index, 'name', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
            <LlmFieldHint field={`thirdParties[${index}].name`} block="thirdParties" />
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата рождения:</Typography>
              <TextField
                fullWidth
                type="date"
                value={toInputDate(thirdParty.birthDate)}
                onChange={(e) => onUpdate(index, 'birthDate', fromInputDate(e.target.value))}
                size="small"
                margin="dense"
                InputLabelProps={{
                  shrink: true,
                }}
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:<LlmHintPending field={`thirdParties[${index}].address`} block="thirdParties" /></Typography>
              <TextField
                fullWidth
                value={thirdParty.address || ''}
                multiline
                onChange={(e) => onUpdate(index, 'address', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
            <LlmFieldHint field={`thirdParties[${index}].address`} block="thirdParties" />
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН:<LlmHintPending field={`thirdParties[${index}].inn`} block="thirdParties" /></Typography>
              <TextField
                fullWidth
                value={thirdParty.inn || ''}
                onChange={(e) => onUpdate(index, 'inn', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
            <LlmFieldHint field={`thirdParties[${index}].inn`} block="thirdParties" />
          </Grid>
          {mode === 'mortgage' && (
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ОГРН:</Typography>
              <TextField
                fullWidth
                value={thirdParty.ogrn || ''}
                onChange={(e) => onUpdate(index, 'ogrn', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>
          )}
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>СНИЛС:</Typography>
              <TextField
                fullWidth
                value={thirdParty.snils || ''}
                onChange={(e) => onUpdate(index, 'snils', e.target.value)}
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
      onClick={onAdd}
      variant="outlined"
      size="small"
      sx={{ mt: 1 }}
    >
      Добавить третье лицо
    </Button>
  </Box>
);

export default ThirdPartiesSection;
