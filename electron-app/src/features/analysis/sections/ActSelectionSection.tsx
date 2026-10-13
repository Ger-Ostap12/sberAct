// Секция выбора судебных актов, перенесена из DocumentAnalysis 1:1.
import React from 'react';
import {
  Alert,
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
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { ToggleButton, ToggleButtonGroup } from '@mui/material';
import { EntityType, CollateralOption, ApplicationKind, DebtorStatus, SelectedAct } from '../../../types';
import { CollateralKinds } from '../lib/collateralSync';
import {
  IntroducedProcedure,
  RTK_VARIANT_LABEL,
  RtkVariant,
  rtkVariantsForEntity,
} from '../lib/finalActs';

interface ActSelectionSectionProps {
  entityType: EntityType | null;
  setEntityType: (v: EntityType | null) => void;
  collateralOption: CollateralOption | null;
  collateralKinds: CollateralKinds;
  /** Галки вида производны от карточек залога — родитель решает, можно ли менять. */
  toggleCollateralKind: (kind: keyof CollateralKinds, checked: boolean) => void;
  selectNoCollateral: () => void;
  collateralNotice: string | null;
  dismissCollateralNotice: () => void;
  /** Вид заявления (ВКЛ в РТК / инициирование) — независимый блок.
   *  'rtk' скрывает поле СРО. */
  applicationKind: ApplicationKind;
  setApplicationKind: (v: ApplicationKind) => void;
  /** Самобанкротство — подвид инициирования, скрывает блок кредитора. */
  selfBankruptcy: boolean;
  setSelfBankruptcy: (v: boolean) => void;
  /** Статус лица (ликвидируемый/отсутствующий ЮЛ, умерший ФЛ) — независимый,
   *  опциональный блок. null = не задан. Совместим с любым видом заявления. */
  debtorStatus: DebtorStatus | null;
  setDebtorStatus: (v: DebtorStatus | null) => void;
  selectedActs: SelectedAct[];
  toggleActSelection: (actId: string) => void;
  /** Больше не используется секцией: поля «Причина»/«Для сторон»/«Запросы суда»
   *  убраны из окон актов. Проп оставлен — родитель по-прежнему им владеет. */
  updateActAdditionalFields?: (actId: string, field: 'reason' | 'forParties' | 'courtRequests', value: string) => void;
  updateActRtkVariant: (actId: string, variant: RtkVariant) => void;
  /** Процедура, введённая судом: по ней подставляется вид акта ВКЛ в РТК. */
  introducedProcedure?: IntroducedProcedure | undefined;
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
  toggleCollateralKind,
  selectNoCollateral,
  collateralNotice,
  dismissCollateralNotice,
  applicationKind,
  setApplicationKind,
  selfBankruptcy,
  setSelfBankruptcy,
  debtorStatus,
  setDebtorStatus,
  selectedActs,
  toggleActSelection,
  updateActRtkVariant,
  introducedProcedure,
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

            {/* Вид заявления — две взаимоисключающие основы: ВКЛ в РТК и
                Инициирование. Самобанкротство — подвид инициирования, поэтому
                чекбокс, а не третья кнопка: оно скрывает блок кредитора, но
                заявление остаётся инициирующим. Статус лица — отдельный блок
                ниже, они совместимы. */}
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
                <FormControlLabel value="initiation" control={<Radio />} label="Инициирование" />
              </RadioGroup>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={selfBankruptcy}
                    disabled={applicationKind === 'rtk'}
                    onChange={(e) => setSelfBankruptcy(e.target.checked)}
                  />
                }
                label="Самобанкрот"
              />
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
                    onChange={(e) => toggleCollateralKind('realEstate', e.target.checked)} />}
                  label="Залог недвижимость"
                />
                <FormControlLabel
                  control={<Checkbox checked={collateralKinds.auto}
                    onChange={(e) => toggleCollateralKind('auto', e.target.checked)} />}
                  label="Залог ТС"
                />
                <FormControlLabel
                  control={<Checkbox checked={collateralKinds.other}
                    onChange={(e) => toggleCollateralKind('other', e.target.checked)} />}
                  label="Залог иное"
                />
                <FormControlLabel
                  control={<Checkbox checked={!collateralKinds.realEstate && !collateralKinds.auto && !collateralKinds.other}
                    onChange={(e) => { if (e.target.checked) selectNoCollateral(); }} />}
                  label="Без залога"
                />
              </Box>
              {collateralNotice && (
                <Alert severity="warning" sx={{ mt: 1 }} onClose={dismissCollateralNotice}>
                  {collateralNotice}
                </Alert>
              )}
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
                        .map(act => (
                          <Box key={act.id} sx={{ mb: 2 }}>
                            <FormControlLabel
                              control={
                                <Checkbox
                                  checked={act.selected}
                                  onChange={() => toggleActSelection(act.id)}
                                />
                              }
                              label={act.name}
                            />
                          </Box>
                        ))}
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
                        .map(act => (
                          <Box key={act.id} sx={{ mb: 2 }}>
                            <FormControlLabel
                              control={
                                <Checkbox
                                  checked={act.selected}
                                  onChange={() => toggleActSelection(act.id)}
                                />
                              }
                              label={act.name}
                            />
                          </Box>
                        ))}
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
                      {applicationKind === 'rtk' ? (
                        // Включение в РТК: виды акта взаимоисключающие, набор
                        // гейтится типом лица, «За реестр» доступен обоим.
                        rtkVariantsForEntity(entityType).map(variant => {
                          const act = selectedActs.find(a => a.id === 'final_rtk_inclusion');
                          const выбран = act?.rtkVariant === variant;
                          const рекомендован = act?.selected && !!introducedProcedure
                            && variant === introducedProcedure;
                          return (
                            <Box key={variant} sx={{ mb: 1 }}>
                              <FormControlLabel
                                control={
                                  <Checkbox
                                    checked={!!выбран}
                                    onChange={() => updateActRtkVariant('final_rtk_inclusion', variant)}
                                  />
                                }
                                label={
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <span>{RTK_VARIANT_LABEL[variant]}</span>
                                    {рекомендован && (
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
                            </Box>
                          );
                        })
                      ) : (
                        // Инициирование: процедурные акты, акта ВКЛ в РТК здесь нет.
                        selectedActs
                          .filter(act => act.category === 'final' && act.id !== 'final_rtk_inclusion')
                          .map(act => {
                            const isRecommended = recommendationsApplied &&
                              recommendedActs?.recommendedActIds?.includes(act.id);
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
                              </Box>
                            );
                          })
                      )}
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
                        label="Резолютивная часть"
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
