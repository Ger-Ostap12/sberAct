import React from 'react';
import { Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { PartyLite } from '../../../types';
import { isValidFio } from '../../../shared/lib/validators';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface CoborrowerSectionProps {
  coborrowers: PartyLite[];
  onUpdate: (index: number, field: keyof PartyLite, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

/** Секция «Созаёмщик» (режим «Ипотека»): карточки созаёмщиков с ФИО/ИНН/адресом.
 *  Предзаполняется из со-должников, юрист правит вручную. */
const CoborrowerSection: React.FC<CoborrowerSectionProps> = ({
  coborrowers,
  onUpdate,
  onAdd,
  onRemove,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Созаёмщик
    </Typography>
    {coborrowers.map((coborrower: PartyLite, index: number) => (
      <Card key={coborrower.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            Созаёмщик {index + 1}
          </Typography>
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            aria-label="Удалить созаёмщика"
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
                value={coborrower.name || ''}
                onChange={(e) => onUpdate(index, 'name', e.target.value)}
                size="small"
                margin="dense"
                error={!isValidFio(coborrower.name)}
                helperText={!isValidFio(coborrower.name) ? 'ФИО: Фамилия Имя Отчество или Фамилия И.О.' : undefined}
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН:</Typography>
              <TextField
                fullWidth
                value={coborrower.inn || ''}
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
                value={coborrower.address || ''}
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
      Добавить созаёмщика
    </Button>
  </Box>
);

export default CoborrowerSection;
