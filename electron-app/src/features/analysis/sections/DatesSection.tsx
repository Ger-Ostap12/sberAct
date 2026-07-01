// Секция «Даты и сроки» карточки анализа документа.
// Даты принятия/направления/поступления и текстовые сроки (возражения, движение, заседание).
import React from 'react';
import { Box, Grid, TextField, Typography } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface DatesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

const DatesSection: React.FC<DatesSectionProps> = ({ editedFields, onFieldChange }) => {
  return (
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Даты и сроки
                </Typography>
                <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата принятия определения:</Typography>
                  <TextField
                    fullWidth
                        type="date"
                        value={editedFields.date || ''}
                        onChange={(e) => onFieldChange('date', e.target.value)}
                    size="small"
                    margin="dense"
                        InputLabelProps={{
                          shrink: true,
                        }}
                  />
                    </Box>
                </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата направления в суд:</Typography>
                      <TextField
                        fullWidth
                        type="date"
                        value={editedFields.courtSubmissionDate24 ?? ''}
                        onChange={(e) => onFieldChange('courtSubmissionDate24', e.target.value)}
                        size="small"
                        margin="dense"
                        InputLabelProps={{
                          shrink: true,
                        }}
                      />
                    </Box>
                  </Grid>

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата поступления заявления в суд (согласно штампу):</Typography>
                  <TextField
                    fullWidth
                        type="date"
                        value={editedFields.applicationReceiptDate23 ?? ''}
                        onChange={(e) => onFieldChange('applicationReceiptDate23', e.target.value)}
                    size="small"
                    margin="dense"
                        InputLabelProps={{
                          shrink: true,
                        }}
                  />
                    </Box>
                </Grid>

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Установка срока на предоставление возражений:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.objectionsDeadline18 ?? ''}
                        onChange={(e) => onFieldChange('objectionsDeadline18', e.target.value)}
                    size="small"
                    margin="dense"
                        placeholder="ДД.ММ.ГГГГ или текст"
                  />
                    </Box>
                </Grid>

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>На рассмотрение заявления в срок:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.considerationDeadline19 ?? ''}
                        onChange={(e) => onFieldChange('considerationDeadline19', e.target.value)}
                    size="small"
                    margin="dense"
                        placeholder="ДД.ММ.ГГГГ или текст"
                  />
                    </Box>
                </Grid>

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Срок для оставления без движения:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.withoutMovementDeadline20 ?? ''}
                        onChange={(e) => onFieldChange('withoutMovementDeadline20', e.target.value)}
                    size="small"
                    margin="dense"
                        placeholder="ДД.ММ.ГГГГ или текст"
                  />
                    </Box>
                </Grid>

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата и время судебного заседания:</Typography>
                  <TextField
                    fullWidth
                        type="datetime-local"
                        value={editedFields.courtHearingDateTime99 ?? ''}
                        onChange={(e) => onFieldChange('courtHearingDateTime99', e.target.value)}
                    size="small"
                    margin="dense"
                        InputLabelProps={{
                          shrink: true,
                        }}
                  />
                    </Box>
                  </Grid>
                </Grid>
              </Box>
  );
};

export default DatesSection;
