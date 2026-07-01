import React from 'react';
import {
  Box,
  Typography,
  Card,
  IconButton,
  Grid,
  TextField,
  FormControl,
  Select,
  MenuItem,
  Button,
} from '@mui/material';
import { Add as AddIcon, Close as CloseIcon } from '@mui/icons-material';
import { Collateral, CollateralType } from '../../../types';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface CollateralSectionProps {
  collaterals: Collateral[];
  onUpdate: (index: number, field: keyof Collateral, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

/**
 * Секция «Залог»: карточки предметов залога с полями по типу (недвижимость/авто/иное).
 * JSX перенесён из DocumentAnalysis 1:1 (снапшот-сеть подтверждает идентичность).
 */
const CollateralSection: React.FC<CollateralSectionProps> = ({
  collaterals,
  onUpdate,
  onAdd,
  onRemove,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, width: '100%', mt: 2 }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Залог
    </Typography>
    {collaterals.map((collateral: Collateral, index: number) => (
      <Card key={collateral.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            Залог {index + 1}
          </Typography>
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            aria-label="Удалить залог"
            sx={{ color: 'text.secondary' }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Grid container spacing={2}>
          {/* Описание предмета залога — только для типа «Иное».
              Для недвижимости/авто описание не показываем. */}
          {collateral.collateralType === 'other' && collateral.otherDescription && collateral.otherDescription.trim() && (
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Описание предмета залога:</Typography>
                <TextField
                  fullWidth
                  multiline
                  rows={4}
                  size="small"
                  margin="dense"
                  value={collateral.otherDescription || ''}
                  onChange={(e) => onUpdate(index, 'otherDescription', e.target.value)}
                  placeholder="Описание предмета залога"
                />
              </Box>
            </Grid>
          )}
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Наименование объекта:</Typography>
              <TextField
                fullWidth
                size="small"
                margin="dense"
                value={collateral.objectName || ''}
                onChange={(e) => onUpdate(index, 'objectName', e.target.value)}
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Залоговая стоимость:</Typography>
              <TextField
                fullWidth
                size="small"
                margin="dense"
                value={collateral.collateralValue || ''}
                onChange={(e) => onUpdate(index, 'collateralValue', e.target.value)}
                placeholder="0.00"
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Тип залога:</Typography>
              <FormControl fullWidth size="small" margin="dense">
                <Select
                  value={collateral.collateralType || 'real_estate'}
                  onChange={(e) => onUpdate(index, 'collateralType', e.target.value as CollateralType)}
                >
                  <MenuItem value="real_estate">Недвижимость</MenuItem>
                  <MenuItem value="auto">Транспортное средство</MenuItem>
                  <MenuItem value="other">Иное</MenuItem>
                </Select>
              </FormControl>
            </Box>
          </Grid>
          {collateral.collateralType === 'real_estate' && (
            <>
              <Grid item xs={12}>
                <Box sx={LABEL_OVERLAP_BOX}>
                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Кадастровый номер:</Typography>
                  <TextField
                    fullWidth
                    size="small"
                    margin="dense"
                    value={collateral.cadastralNumber || ''}
                    onChange={(e) => onUpdate(index, 'cadastralNumber', e.target.value)}
                  />
                </Box>
              </Grid>
              <Grid item xs={12}>
                <Box sx={LABEL_OVERLAP_BOX}>
                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:</Typography>
                  <TextField
                    fullWidth
                    size="small"
                    margin="dense"
                    value={collateral.address || ''}
                    onChange={(e) => onUpdate(index, 'address', e.target.value)}
                  />
                </Box>
              </Grid>
            </>
          )}
          {collateral.collateralType === 'auto' && (
            <>
              <Grid item xs={12}>
                <Box sx={LABEL_OVERLAP_BOX}>
                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>VIN:</Typography>
                  <TextField
                    fullWidth
                    size="small"
                    margin="dense"
                    value={collateral.vin || ''}
                    onChange={(e) => onUpdate(index, 'vin', e.target.value)}
                  />
                </Box>
              </Grid>
              <Grid item xs={12}>
                <Box sx={LABEL_OVERLAP_BOX}>
                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Марка / модель:</Typography>
                  <TextField
                    fullWidth
                    size="small"
                    margin="dense"
                    value={collateral.brandModel || ''}
                    onChange={(e) => onUpdate(index, 'brandModel', e.target.value)}
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
      Добавить залог
    </Button>
  </Box>
);

export default CollateralSection;
