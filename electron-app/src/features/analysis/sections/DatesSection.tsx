// Секция «Даты и сроки» карточки анализа документа.
// Даты принятия/направления/поступления и текстовые сроки (возражения, движение, заседание).
import React from 'react';
import { Box, Grid, TextField, Typography } from '@mui/material';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface DatesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
}

// Умная маска для полей сроков, допускающих «дата ИЛИ текст».
// Если ввод содержит буквы («в течение 30 дней», «30 дней») — не трогаем, свободный текст.
// Если только цифры/точки/пробелы — трактуем как дату: цифры, максимум 8, точки после
// дд и мм автоматически → ДД.ММ.ГГГГ. Это чинит ввод вида «223.044.202676» (9-10 цифр).
const maskDeadline = (raw: string): string => {
  if (/[^\d.\s]/.test(raw)) return raw;
  const digits = raw.replace(/\D/g, '').slice(0, 8);
  let out = digits.slice(0, 2);
  if (digits.length > 2) out += '.' + digits.slice(2, 4);
  if (digits.length > 4) out += '.' + digits.slice(4, 8);
  return out;
};

// Нативный <input type="date"> отдаёт ISO 'YYYY-MM-DD', но на части Chromium
// в поле года можно набрать больше 4 цифр (баг: «22.04.493930»). Обрезаем год до 4.
const clampNativeDate = (iso: string): string => {
  const m = iso.match(/^(\d+)-(\d{1,2})-(\d{1,2})$/);
  if (!m) return iso;
  return `${m[1].slice(0, 4)}-${m[2]}-${m[3]}`;
};

// datetime-local отдаёт 'YYYY-MM-DDTHH:mm' — обрезаем год так же.
const clampNativeDateTime = (iso: string): string => {
  const m = iso.match(/^(\d+)(-\d{1,2}-\d{1,2}T.*)$/);
  if (!m) return iso;
  return `${m[1].slice(0, 4)}${m[2]}`;
};

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
                        onChange={(e) => onFieldChange('date', clampNativeDate(e.target.value))}
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
                        onChange={(e) => onFieldChange('courtSubmissionDate24', clampNativeDate(e.target.value))}
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
                        onChange={(e) => onFieldChange('applicationReceiptDate23', clampNativeDate(e.target.value))}
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
                        onChange={(e) => onFieldChange('objectionsDeadline18', maskDeadline(e.target.value))}
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
                        onChange={(e) => onFieldChange('considerationDeadline19', maskDeadline(e.target.value))}
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
                        onChange={(e) => onFieldChange('withoutMovementDeadline20', maskDeadline(e.target.value))}
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
                        onChange={(e) => onFieldChange('courtHearingDateTime99', clampNativeDateTime(e.target.value))}
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
