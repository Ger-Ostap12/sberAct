// Секция «Судебная информация» — перенесена из DocumentAnalysis 1:1.
// Внешний <Grid item> остаётся в родителе; здесь только внутренний блок-бокс.
import React from 'react';
import {
  Box,
  Typography,
  Grid,
  TextField,
  FormControl,
  Select,
  MenuItem,
  RadioGroup,
  FormControlLabel,
  Radio,
} from '@mui/material';
import { JUDGES } from '../../../shared/constants/judges';
import { formatJudgeName } from '../../../shared/lib/judges';
import {
  LABEL_OVERLAP_BOX,
  LABEL_OVERLAP_SX,
  BLOCK_BOX_SX,
} from '../../../shared/styles/formStyles';

interface CourtSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const CourtSection: React.FC<CourtSectionProps> = ({ editedFields, onFieldChange }) => {
  return (
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Судебная информация
                </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Название суда:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.courtName || ''}
                        onChange={(e) => onFieldChange('courtName', e.target.value)}
                    size="small"
                    margin="dense"
                        placeholder="Арбитражный суд Ростовской области"
                  />
                    </Box>
                </Grid>

                <Grid item xs={12}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер дела:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.caseNumber || ''}
                        onChange={(e) => onFieldChange('caseNumber', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                    </Box>
                </Grid>

                  <Grid item xs={12}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Судья:</Typography>
                      <FormControl fullWidth size="small" margin="dense">
                        <Select
                          value={editedFields.judge || ''}
                          onChange={(e) => onFieldChange('judge', e.target.value)}
                          displayEmpty
                          renderValue={(selected) => {
                            if (!selected) {
                              return <em>Выберите судью</em>;
                            }
                            // Если значение уже в формате "Фамилия И.О." (содержит точку), показываем как есть
                            // Иначе преобразуем полное ФИО в формат "Фамилия И.О."
                            if (selected.includes('.') && selected.split('.').length > 1) {
                              return selected;
                            }
                            return formatJudgeName(selected);
                          }}
                        >
                          <MenuItem value="">
                            <em>Выберите судью</em>
                          </MenuItem>
                          {JUDGES.map((judge) => (
                            <MenuItem key={judge} value={judge}>
                              {formatJudgeName(judge)}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Box>
                  </Grid>

                  {/* Роль составителя: меняет абзац «кем подготовлен акт» при генерации */}
                  <Grid item xs={12}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Лицо ведущее протокол:</Typography>
                      <RadioGroup
                        row
                        value={editedFields.authorRole || ''}
                        onChange={(e) => onFieldChange('authorRole', e.target.value)}
                        sx={{ pl: 1, pt: 0.5 }}
                      >
                        <FormControlLabel value="Помощник" control={<Radio size="small" />} label="Помощник" />
                        <FormControlLabel value="Секретарь" control={<Radio size="small" />} label="Секретарь" />
                      </RadioGroup>
                    </Box>
                  </Grid>

                  {/* ФИО составителя — метка зависит от выбранной роли */}
                  <Grid item xs={12}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>
                        {editedFields.authorRole === 'Секретарь'
                          ? 'ФИО секретаря:'
                          : editedFields.authorRole === 'Помощник'
                            ? 'ФИО помощника:'
                            : 'ФИО помощника/секретаря:'}
                      </Typography>
                      <TextField
                        fullWidth
                        value={editedFields.authorName || ''}
                        onChange={(e) => onFieldChange('authorName', e.target.value)}
                        size="small"
                        margin="dense"
                      />
                    </Box>
                  </Grid>

                <Grid item xs={12}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер обособленного спора:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.separateDisputeNumber22 ?? ''}
                        onChange={(e) => onFieldChange('separateDisputeNumber22', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                    </Box>
                  </Grid>
                </Grid>
              </Box>
  );
};

export default CourtSection;
