import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Grid,
  Chip,
  Alert,
  CircularProgress,
  Divider
} from '@mui/material';
import { ArrowBack as BackIcon, CheckCircle as CheckIcon } from '@mui/icons-material';
import { DocumentData, ExtractedData, Obligation, Collateral, CollateralType, EntityType, CollateralOption, DebtorStatus, SelectedAct, ThirdParty, Debtor } from '../../types';
import { BANK_DATA } from '../../shared/constants/banks';
import { extractCollateralData } from '../../shared/lib/collateral';
import { buildSubmitData } from './lib/buildSubmitData';
import ObligationsSection from './sections/ObligationsSection';
import CollateralSection from './sections/CollateralSection';
import CourtSection from './sections/CourtSection';
import DatesSection from './sections/DatesSection';
import ManagerSection from './sections/ManagerSection';
import ThirdPartiesSection from './sections/ThirdPartiesSection';
import DebtorsSection from './sections/DebtorsSection';
import CreditorSection from './sections/CreditorSection';
import FinancesSection from './sections/FinancesSection';
import PriorCollectionSection from './sections/PriorCollectionSection';
import ActSelectionSection from './sections/ActSelectionSection';

interface DocumentAnalysisProps {
  documentData: DocumentData;
  extractedData?: ExtractedData;
  onAnalysisComplete: (data: ExtractedData) => void;
  onBack: () => void;
}

const DocumentAnalysis: React.FC<DocumentAnalysisProps> = ({
  documentData,
  extractedData: propExtractedData,
  onAnalysisComplete,
  onBack
}) => {
  const [isAnalyzing, setIsAnalyzing] = useState(true);
  const [analysisResult, setAnalysisResult] = useState<ExtractedData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editedFields, setEditedFields] = useState<Record<string, string>>({});

  // Состояние для выбора актов
  const [entityType, setEntityType] = useState<EntityType | null>(null);
  const [collateralOption, setCollateralOption] = useState<CollateralOption | null>(null);
  // Виды залога для блока «Выбор залога» (можно несколько: недвижка, транспорт, иное).
  const [collateralKinds, setCollateralKinds] = useState<{ realEstate: boolean; auto: boolean; other: boolean }>({ realEstate: false, auto: false, other: false });
  const [selectedActs, setSelectedActs] = useState<SelectedAct[]>([]);
  const [recommendationsApplied, setRecommendationsApplied] = useState(false);
  // Статус должника (банкротство): отсутствующий / ликвидируемый / умерший.
  // Взаимоисключающие: выбор одного снимает остальные.
  const [debtorStatus, setDebtorStatus] = useState<DebtorStatus | null>(null);

  const toggleDebtorStatus = (status: DebtorStatus) => {
    setDebtorStatus(prev => (prev === status ? null : status));
  };

  // Статус должника влияет на рекомендацию финального СА:
  // отсутствующий/ликвидируемый ЮЛ → «Решение конкурсное»; умерший ФЛ → «Решение реализация».
  useEffect(() => {
    if (!debtorStatus) return;
    const finalByStatus: Record<DebtorStatus, string> = {
      absent: 'final_competition',
      liquidation: 'final_competition',
      deceased: 'final_realization',
    };
    const targetFinal = finalByStatus[debtorStatus];
    setSelectedActs(prev => prev.map(act =>
      act.category === 'final' ? { ...act, selected: act.id === targetFinal } : act
    ));
    // Статус подразумевает тип лица: отсутствующий/ликвидируемый — ЮЛ, умерший — ФЛ.
    setEntityType(debtorStatus === 'deceased' ? 'individual' : 'legal');
  }, [debtorStatus]);

  // Если тип лица сменили на несовместимый со статусом — сбрасываем статус
  // (умерший только у ФЛ; отсутствующий/ликвидируемый только у ЮЛ).
  useEffect(() => {
    if (!debtorStatus) return;
    if (debtorStatus === 'deceased' && entityType !== 'individual') setDebtorStatus(null);
    if ((debtorStatus === 'absent' || debtorStatus === 'liquidation') && entityType !== 'legal') setDebtorStatus(null);
  }, [entityType]);

  // Сводим выбранные виды залога к одному значению collateralOption (для генерации):
  // ничего → no_collateral; только транспорт → collateral_auto; иначе → collateral.
  useEffect(() => {
    const { realEstate, auto, other } = collateralKinds;
    let opt: CollateralOption;
    if (!realEstate && !auto && !other) opt = 'no_collateral';
    else if (auto && !realEstate && !other) opt = 'collateral_auto';
    else opt = 'collateral';
    setCollateralOption(opt);
  }, [collateralKinds]);

  // Инициализация списка актов
  useEffect(() => {
    const allActs: SelectedAct[] = [
      // Финальные СА
      { id: 'final_realization', name: 'Решение реализация', category: 'final', selected: false },
      { id: 'final_competition', name: 'Решение конкурсное', category: 'final', selected: false },
      { id: 'final_restructuring', name: 'Определение реструктуризация', category: 'final', selected: false },
      { id: 'final_observation', name: 'Определение Наблюдение', category: 'final', selected: false },
      { id: 'final_rtk_inclusion', name: 'Определение ВКЛ в РТК', category: 'final', selected: false },
      // Принятие
      { id: 'acceptance_definition', name: 'Определение о принятии', category: 'acceptance', selected: false, additionalFields: { courtRequests: '' } },
      { id: 'acceptance_no_motion_no_duty', name: 'Определение Б/Д нет ГП', category: 'acceptance', selected: false },
      { id: 'acceptance_no_motion_no_duty_collateral', name: 'Определение Б/Д нет ГП залог', category: 'acceptance', selected: false },
      { id: 'acceptance_no_motion_other', name: 'Определение Б/Д иное', category: 'acceptance', selected: false, additionalFields: { reason: '', forParties: '' } },
      { id: 'acceptance_after_no_motion', name: 'Принятие после Б/Д', category: 'acceptance', selected: false, additionalFields: { courtRequests: '' } },
      // Промежуточные
      { id: 'intermediate_postponement', name: 'Отложение', category: 'intermediate', selected: false, additionalFields: { reason: '', forParties: '', courtRequests: '' } },
      { id: 'intermediate_return', name: 'Возврат', category: 'intermediate', selected: false, additionalFields: { reason: '', forParties: '' } },
      { id: 'intermediate_extend_no_motion', name: 'Продление Б/Д', category: 'intermediate', selected: false },
      { id: 'intermediate_extend_simplified', name: 'Продление упрощёнка', category: 'intermediate', selected: false },
      { id: 'intermediate_simplified_to_main', name: 'Переход из упрощёнки в основное производство', category: 'intermediate', selected: false },
    ];
    setSelectedActs(allActs);
  }, []);

  // Применяем рекомендации после инициализации актов и получения данных
  useEffect(() => {
    if (selectedActs.length > 0 && analysisResult && !recommendationsApplied) {
      const recommendedActs = (analysisResult as any).recommendedActs;
      if (recommendedActs) {

        // Устанавливаем рекомендуемый тип лица
        if (recommendedActs.entityType) {
          setEntityType(recommendedActs.entityType as EntityType);
        }

        // Устанавливаем рекомендуемый тип залога
        if (recommendedActs.collateralOption) {
          setCollateralOption(recommendedActs.collateralOption as CollateralOption);
        }

        // Авто-статус должника: умерший — по процедуре; конкурсное (отсутствующий/
        // ликвидируемый) оставляем на ручной выбор (по тексту не различить).
        const procType = (analysisResult.fields as any)?.procedureType
          || (analysisResult.fields as any)?.procedureTypeRaw || '';
        if (String(procType).toLowerCase().includes('умер') || String(procType).toLowerCase() === 'deceased') {
          setDebtorStatus('deceased');
        }

        // Устанавливаем рекомендуемые акты
        if (recommendedActs.recommendedActIds && recommendedActs.recommendedActIds.length > 0) {
          setSelectedActs(prevActs => {
            const updatedActs = prevActs.map(act => ({
              ...act,
              selected: recommendedActs.recommendedActIds!.includes(act.id)
            }));
            return updatedActs;
          });
        }

        setRecommendationsApplied(true);
      }
    }
  }, [selectedActs.length, analysisResult, recommendationsApplied]);

  // Таймаут для предотвращения бесконечной загрузки
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (isAnalyzing) {
        setIsAnalyzing(false);
        setError('Превышено время ожидания анализа документа');
      }
    }, 25000); // 25 секунд

    return () => clearTimeout(timeout);
  }, [isAnalyzing]);

  useEffect(() => {
    // Анализ уже выполнен в DocumentUpload, данные переданы через props
    if (documentData) {

      if (propExtractedData) {
        // Используем данные, переданные через props

        // Устанавливаем полный analysisResult с obligations
        const defaultCollateral = (): Collateral => ({
          id: `collateral-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          collateralType: 'real_estate',
          objectName: '',
          collateralValue: '',
          cadastralNumber: '',
          address: '',
          vin: '',
          brandModel: '',
          otherDescription: ''
        });

        // Проверяем, есть ли данные о залоге в извлеченных полях
        const mortgageCollateralDescription = propExtractedData.fields?.mortgageCollateralDescription1221;
        let initialCollaterals: Collateral[] = [];

        const existingCollaterals = (propExtractedData as ExtractedData).collaterals;
        if (existingCollaterals && existingCollaterals.length > 0) {
          // Если уже есть массив collaterals из backend (может содержать несколько предметов залога), обрабатываем каждый
          initialCollaterals = existingCollaterals.map((collateral: Collateral, idx: number) => {
            // Используем описание из collateral.description или otherDescription
            const itemDescription = (collateral as any).description || collateral.otherDescription || '';

            // Если у залога есть описание, определяем тип и извлекаем данные
            if (itemDescription && itemDescription.trim()) {
              const desc = itemDescription.toLowerCase();
              const detectedType = (() => {
                if (desc.includes('автомобил') || desc.includes('vin') || desc.includes('марка') || desc.includes('модель')) {
                  return 'auto';
                } else if (desc.includes('недвижим') || desc.includes('квартир') || desc.includes('дом') || desc.includes('земел') || desc.includes('кадастр')) {
                  return 'real_estate';
                } else {
                  return 'other';
                }
              })() as CollateralType;

              // Извлекаем адрес и кадастровый номер из описания конкретного предмета залога
              const extractedData = extractCollateralData(itemDescription);

              const finalType = (collateral.collateralType || detectedType) as CollateralType;
              const isOther = finalType === 'other';
              return {
                ...collateral,
                id: collateral.id || `collateral-${idx}`,
                collateralType: finalType,
                // Наименование — из бэкенда (вид объекта). Для «иное» оставляем пустым.
                objectName: collateral.objectName || '',
                // Описание показываем только для «иное»; для недвижимости/авто его нет.
                otherDescription: isOther ? (collateral.otherDescription || itemDescription) : '',
                // Адрес/кадастр — приоритет данным бэкенда (полные), затем фронт-извлечение.
                address: collateral.address || extractedData.address || '',
                cadastralNumber: collateral.cadastralNumber || extractedData.cadastralNumber || ''
              };
            }

            // Если описания нет, возвращаем залог как есть
            return {
              ...collateral,
              id: collateral.id || `collateral-${idx}`
            };
          });
        } else if (mortgageCollateralDescription) {
          // Если нет массива collaterals, но есть описание предмета залога, создаем один залог с этим описанием
          // (это fallback для старых данных или случаев, когда backend не разбил на несколько предметов)
          const desc = mortgageCollateralDescription.toLowerCase();
          const detectedType = (() => {
            if (desc.includes('автомобил') || desc.includes('vin') || desc.includes('марка') || desc.includes('модель')) {
              return 'auto';
            } else if (desc.includes('недвижим') || desc.includes('квартир') || desc.includes('дом') || desc.includes('земел') || desc.includes('кадастр')) {
              return 'real_estate';
            } else {
              return 'other';
            }
          })() as CollateralType;

          // Извлекаем адрес и кадастровый номер из описания
          const extractedData = extractCollateralData(mortgageCollateralDescription);

          const collateral: Collateral = {
            ...defaultCollateral(),
            collateralType: detectedType,
            objectName: detectedType !== 'other' ? (mortgageCollateralDescription.length < 200 ? mortgageCollateralDescription : mortgageCollateralDescription.substring(0, 200)) : '',
            otherDescription: mortgageCollateralDescription,
            address: extractedData.address || '',
            cadastralNumber: extractedData.cadastralNumber || ''
          };
          initialCollaterals = [collateral];
        } else {
          // Залога нет — блок остаётся пустым (без записей).
          // Пользователь может добавить залог вручную кнопкой «Добавить залог».
          initialCollaterals = [];
        }

        // Виды залога для блока «Выбор залога» — из реальных типов предметов залога.
        // Может быть выбрано несколько (например, недвижимость И транспорт одновременно).
        const hasRealEstate = initialCollaterals.some(c => c.collateralType === 'real_estate');
        const hasAuto = initialCollaterals.some(c => c.collateralType === 'auto');
        const hasOther = initialCollaterals.some(c => c.collateralType === 'other');
        setCollateralKinds({ realEstate: hasRealEstate, auto: hasAuto, other: hasOther });

        // Инициализируем третьих лиц из полей или создаем пустой массив
        let initialThirdParties: ThirdParty[] = [];
        if (propExtractedData.thirdParties && propExtractedData.thirdParties.length > 0) {
          initialThirdParties = propExtractedData.thirdParties.map((tp, i) => ({
            ...tp,
            id: tp.id || `thirdParty-${Date.now()}-${i}-${Math.random().toString(36).slice(2)}`
          }));
        } else if (propExtractedData.fields?.thirdPartyName) {
          // Если есть данные в старом формате (поля), создаем один объект третьего лица
          initialThirdParties = [{
            id: `thirdParty-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            name: propExtractedData.fields.thirdPartyName || '',
            birthDate: propExtractedData.fields.thirdPartyBirthDate || '',
            address: propExtractedData.fields.thirdPartyAddress || '',
            inn: propExtractedData.fields.thirdPartyInn || '',
            snils: propExtractedData.fields.thirdPartySnils || ''
          }];
        } else {
          // Если нет данных, создаем пустой массив (не создаем пустой объект по умолчанию)
          initialThirdParties = [];
        }

        // Инициализируем должников из массива debtors или из плоских полей (один должник)
        let initialDebtors: Debtor[] = [];
        if (propExtractedData.debtors && propExtractedData.debtors.length > 0) {
          initialDebtors = propExtractedData.debtors.map((d, i) => ({
            ...d,
            id: d.id || `debtor-${Date.now()}-${i}-${Math.random().toString(36).slice(2)}`
          }));
        } else {
          const pf = propExtractedData.fields || {};
          initialDebtors = [{
            id: `debtor-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            name: pf.applicantName || pf.debtorName || '',
            address: pf.applicantAddress || '',
            inn: pf.inn || pf.companyInn || '',
            ogrn: pf.ogrn || '',
            ogrnip: pf.ogrnip || '',
            birthDate: pf.birthDate || '',
            birthPlace: pf.birthPlace || '',
            snils: pf.snils || ''
          }];
        }

        const fullAnalysisResult = {
          ...propExtractedData,
          obligations: propExtractedData.obligations || [],
          collaterals: initialCollaterals,
          thirdParties: initialThirdParties,
          debtors: initialDebtors
        };
        setAnalysisResult(fullAnalysisResult);

        const fields = propExtractedData.fields || {};

        // Устанавливаем статичные значения и фильтруем undefined
        const cleanFields: Record<string, string> = {};
        Object.keys(fields).forEach(key => {
          if (fields[key] !== undefined && fields[key] !== null) {
            cleanFields[key] = String(fields[key]);
          }
        });
        // Название суда берётся из документа (courtName), без хардкода — суд
        // зависит от типа дела (арбитражный / районный / городской / мировой).
        if (!cleanFields.creditorName) {
          cleanFields.creditorName = "ПАО Сбербанк";
        }
        // Синхронизируем связанные поля
        if (cleanFields.debtorName && !cleanFields.applicantName) {
          cleanFields.applicantName = cleanFields.debtorName;
        }
        if (cleanFields.applicantName && !cleanFields.debtorName) {
          cleanFields.debtorName = cleanFields.applicantName;
        }
        if (cleanFields.inn && !cleanFields.companyInn) {
          cleanFields.companyInn = cleanFields.inn;
        }
        if (cleanFields.companyInn && !cleanFields.inn) {
          cleanFields.inn = cleanFields.companyInn;
        }
        if (cleanFields.ogrnip && !cleanFields.ogrn) {
          cleanFields.ogrn = cleanFields.ogrnip;
        }
        // Синхронизируем loanDebt и principalDebt
        if (cleanFields.principalDebt && !cleanFields.loanDebt) {
          cleanFields.loanDebt = cleanFields.principalDebt;
        }
        if (cleanFields.loanDebt && !cleanFields.principalDebt) {
          cleanFields.principalDebt = cleanFields.loanDebt;
        }
        setEditedFields(cleanFields);
        setIsAnalyzing(false);
      } else {
        // Fallback: получаем данные из electronAPI
        const extractedData = (window as any).electronAPI?.getExtractedData();
        if (extractedData) {
          setAnalysisResult(extractedData);


          const fields = extractedData.fields || {};
          const cleanFields: Record<string, string> = {};
          Object.keys(fields).forEach(key => {
            if (fields[key] !== undefined && fields[key] !== null) {
              cleanFields[key] = String(fields[key]);
            }
          });
          // courtName берётся из извлечённых данных (без хардкода)
          // creditorName берется из извлеченных данных (маркер [987])
          setEditedFields(cleanFields);
        } else {
        }
        setIsAnalyzing(false);
      }
    } else {
      setIsAnalyzing(false);
    }
  }, [documentData, propExtractedData]);

  const handleFieldChange = (fieldName: string, value: string) => {
    setEditedFields(prev => ({
      ...prev,
      [fieldName]: value
    }));
  };

  const handleCreditorChange = (value: string) => {
    if (value === 'OTHER') {
      // Если выбран "Другой банк", очищаем автозаполненные данные, но оставляем creditorName пустым для ручного ввода
      setEditedFields(prev => ({
        ...prev,
        creditorName: '',
        creditorAddress: '',
        creditorOgrn: '',
        creditorInn: ''
      }));
    } else if (value && BANK_DATA[value]) {
      // Если выбран банк из списка, автозаполняем данные
      const bankData = BANK_DATA[value];
      setEditedFields(prev => ({
        ...prev,
        creditorName: value,
        creditorAddress: bankData.address,
        creditorOgrn: bankData.ogrn,
        creditorInn: bankData.inn
      }));
    } else {
      // Если выбрано пустое значение, очищаем все поля кредитора
      setEditedFields(prev => ({
        ...prev,
        creditorName: '',
        creditorAddress: '',
        creditorOgrn: '',
        creditorInn: ''
      }));
    }
  };

  const addCollateral = () => {
    if (!analysisResult) return;
    const newCollateral: Collateral = {
      id: `collateral-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      collateralType: 'real_estate',
      objectName: '',
      collateralValue: '',
      cadastralNumber: '',
      address: '',
      vin: '',
      brandModel: '',
      otherDescription: ''
    };
    const collaterals = [...(analysisResult.collaterals || []), newCollateral];
    setAnalysisResult({ ...analysisResult, collaterals });
  };

  const updateCollateral = (index: number, field: keyof Collateral, value: string) => {
    if (!analysisResult?.collaterals) return;
    const updated = [...analysisResult.collaterals];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, collaterals: updated });
  };

  const removeCollateral = (index: number) => {
    if (!analysisResult?.collaterals) return;
    const updated = analysisResult.collaterals.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, collaterals: updated });
  };

  const addObligation = () => {
    if (!analysisResult) return;
    const newObligation: Obligation = {
      id: `obligation-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      contractNumber: '',
      contractDate: '',
      obligationType: ''
    };
    const obligations = [...(analysisResult.obligations || []), newObligation];
    setAnalysisResult({ ...analysisResult, obligations });
  };

  const removeObligation = (index: number) => {
    if (!analysisResult) return;
    const updated = (analysisResult.obligations || []).filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, obligations: updated });
  };

  const updateObligation = (index: number, patch: Partial<Obligation>) => {
    if (!analysisResult) return;
    const updated = [...(analysisResult.obligations || [])];
    updated[index] = { ...updated[index], ...patch };
    setAnalysisResult({ ...analysisResult, obligations: updated });
  };

  const addThirdParty = () => {
    if (!analysisResult) return;
    const newThirdParty: ThirdParty = {
      id: `thirdParty-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: '',
      birthDate: '',
      address: '',
      inn: '',
      snils: ''
    };
    const thirdParties = [...(analysisResult.thirdParties || []), newThirdParty];
    setAnalysisResult({ ...analysisResult, thirdParties });
  };

  const updateThirdParty = (index: number, field: keyof ThirdParty, value: string) => {
    if (!analysisResult?.thirdParties) return;
    const updated = [...analysisResult.thirdParties];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, thirdParties: updated });
  };

  const removeThirdParty = (index: number) => {
    if (!analysisResult?.thirdParties) return;
    const updated = analysisResult.thirdParties.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, thirdParties: updated });
  };

  // --- Должники (со-ответчики): динамический список ---
  const DEBTOR_FLAT_MAP: Record<string, string> = {
    name: 'applicantName', address: 'applicantAddress', inn: 'inn',
    ogrn: 'ogrn', ogrnip: 'ogrnip', birthDate: 'birthDate', birthPlace: 'birthPlace', snils: 'snils'
  };

  const addDebtor = () => {
    if (!analysisResult) return;
    const newDebtor: Debtor = {
      id: `debtor-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: '', address: '', inn: '', ogrn: '', ogrnip: '', birthDate: '', birthPlace: '', snils: ''
    };
    const debtors = [...(analysisResult.debtors || []), newDebtor];
    setAnalysisResult({ ...analysisResult, debtors });
  };

  const updateDebtor = (index: number, field: keyof Debtor, value: string) => {
    if (!analysisResult?.debtors) return;
    const updated = [...analysisResult.debtors];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, debtors: updated });
    // Зеркалим первого должника в плоские поля (одно-должниковые потоки и падежи)
    if (index === 0) {
      const flatKey = DEBTOR_FLAT_MAP[field as string];
      if (flatKey) {
        handleFieldChange(flatKey, value);
        if (field === 'inn') handleFieldChange('companyInn', value);
      }
    }
  };

  const removeDebtor = (index: number) => {
    if (!analysisResult?.debtors) return;
    const updated = analysisResult.debtors.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, debtors: updated });
  };

  const toggleActSelection = (actId: string) => {
    setSelectedActs(prevActs =>
      prevActs.map(act =>
        act.id === actId ? { ...act, selected: !act.selected } : act
      )
    );
  };

  const updateActAdditionalFields = (actId: string, field: 'reason' | 'forParties' | 'courtRequests', value: string) => {
    setSelectedActs(prevActs =>
      prevActs.map(act => {
        if (act.id === actId) {
          return {
            ...act,
            additionalFields: {
              ...act.additionalFields,
              [field]: value
            }
          };
        }
        return act;
      })
    );
  };

  const updateActRtkVariant = (
    actId: string,
    variant: 'realization' | 'restructuring' | 'competition' | 'observation' | 'registry'
  ) => {
    setSelectedActs(prevActs =>
      prevActs.map(act =>
        act.id === actId ? { ...act, rtkVariant: variant } : act
      )
    );
  };

  const handleContinue = () => {
    if (!analysisResult) return;
    // Подготовка итоговых данных (ФИО судьи, синхронизация сумм, выбор пользователя)
    // вынесена в чистую функцию buildSubmitData (features/analysis/lib) — покрыта тестами.
    onAnalysisComplete(
      buildSubmitData({
        analysisResult,
        editedFields,
        entityType,
        collateralOption,
        debtorStatus,
        selectedActs,
      })
    );
  };


  if (isAnalyzing) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <CircularProgress size={64} sx={{ mb: 3 }} />
        <Typography variant="h5" gutterBottom>
          Анализируем документ...
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Извлекаем данные из заявления
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ maxWidth: 600, mx: 'auto', textAlign: 'center' }}>
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
        <Button variant="outlined" onClick={onBack} startIcon={<BackIcon />}>
          Вернуться к загрузке
        </Button>
      </Box>
    );
  }

  if (!analysisResult) {
    return null;
  }

  return (
    <Box sx={{ width: '100%', maxWidth: 1600, mx: 'auto', px: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Button
          variant="outlined"
          onClick={onBack}
          startIcon={<BackIcon />}
          sx={{ mr: 2 }}
        >
          Назад
        </Button>
        <Typography variant="h4" component="h1">
          Анализ документа
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Информация о документе */}
        <Grid item xs={12}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Typography variant="h6" gutterBottom>
                Информация о документе
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Файл: {documentData.fileName}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Размер: {(documentData.fileSize / 1024 / 1024).toFixed(2)} MB
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Дата загрузки: {documentData.uploadDate.toLocaleDateString('ru-RU')}
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Тип документа:
                </Typography>
                <Chip
                  label="Заявление о включении в РТК"
                  color="primary"
                  size="small"
                />
              </Box>

            </CardContent>
          </Card>
        </Grid>

        {/* Блок выбора судебных актов */}
        <Grid item xs={12}>
          <ActSelectionSection
            entityType={entityType}
            setEntityType={setEntityType}
            collateralOption={collateralOption}
            collateralKinds={collateralKinds}
            setCollateralKinds={setCollateralKinds}
            debtorStatus={debtorStatus}
            toggleDebtorStatus={toggleDebtorStatus}
            selectedActs={selectedActs}
            toggleActSelection={toggleActSelection}
            updateActAdditionalFields={updateActAdditionalFields}
            updateActRtkVariant={updateActRtkVariant}
            recommendationsApplied={recommendationsApplied}
            recommendedActs={analysisResult?.recommendedActs}
          />
        </Grid>

        {/* Извлеченные данные */}
        <Grid item xs={12}>
          <Card sx={{ width: '100%' }}>
            <CardContent sx={{ width: '100%', boxSizing: 'border-box' }}>
              <Typography variant="h6" gutterBottom>
                Извлеченные данные
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Проверьте и при необходимости отредактируйте извлеченные данные
              </Typography>

              <Grid container spacing={2} sx={{ width: '100%' }}>
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Судебная информация */}
              <CourtSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Даты и сроки */}
              <DatesSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Данные должника */}
              <DebtorsSection
                debtors={analysisResult?.debtors || []}
                entityType={entityType}
                onUpdate={updateDebtor}
                onAdd={addDebtor}
                onRemove={removeDebtor}
              />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Информация о кредиторе */}
              <CreditorSection
                editedFields={editedFields}
                onFieldChange={handleFieldChange}
                onCreditorChange={handleCreditorChange}
              />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Арбитражный управляющий */}
              <ManagerSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Третьи лица */}
              <ThirdPartiesSection
                thirdParties={analysisResult?.thirdParties || []}
                onUpdate={updateThirdParty}
                onAdd={addThirdParty}
                onRemove={removeThirdParty}
              />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Финансовые данные */}
              <FinancesSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Ранее вынесенное решение суда */}
              <PriorCollectionSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Блок обязательств */}
              <ObligationsSection
                obligations={analysisResult?.obligations || []}
                onUpdate={updateObligation}
                onAdd={addObligation}
                onRemove={removeObligation}
              />
                </Grid>

                {/* Залог */}
                <Grid item xs={12} sx={{ display: 'flex', minWidth: 0 }}>
                  <CollateralSection
                    collaterals={analysisResult?.collaterals || []}
                    onUpdate={updateCollateral}
                    onAdd={addCollateral}
                    onRemove={removeCollateral}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>


      <Box sx={{ textAlign: 'center', mt: 4 }}>
        <Button
          variant="contained"
          size="large"
          onClick={handleContinue}
          startIcon={<CheckIcon />}
          sx={{ px: 4 }}
          disabled={!entityType || !collateralOption || selectedActs.filter(a => a.selected).length === 0}
        >
          Продолжить
        </Button>
      </Box>
    </Box>
  );
};

export default DocumentAnalysis;
