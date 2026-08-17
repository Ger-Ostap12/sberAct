import React from 'react';
import { Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import { Add as AddIcon, Close as CloseIcon } from '@mui/icons-material';
import { PartyLite } from '../../../types';
import { isValidFio } from '../../../shared/lib/validators';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface GuarantorSectionProps {
  guarantors: PartyLite[];
  onUpdate: (index: number, field: keyof PartyLite, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

/** Секция «Информация о поручителе» (режим «Ипотека»): карточки поручителей с
 *  ФИО/ИНН/адресом. Предзаполняется из третьих лиц, юрист правит вручную. */
const GuarantorSection: React.FC<GuarantorSectionProps> = ({
  guarantors,
  onUpdate,
  onAdd,
  onRemove,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Информация о поручителе
    </Typography>
    {guarantors.map((guarantor: PartyLite, index: number) => (
      <Card key={guarantor.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            Поручитель {index + 1}
          </Typography>
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            aria-label="Удалить поручителя"
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
                value={guarantor.name || ''}
                onChange={(e) => onUpdate(index, 'name', e.target.value)}
                size="small"
                margin="dense"
                error={!isValidFio(guarantor.name)}
                helperText={!isValidFio(guarantor.name) ? 'ФИО: Фамилия Имя Отчество или Фамилия И.О.' : undefined}
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН:</Typography>
              <TextField
                fullWidth
                value={guarantor.inn || ''}
                onChange={(e) => onUpdate(index, 'inn', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес проживания:</Typography>
              <TextField
                fullWidth
                value={guarantor.address || ''}
                multiline
                onChange={(e) => onUpdate(index, 'address', e.target.value)}
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
      Добавить поручителя
    </Button>
  </Box>
);

export default GuarantorSection;
