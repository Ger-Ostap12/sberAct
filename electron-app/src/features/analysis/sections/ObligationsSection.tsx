import React from 'react';
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  Grid,
  TextField,
  Button,
} from '@mui/material';
import { Add as AddIcon, Close as CloseIcon, ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import { Obligation } from '../../../types';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface ObligationsSectionProps {
  obligations: Obligation[];
  onUpdate: (index: number, patch: Partial<Obligation>) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

/**
 * Секция «Обязательства»: список сворачиваемых карточек (Accordion). По умолчанию
 * каждая карточка свёрнута — при большом числе обязательств экран не растягивается;
 * разворачивается кликом по шапке (стрелка). Кнопка удаления в шапке не триггерит
 * разворот (stopPropagation).
 */
const ObligationsSection: React.FC<ObligationsSectionProps> = ({
  obligations,
  onUpdate,
  onAdd,
  onRemove,
}) => (
  <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
      Обязательства
    </Typography>
    {obligations.map((obligation: Obligation, index: number) => (
      <Accordion key={obligation.id} disableGutters sx={{ mb: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-label={`Обязательство ${index + 1}`}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', pr: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
              Обязательство {index + 1}
              {obligation.contractNumber ? ` — № ${obligation.contractNumber}` : ''}
            </Typography>
            <IconButton
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                onRemove(index);
              }}
              aria-label="Удалить обязательство"
              sx={{ color: 'text.secondary' }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер договора:</Typography>
                <TextField
                  fullWidth
                  value={obligation.contractNumber || ''}
                  multiline
                  onChange={(e) => onUpdate(index, { contractNumber: e.target.value })}
                  size="small"
                  margin="dense"
                />
              </Box>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Box sx={LABEL_OVERLAP_BOX}>
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата договора:</Typography>
                <TextField
                  fullWidth
                  type="date"
                  value={toInputDate(obligation.contractDate)}
                  onChange={(e) => onUpdate(index, { contractDate: fromInputDate(e.target.value) })}
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
                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Тип обязательства:</Typography>
                <TextField
                  fullWidth
                  value={obligation.obligationType || ''}
                  multiline
                  onChange={(e) => onUpdate(index, { obligationType: e.target.value })}
                  size="small"
                  margin="dense"
                />
              </Box>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>
    ))}
    <Button
      startIcon={<AddIcon />}
      onClick={onAdd}
      variant="outlined"
      size="small"
      sx={{ mt: 1 }}
    >
      Добавить обязательство
    </Button>
  </Box>
);

export default ObligationsSection;
