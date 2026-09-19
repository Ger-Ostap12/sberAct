import React from 'react';
import { Box, Typography, Card, IconButton, Grid, TextField, Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { Creditor } from '../../../types';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface CreditorsListSectionProps {
  creditors: Creditor[];
  onUpdate: (index: number, field: keyof Creditor, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

/**
 * Секция «Кредиторы»: список кредиторов, перечисленных САМИМ должником
 * в заявлении о собственном банкротстве. Их бывает до полутора десятков,
 * поэтому карточками — как третьи лица.
 *
 * Не путать с блоком «Кредитор» (CreditorSection): там ОДИН кредитор-заявитель
 * с выбором банка из справочника. У самобанкрота заявителя-кредитора нет вовсе.
 */
const CreditorsListSection: React.FC<CreditorsListSectionProps> = ({
  creditors,
  onUpdate,
  onAdd,
  onRemove,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Кредиторы
    </Typography>
    {creditors.map((creditor: Creditor, index: number) => (
      <Card key={creditor.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            Кредитор {index + 1}
          </Typography>
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            aria-label="Удалить кредитора"
            sx={{ color: 'text.secondary' }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Наименование:</Typography>
              <TextField
                fullWidth
                value={creditor.name || ''}
                onChange={(e) => onUpdate(index, 'name', e.target.value)}
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
                value={creditor.address || ''}
                multiline
                onChange={(e) => onUpdate(index, 'address', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН:</Typography>
              <TextField
                fullWidth
                value={creditor.inn || ''}
                onChange={(e) => onUpdate(index, 'inn', e.target.value)}
                size="small"
                margin="dense"
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ОГРН:</Typography>
              <TextField
                fullWidth
                value={creditor.ogrn || ''}
                onChange={(e) => onUpdate(index, 'ogrn', e.target.value)}
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
      Добавить кредитора
    </Button>
  </Box>
);

export default CreditorsListSection;
