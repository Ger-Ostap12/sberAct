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
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import { EntityType, CollateralOption, DebtorStatus, SelectedAct } from '../../../types';

interface ActSelectionSectionProps {
  entityType: EntityType | null;
  setEntityType: (v: EntityType | null) => void;
  collateralOption: CollateralOption | null;
  collateralKinds: { realEstate: boolean; auto: boolean; other: boolean };
  setCollateralKinds: React.Dispatch<React.SetStateAction<{ realEstate: boolean; auto: boolean; other: boolean }>>;
  debtorStatus: DebtorStatus | null;
  toggleDebtorStatus: (status: DebtorStatus) => void;
  selectedActs: SelectedAct[];
  toggleActSelection: (actId: string) => void;
  updateActAdditionalFields: (actId: string, field: 'reason' | 'forParties' | 'courtRequests', value: string) => void;
  updateActRtkVariant: (actId: string, variant: 'realization' | 'restructuring' | 'competition' | 'observation' | 'registry') => void;
  recommendationsApplied: boolean;
  recommendedActs?: { entityType?: string; collateralOption?: string; recommendedActIds?: string[] } | undefined;
}

const ActSelectionSection: React.FC<ActSelectionSectionProps> = ({
  entityType,
  setEntityType,
  collateralOption,
  collateralKinds,
  setCollateralKinds,
  debtorStatus,
  toggleDebtorStatus,
  selectedActs,
  toggleActSelection,
  updateActAdditionalFields,
  updateActRtkVariant,
  recommendationsApplied,
  recommendedActs,
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

            {/* Статус должника (банкротство) — влияет на финальный СА.
                «Умерший» доступен только для Физ.лица, «Отсутствующий»/«Ликвидируемый» —
                только для Юр.лица. Выбор взаимоисключающий → круглые radio;
                повторный клик снимает выбор. */}
            {(entityType === 'individual' || entityType === 'legal') && (
            <Box sx={{ mb: 4 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', mb: 1 }}>
                Статус должника
              </Typography>
              <RadioGroup row value={debtorStatus || ''}>
                {entityType === 'legal' && (
                  <FormControlLabel
                    value="absent"
                    control={<Radio onClick={() => toggleDebtorStatus('absent')} />}
                    label="Отсутствующий"
                  />
                )}
                {entityType === 'legal' && (
                  <FormControlLabel
                    value="liquidation"
                    control={<Radio onClick={() => toggleDebtorStatus('liquidation')} />}
                    label="Ликвидируемый"
                  />
                )}
                {entityType === 'individual' && (
                  <FormControlLabel
                    value="deceased"
                    control={<Radio onClick={() => toggleDebtorStatus('deceased')} />}
                    label="Умерший"
                  />
                )}
              </RadioGroup>
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
                            {act.selected && act.additionalFields && (
                              <Box sx={{ ml: 4, mt: 1 }}>
                                {/* Поля "Причина" и "Для сторон" для акта "Определение Б/Д иное" */}
                                {act.additionalFields.reason !== undefined && act.id === 'acceptance_no_motion_other' && (
                                  <>
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={3}
                                      label="Причина"
                                      value={act.additionalFields.reason || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'reason', e.target.value)}
                                      sx={{ mb: 1 }}
                                    />
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={3}
                                      label="Для сторон"
                                      value={act.additionalFields.forParties || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'forParties', e.target.value)}
                                      sx={{ mb: 1 }}
                                    />
                                  </>
                                )}
                                {/* Поле "Запросы суда" для актов "Определение о принятии" и "Принятие после Б/Д" */}
                                {act.additionalFields.courtRequests !== undefined && (
                                  <TextField
                                    fullWidth
                                    multiline
                                    rows={4}
                                    label="Запросы суда"
                                    value={act.additionalFields.courtRequests || ''}
                                    onChange={(e) => updateActAdditionalFields(act.id, 'courtRequests', e.target.value)}
                                  />
                                )}
                              </Box>
                            )}
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
                            {act.selected && act.additionalFields && (
                              <Box sx={{ ml: 4, mt: 1 }}>
                                {/* Поля "Причина" и "Для сторон" для акта "Возврат" */}
                                {act.additionalFields.reason !== undefined && act.id === 'intermediate_return' && (
                                  <>
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={3}
                                      label="Причина"
                                      value={act.additionalFields.reason || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'reason', e.target.value)}
                                      sx={{ mb: 1 }}
                                    />
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={3}
                                      label="Для сторон"
                                      value={act.additionalFields.forParties || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'forParties', e.target.value)}
                                    />
                                  </>
                                )}
                                {/* Поля "Причина", "Для сторон" и "Запросы суда" для акта "Отложение" */}
                                {act.additionalFields.reason !== undefined && act.id === 'intermediate_postponement' && (
                                  <>
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={3}
                                      label="Причина"
                                      value={act.additionalFields.reason || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'reason', e.target.value)}
                                      sx={{ mb: 1 }}
                                    />
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={3}
                                      label="Для сторон"
                                      value={act.additionalFields.forParties || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'forParties', e.target.value)}
                                      sx={{ mb: 1 }}
                                    />
                                    <TextField
                                      fullWidth
                                      multiline
                                      rows={4}
                                      label="Запросы суда"
                                      value={act.additionalFields.courtRequests || ''}
                                      onChange={(e) => updateActAdditionalFields(act.id, 'courtRequests', e.target.value)}
                                    />
                                  </>
                                )}
                              </Box>
                            )}
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
                  </AccordionDetails>
                </Accordion>
              </Grid>
            </Grid>
          </Card>
  );
};

export default ActSelectionSection;
