// Секция «Предмет ипотеки» (режим «Ипотека»): реквизиты заложенной недвижимости.
// Объектов может быть несколько — карточки с добавлением/удалением (как «Третьи лица»).
import React from 'react';
import { Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import { Add as AddIcon, Close as CloseIcon } from '@mui/icons-material';
import { MortgageProperty, MortgageKind } from '../../../types';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import {
  LABEL_OVERLAP_BOX,
  LABEL_OVERLAP_SX,
  BLOCK_BOX_SX,
} from '../../../shared/styles/formStyles';

interface MortgagePropertySectionProps {
  mortgageProperties: MortgageProperty[];
  onUpdate: (index: number, field: keyof MortgageProperty, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  /** Вид ипотеки. При 'ddu' добавляются поля договора долевого участия. */
  mortgageKind?: MortgageKind;
}

const MortgagePropertySection: React.FC<MortgagePropertySectionProps> = ({
  mortgageProperties,
  onUpdate,
  onAdd,
  onRemove,
  mortgageKind = 'civil',
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Предмет ипотеки
    </Typography>
    {mortgageProperties.map((property: MortgageProperty, index: number) => (
      <Card key={property.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            Предмет ипотеки {index + 1}
          </Typography>
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            aria-label="Удалить предмет ипотеки"
            sx={{ color: 'text.secondary' }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Описание объекта:</Typography>
              <TextField
                fullWidth
                multiline
                value={property.description || ''}
                onChange={(e) => onUpdate(index, 'description', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Кадастровый номер:</Typography>
              <TextField
                fullWidth
                value={property.cadastralNumber || ''}
                onChange={(e) => onUpdate(index, 'cadastralNumber', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес объекта:</Typography>
              <TextField
                fullWidth
                multiline
                value={property.address || ''}
                onChange={(e) => onUpdate(index, 'address', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Стоимость (оценка):</Typography>
              <TextField
                fullWidth
                value={property.value || ''}
                onChange={(e) => onUpdate(index, 'value', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Начальная продажная цена:</Typography>
              <TextField
                fullWidth
                value={property.startingPrice || ''}
                onChange={(e) => onUpdate(index, 'startingPrice', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Стратегия определения НПЦ:</Typography>
              <TextField
                fullWidth
                multiline
                value={property.npcStrategy || ''}
                onChange={(e) => onUpdate(index, 'npcStrategy', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Запись в ЕГРН:</Typography>
              <TextField
                fullWidth
                value={property.egrnRecord || ''}
                onChange={(e) => onUpdate(index, 'egrnRecord', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата записи ЕГРН:</Typography>
              <TextField
                fullWidth
                type="date"
                value={toInputDate(property.egrnRecordDate)}
                onChange={(e) => onUpdate(index, 'egrnRecordDate', fromInputDate(e.target.value))}
                size="small"
                margin="dense"
                InputLabelProps={{ shrink: true }}
              />
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Отчёт об оценке:</Typography>
              <TextField
                fullWidth
                value={property.appraisalReport || ''}
                onChange={(e) => onUpdate(index, 'appraisalReport', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>

          {/* ДДУ (вид ипотеки 'ddu'): договор долевого участия и его дата. */}
          {mortgageKind === 'ddu' && (
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Договор долевого участия:</Typography>
              <TextField
                fullWidth
                value={property.dduContract || ''}
                onChange={(e) => onUpdate(index, 'dduContract', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>
          )}

          {mortgageKind === 'ddu' && (
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ДДУ:</Typography>
              <TextField
                fullWidth
                type="date"
                value={toInputDate(property.dduDate)}
                onChange={(e) => onUpdate(index, 'dduDate', fromInputDate(e.target.value))}
                size="small"
                margin="dense"
                InputLabelProps={{ shrink: true }}
              />
            </Box>
          </Grid>
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
      Добавить предмет ипотеки
    </Button>
  </Box>
);

export default MortgagePropertySection;
