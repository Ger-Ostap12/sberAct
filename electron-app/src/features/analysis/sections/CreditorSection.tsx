import React from 'react';
import { Box, Typography, Grid, TextField, FormControl, Select, MenuItem } from '@mui/material';
import { BANK_NAMES } from '../../../shared/constants/banks';
import { matchBankKey } from '../../../shared/lib/banks';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface CreditorSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  onCreditorChange: (value: string) => void;
}

/**
 * Секция «Информация о кредиторе»: выбор банка из справочника (с автозаполнением)
 * либо ручной ввод + адрес/ОГРН/ИНН. Перенесено из DocumentAnalysis 1:1.
 */
const CreditorSection: React.FC<CreditorSectionProps> = ({
  editedFields,
  onFieldChange,
  onCreditorChange,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Информация о кредиторе
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Кредитор:</Typography>
          <FormControl fullWidth size="small" margin="dense">
            <Select
              value={matchBankKey(editedFields.creditorName) || (editedFields.creditorName ? 'OTHER' : '')}
              onChange={(e) => onCreditorChange(e.target.value)}
              displayEmpty
            >
              <MenuItem value="">
                <em>Выберите банк</em>
              </MenuItem>
              {BANK_NAMES.map((bankName) => (
                <MenuItem key={bankName} value={bankName}>
                  {bankName}
                </MenuItem>
              ))}
              <MenuItem value="OTHER">
                <em>Другой кредитор</em>
              </MenuItem>
            </Select>
          </FormControl>
          {!matchBankKey(editedFields.creditorName) ? (
            <Box sx={{ mt: 1, ...LABEL_OVERLAP_BOX }}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Название кредитора:</Typography>
              <TextField
                fullWidth
                value={editedFields.creditorName || ''}
                multiline
                onChange={(e) => onFieldChange('creditorName', e.target.value)}
                size="small"
                margin="dense"
                placeholder="Введите название банка вручную"
              />
            </Box>
          ) : null}
        </Box>
      </Grid>

      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Юридический адрес кредитора:</Typography>
          <TextField
            fullWidth
            value={editedFields.creditorAddress || ''}
            multiline
            onChange={(e) => onFieldChange('creditorAddress', e.target.value)}
            size="small"
            margin="dense"
            placeholder="117312, г. Москва, ул. Вавилова, д. 19"
          />
        </Box>
      </Grid>

      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ОГРН кредитора:</Typography>
          <TextField
            fullWidth
            value={editedFields.creditorOgrn || ''}
            onChange={(e) => onFieldChange('creditorOgrn', e.target.value)}
            size="small"
            margin="dense"
            placeholder="1027700132195"
          />
        </Box>
      </Grid>

      <Grid item xs={12}>
        <Box sx={LABEL_OVERLAP_BOX}>
          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН кредитора:</Typography>
          <TextField
            fullWidth
            value={editedFields.creditorInn || ''}
            onChange={(e) => onFieldChange('creditorInn', e.target.value)}
            size="small"
            margin="dense"
            placeholder="7707083893"
          />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

export default CreditorSection;
