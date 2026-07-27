// Секция «Предмет ипотеки» (режим «Ипотека»): реквизиты заложенной недвижимости.
// Плоские поля из editedFields (backend извлекает их для mortgage_claim).
import React from 'react';
import { Box, Typography, Grid, TextField } from '@mui/material';
import {
  LABEL_OVERLAP_BOX,
  LABEL_OVERLAP_SX,
  BLOCK_BOX_SX,
} from '../../../shared/styles/formStyles';

interface MortgagePropertySectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const MortgagePropertySection: React.FC<MortgagePropertySectionProps> = ({
  editedFields,
  onFieldChange,
}) => {
  return (
    <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
      <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
        Предмет ипотеки
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Box sx={LABEL_OVERLAP_BOX}>
            <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Описание объекта:</Typography>
            <TextField
              fullWidth
              multiline
              value={editedFields.mortgageCollateralDescription1221 || ''}
              onChange={(e) => onFieldChange('mortgageCollateralDescription1221', e.target.value)}
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
              value={editedFields.mortgageCadastralNumber || ''}
              onChange={(e) => onFieldChange('mortgageCadastralNumber', e.target.value)}
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
              value={editedFields.mortgagePropertyAddress || ''}
              onChange={(e) => onFieldChange('mortgagePropertyAddress', e.target.value)}
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
              value={editedFields.mortgageCollateralValue1224 || ''}
              onChange={(e) => onFieldChange('mortgageCollateralValue1224', e.target.value)}
              size="small"
              margin="dense"
            />
          </Box>
        </Grid>

        <Grid item xs={12}>
          <Box sx={LABEL_OVERLAP_BOX}>
            <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Начальная цена продажи:</Typography>
            <TextField
              fullWidth
              value={editedFields.mortgageStartingPrice1225 || ''}
              onChange={(e) => onFieldChange('mortgageStartingPrice1225', e.target.value)}
              size="small"
              margin="dense"
            />
          </Box>
        </Grid>

        <Grid item xs={12}>
          <Box sx={LABEL_OVERLAP_BOX}>
            <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Отчёт об оценке:</Typography>
            <TextField
              fullWidth
              value={editedFields.mortgageAppraisalReport1223 || ''}
              onChange={(e) => onFieldChange('mortgageAppraisalReport1223', e.target.value)}
              size="small"
              margin="dense"
            />
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MortgagePropertySection;
