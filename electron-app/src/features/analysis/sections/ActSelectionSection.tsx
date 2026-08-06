// Секция выбора судебных актов, перенесена из DocumentAnalysis 1:1.
import React from 'react';
import {
  Card,
  Typography,
  Box,
  Chip,
  RadioGroup,
  FormControlLabel,
  Radio,
  Checkbox,
  Grid,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import { ToggleButton, ToggleButtonGroup } from '@mui/material';
import { EntityType, CollateralOption, ApplicationKind, DebtorStatus, SelectedAct } from '../../../types';

interface ActSelectionSectionProps {
  entityType: EntityType | null;
  setEntityType: (v: EntityType | null) => void;
  collateralOption: CollateralOption | null;
  collateralKinds: { realEstate: boolean; auto: boolean; other: boolean };
  setCollateralKinds: React.Dispatch<React.SetStateAction<{ realEstate: boolean; auto: boolean; other: boolean }>>;
  /** Вид заявления (ВКЛ в РТК / инициирование / самобанкрот) — независимый блок.
   *  'rtk' скрывает поле СРО; 'self' скрывает блок кредитора. */
  applicationKind: ApplicationKind;
  setApplicationKind: (v: ApplicationKind) => void;
  /** Статус лица (ликвидируемый/отсутствующий ЮЛ, умерший ФЛ) — независимый,
   *  опциональный блок. null = не задан. Совместим с любым видом заявления. */
  debtorStatus: DebtorStatus | null;
  setDebtorStatus: (v: DebtorStatus | null) => void;
  selectedActs: SelectedAct[];
  toggleActSelection: (actId: string) => void;
  /** Больше не используется секцией: поля «Причина»/«Для сторон»/«Запросы суда»
   *  убраны из окон актов. Проп оставлен — родитель по-прежнему им владеет. */
  updateActAdditionalFields?: (actId: string, field: 'reason' | 'forParties' | 'courtRequests', value: string) => void;
  updateActRtkVariant: (actId: string, variant: 'realization' | 'restructuring' | 'competition' | 'observation' | 'registry') => void;
  recommendationsApplied: boolean;
  recommendedActs?: { entityType?: string; collateralOption?: string; recommendedActIds?: string[] } | undefined;
  /** Чекбокс «Короткий текст»: доп. генерация резолютивки основной процедуры. */
  shortText: boolean;
  setShortText: (v: boolean) => void;
}

const ActSelectionSection: React.FC<ActSelectionSectionProps> = ({
  entityType,
  setEntityType,
  collateralOption,
  collateralKinds,
  setCollateralKinds,
  applicationKind,
  setApplicationKind,
  debtorStatus,
  setDebtorStatus,
  selectedActs,
  toggleActSelection,
  updateActRtkVariant,
  recommendationsApplied,
  recommendedActs,
  shortText,
  setShortText,
}) => {
  return (
          <Card sx={{ p: 3 }}>
            <Typography variant="h5" gutterBottom sx={{ mb: 3, color: 'primary.main', fontWeight: 'bold' }}>
              Выбор типа судебного акта
                </Typography>

            {/* Выбор лица */}
            <Box sx={{ mb: 4 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', mb: 0 }}>
                  Выбор лица
                </Typography>
                {recommendationsApplied && recommendedActs?.entityType && (
                  <Chip
                    label="Автоматически определено"
                    size="small"
                    color="info"
                    sx={{ fontSize: '0.7rem' }}
                  />
                )}
              </Box>
              <RadioGroup
                row
                value={entityType || ''}
                onChange={(e) => setEntityType(e.target.value as EntityType)}
              >
                <FormControlLabel value="individual" control={<Radio />} label="Физ.лицо" />
                <FormControlLabel value="legal" control={<Radio />} label="Юр.лицо" />
                <FormControlLabel value="ip" control={<Radio />} label="ИП" />
                <FormControlLabel value="kfh" control={<Radio />} label="Глава КФХ" />
              </RadioGroup>
              </Box>

            {/* Вид заявления — независимый взаимоисключающий блок: ВКЛ в РТК /
                Инициирование / Самобанкрот. «Включение в РТК» скрывает поле СРО
                (управляющий уже утверждён); «Самобанкрот» скрывает блок кредитора.
                Драйвер ВКЛ в РТК — акт final_rtk_inclusion (синхронен с чекбоксом в
                «3. Финальные СА»). Статус лица — отдельный блок ниже, они СОВМЕСТИМЫ
                (можно выбрать, напр., «Инициирование» + «Ликвидируемый»). */}
            <Box sx={{ mb: 4 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', mb: 0 }}>
                  Вид заявления
                </Typography>
                {recommendationsApplied && recommendedActs?.entityType && (
                  <Chip
                    label="Автоматически определено"
                    size="small"
                    color="info"
                    sx={{ fontSize: '0.7rem' }}
                  />
                )}
              </Box>
              <RadioGroup
                row
                value={applicationKind}
                onChange={(e) => setApplicationKind(e.target.value as ApplicationKind)}
              >
                <FormControlLabel value="rtk" control={<Radio />} label="Включение в РТК" />
                <FormControlLabel value="other" control={<Radio />} label="Инициирование" />
                <FormControlLabel value="self" control={<Radio />} label="Самобанкрот" />
              </RadioGroup>
            </Box>

            {/* Статус лица — независимый, опциональный, взаимоисключающий блок:
                Ликвидируемый/Отсутствующий (ЮЛ) или Умерший (ФЛ). Совместим с любым
                видом заявления. ToggleButtonGroup exclusive: повторный клик по активной
                кнопке снимает выбор (null). Набор гейтится по типу лица. Влияет на
                рекомендацию финального СА (см. useEffect по debtorStatus). */}
            {(entityType === 'legal' || entityType === 'individual') && (
            <Box sx={{ mb: 4 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', mb: 1 }}>
                Статус лица
              </Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={debtorStatus}
                onChange={(_e, v) => setDebtorStatus((v as DebtorStatus | null) ?? null)}
                sx={{
                  // Акцент выбранной кнопки: залитый primary + жирный белый текст,
                  // иначе активное состояние почти не отличалось от неактивного.
                  '& .MuiToggleButton-root': {
                    px: 2,
                    fontWeight: 600,
                    textTransform: 'none',
                    border: '1px solid',
                    borderColor: 'primary.main',
                    color: 'primary.main',
                  },
                  '& .MuiToggleButton-root.Mui-selected': {
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    '&:hover': { bgcolor: 'primary.dark' },
                  },
                }}
              >
                {entityType === 'legal' && (
                  <ToggleButton value="liquidation">Ликвидируемый</ToggleButton>
                )}
                {entityType === 'legal' && (
                  <ToggleButton value="absent">Отсутствующий</ToggleButton>
                )}
                {entityType === 'individual' && (
                  <ToggleButton value="deceased">Умерший</ToggleButton>
                )}
              </ToggleButtonGroup>
            </Box>
            )}

            {/* Выбор залога */}
            <Box sx={{ mb: 4 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', mb: 0 }}>
                  Выбор залога
                </Typography>
                {recommendationsApplied && recommendedActs?.collateralOption && (
                  <Chip
                    label="Автоматически определено"
                    size="small"
                    color="info"
                    sx={{ fontSize: '0.7rem' }}
                  />
                )}
              </Box>
              {/* Можно выбрать несколько видов залога одновременно. */}
              <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 2 }}>
                <FormControlLabel
                  control={<Checkbox checked={collateralKinds.realEstate}
                    onChange={(e) => setCollateralKinds(prev => ({ ...prev, realEstate: e.target.checked }))} />}
                  label="Залог недвижимость"
                />
                <FormControlLabel
                  control={<Checkbox checked={collateralKinds.auto}
                    onChange={(e) => setCollateralKinds(prev => ({ ...prev, auto: e.target.checked }))} />}
                  label="Залог ТС"
                />
                <FormControlLabel
                  control={<Checkbox checked={collateralKinds.other}
                    onChange={(e) => setCollateralKinds(prev => ({ ...prev, other: e.target.checked }))} />}
                  label="Залог иное"
                />
                <FormControlLabel
                  control={<Checkbox checked={!collateralKinds.realEstate && !collateralKinds.auto && !collateralKinds.other}
                    onChange={(e) => { if (e.target.checked) setCollateralKinds({ realEstate: false, auto: false, other: false }); }} />}
                  label="Без залога"
                />
              </Box>
            </Box>

            {/* Три окна с актами */}
            <Grid container spacing={2}>
              {/* 1. Принятие */}
              <Grid item xs={12} md={4}>
                <Accordion defaultExpanded>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                      1. Принятие
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
              <Box>
                      {selectedActs
                        .filter(act => act.category === 'acceptance')
                        .map(act => {
                          const isRecommended = recommendationsApplied &&
                            recommendedActs?.recommendedActIds?.includes(act.id);
                          return (
                          <Box key={act.id} sx={{ mb: 2 }}>
                            <FormControlLabel
                              control={
                                <Checkbox
                                  checked={act.selected}
                                  onChange={() => toggleActSelection(act.id)}
                                />
                              }
                              label={
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <span>{act.name}</span>
                                  {isRecommended && (
                                    <Chip
                                      label="Рекомендуется"
                                      size="small"
                                      color="success"
                                      sx={{ fontSize: '0.65rem', height: '18px' }}
                                    />
                                  )}
                                </Box>
                              }
                            />
                            {/* Поля «Причина», «Для сторон», «Запросы суда» убраны
                                по требованию Андрея: окна выбора актов остаются
                                списком чекбоксов. Сами поля в данных живут
                                (additionalFields), пустые маркеры зачищаются при
                                генерации. */}
                          </Box>
                        );
                        })}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </Grid>

              {/* 2. Промежуточные */}
              <Grid item xs={12} md={4}>
                <Accordion defaultExpanded>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                      2. Промежуточные
                </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box>
                      {selectedActs
                        .filter(act => act.category === 'intermediate')
                        .map(act => {
                          const isRecommended = recommendationsApplied &&
                            recommendedActs?.recommendedActIds?.includes(act.id);
                          return (
                          <Box key={act.id} sx={{ mb: 2 }}>
                            <FormControlLabel
                              control={
                                <Checkbox
                                  checked={act.selected}
                                  onChange={() => toggleActSelection(act.id)}
                                />
                              }
                              label={
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <span>{act.name}</span>
                                  {isRecommended && (
                <Chip
                                      label="Рекомендуется"
                  size="small"
                                      color="success"
                                      sx={{ fontSize: '0.65rem', height: '18px' }}
                />
                                  )}
              </Box>
                              }
                            />
                            {/* Поля «Причина», «Для сторон», «Запросы суда» убраны
                                по требованию Андрея (см. окно «1. Принятие»). */}
                          </Box>
                        );
                        })}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </Grid>

              {/* 3. Финальные СА */}
              <Grid item xs={12} md={4}>
                <Accordion defaultExpanded>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                      3. Финальные СА
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box>
                      {selectedActs
                        .filter(act => act.category === 'final')
                        .map(act => {
                          const isRecommended = recommendationsApplied &&
                            recommendedActs?.recommendedActIds?.includes(act.id);
                          const isRtkAct = act.id === 'final_rtk_inclusion';

                          return (
                            <Box key={act.id} sx={{ mb: 1 }}>
                              <FormControlLabel
                                control={
                                  <Checkbox
                                    checked={act.selected}
                                    onChange={() => toggleActSelection(act.id)}
                                  />
                                }
                                label={
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <span>{act.name}</span>
                                    {isRecommended && (
                                      <Chip
                                        label="Рекомендуется"
                                        size="small"
                                        color="success"
                                        sx={{ fontSize: '0.65rem', height: '18px' }}
                                      />
                                    )}
                                  </Box>
                                }
                              />

                              {/* Дополнительный выбор варианта для "Определение ВКЛ в РТК" */}
                              {isRtkAct && act.selected && (
                                <Box sx={{ mt: 1, ml: 4 }}>
                                  <FormControl fullWidth size="small">
                                    <InputLabel id={`${act.id}-variant-label`}>
                                      Выберите вид акта
                                    </InputLabel>
                                    <Select
                                      labelId={`${act.id}-variant-label`}
                                      label="Выберите вид акта"
                                      value={act.rtkVariant || ''}
                                      onChange={(e) =>
                                        updateActRtkVariant(
                                          act.id,
                                          e.target.value as
                                            'realization' | 'restructuring' | 'competition' | 'observation' | 'registry'
                                        )
                                      }
                                    >
                                      <MenuItem value="realization">
                                        Определение включение в РТК реализация
                                      </MenuItem>
                                      <MenuItem value="restructuring">
                                        Определение включение в РТК реструктуризация
                                      </MenuItem>
                                      <MenuItem value="competition">
                                        Определение включение в РТК конкурсное
                                      </MenuItem>
                                      <MenuItem value="observation">
                                        Определение включение в РТК наблюдение
                                      </MenuItem>
                                      <MenuItem value="registry">
                                        Определение ВКЛ в РТК "зареестр"
                                      </MenuItem>
                                    </Select>
                                  </FormControl>
                                </Box>
                              )}
                            </Box>
                          );
                        })}
                    </Box>
                    {/* Короткий текст — доп. генерация резолютивки основной процедуры
                        к выбранным финальным актам. Стоит здесь, а не отдельным блоком
                        сверху: относится ровно к этому окну (решение суда пишется в
                        полном или коротком варианте). Если резолютивки нет (конкурсное,
                        наблюдение с залогом) — при генерации придёт предупреждение
                        «нет шаблона». */}
                    <Box sx={{ mt: 1, pt: 1, borderTop: 1, borderColor: 'divider' }}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={shortText}
                            onChange={(e) => setShortText(e.target.checked)}
                          />
                        }
                        label="Короткий текст"
                      />
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </Grid>
            </Grid>
          </Card>
  );
};

export default ActSelectionSection;
