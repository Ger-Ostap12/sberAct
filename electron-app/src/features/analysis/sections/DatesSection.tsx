// Секция «Даты и сроки» карточки анализа документа.
// Даты принятия/направления/поступления и текстовые сроки (возражения, движение, заседание).
import React from 'react';
import { Box, Grid, TextField, Typography, InputAdornment, IconButton, Tooltip } from '@mui/material';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import { toInputDate, fromInputDate } from '../../../shared/lib/dates';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

// Календарь для поля срока. Поле остаётся свободным: юрист может написать
// «в течение 30 дней», а может выбрать конкретную дату мышью — выбор
// подставляется как ДД.ММ.ГГГГ поверх текущего значения.
//
// Нативный input скрыт, а не показан рядом: у input[type=date] нельзя убрать
// текстовую часть кроссбраузерно, и рядом с текстовым полем он выглядел бы
// вторым полем ввода. Открываем его через showPicker() — в Electron (Chromium)
// метод есть; если вдруг нет, падаем на обычный click по input.
const DeadlineDatePicker: React.FC<{ value: string; onPick: (v: string) => void }> = ({ value, onPick }) => {
  const ref = React.useRef<HTMLInputElement>(null);

  const open = () => {
    const el = ref.current;
    if (!el) return;
    const withPicker = el as HTMLInputElement & { showPicker?: () => void };
    if (typeof withPicker.showPicker === 'function') {
      withPicker.showPicker();
    } else {
      el.click();
    }
  };

  return (
    <>
      <Tooltip title="Выбрать дату в календаре">
        <IconButton size="small" edge="end" onClick={open} aria-label="Выбрать дату в календаре">
          <CalendarTodayIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <input
        ref={ref}
        type="date"
        // toInputDate вернёт пустую строку для свободного текста — календарь
        // просто откроется на текущем месяце, введённый текст не потеряется.
        value={toInputDate(value)}
        onChange={(e) => onPick(fromInputDate(clampNativeDate(e.target.value)))}
        style={{ position: 'absolute', width: 0, height: 0, opacity: 0, pointerEvents: 'none' }}
        tabIndex={-1}
        aria-hidden="true"
      />
    </>
  );
};

interface DatesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  /** Режим формы. В ипотеке: метка «Дата принятия решения», скрыты сроки
   *  возражений / рассмотрения / оставления без движения (банкротные). */
  mode?: 'bankruptcy' | 'mortgage';
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

const DatesSection: React.FC<DatesSectionProps> = ({ editedFields, onFieldChange, mode = 'bankruptcy' }) => {
  const isMortgage = mode === 'mortgage';
  return (
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Даты и сроки
                </Typography>
                <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{isMortgage ? 'Дата принятия решения:' : 'Дата принятия определения:'}</Typography>
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

                {isMortgage && (
                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата извещения:</Typography>
                  <TextField
                    fullWidth
                        type="date"
                        value={editedFields.noticeDate ?? ''}
                        onChange={(e) => onFieldChange('noticeDate', clampNativeDate(e.target.value))}
                    size="small"
                    margin="dense"
                        InputLabelProps={{
                          shrink: true,
                        }}
                  />
                    </Box>
                </Grid>
                )}

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

                {/* «Установка срока на предоставление возражений» — показываем в
                    обоих режимах. Остальные банкротные сроки (рассмотрение / без
                    движения) в ипотеке не применимы, скрываем. */}
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
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <DeadlineDatePicker
                                value={editedFields.objectionsDeadline18 ?? ''}
                                onPick={(v) => onFieldChange('objectionsDeadline18', v)}
                              />
                            </InputAdornment>
                          ),
                        }}
                  />
                    </Box>
                </Grid>

                {!isMortgage && (
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
                )}

                {!isMortgage && (
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
                )}

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
