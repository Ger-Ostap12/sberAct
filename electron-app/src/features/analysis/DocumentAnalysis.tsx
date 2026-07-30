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
import { DocumentData, ExtractedData, Obligation, Collateral, CollateralType, EntityType, CollateralOption, DebtorStatus, ApplicationKind, SelectedAct, ThirdParty, Debtor, Heir, PartyLite, MortgageKind, MortgageProperty } from '../../types';
import { useBanks } from './hooks/useBanks';
import { extractCollateralData } from '../../shared/lib/collateral';
import { isFnsCreditor, FNS_CREDITOR_KEY } from '../../shared/lib/banks';
import { buildSubmitData } from './lib/buildSubmitData';
import ObligationsSection from './sections/ObligationsSection';
import CollateralSection from './sections/CollateralSection';
import CourtSection from './sections/CourtSection';
import FieldIssuesPanel from './sections/FieldIssuesPanel';
import DatesSection from './sections/DatesSection';
import ManagerSection from './sections/ManagerSection';
import LiquidationSection from './sections/LiquidationSection';
import AbsentDebtorSection from './sections/AbsentDebtorSection';
import DeceasedSection from './sections/DeceasedSection';
import ThirdPartiesSection from './sections/ThirdPartiesSection';
import DebtorsSection from './sections/DebtorsSection';
import CreditorSection from './sections/CreditorSection';
import FinancesSection from './sections/FinancesSection';
import PriorCollectionSection from './sections/PriorCollectionSection';
import ActSelectionSection from './sections/ActSelectionSection';
import CoborrowerSection from './sections/CoborrowerSection';
import GuarantorSection from './sections/GuarantorSection';
import MortgagePropertySection from './sections/MortgagePropertySection';
import RepresentativeSection from './sections/RepresentativeSection';
import RespondentRepresentativeSection from './sections/RespondentRepresentativeSection';
import MortgageKindSection from './sections/MortgageKindSection';
import ClaimResolutionSection from './sections/ClaimResolutionSection';
import { findCourtDefaults } from '../../shared/lib/courts';

interface DocumentAnalysisProps {
  documentData: DocumentData;
  extractedData?: ExtractedData;
  /** Режим формы: 'bankruptcy' — полный функционал (по умолчанию); 'mortgage' —
   *  без блоков управляющий/акты/залог/статус/взыскание, с созаёмщиком/поручителем/
   *  предметом ипотеки. */
  mode?: 'bankruptcy' | 'mortgage';
  onAnalysisComplete: (data: ExtractedData) => void;
  onBack: () => void;
}

const DocumentAnalysis: React.FC<DocumentAnalysisProps> = ({
  documentData,
  extractedData: propExtractedData,
  mode = 'bankruptcy',
  onAnalysisComplete,
  onBack
}) => {
  const isMortgage = mode === 'mortgage';
  const [isAnalyzing, setIsAnalyzing] = useState(true);
  const [analysisResult, setAnalysisResult] = useState<ExtractedData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editedFields, setEditedFields] = useState<Record<string, string>>({});

  // Единый реестр банков с бэкенда (для дропдауна кредитора и автозаполнения).
  const banks = useBanks();

  // Состояние для выбора актов
  const [entityType, setEntityType] = useState<EntityType | null>(null);
  const [collateralOption, setCollateralOption] = useState<CollateralOption | null>(null);
  // Виды залога для блока «Выбор залога» (можно несколько: недвижка, транспорт, иное).
  const [collateralKinds, setCollateralKinds] = useState<{ realEstate: boolean; auto: boolean; other: boolean }>({ realEstate: false, auto: false, other: false });
  const [selectedActs, setSelectedActs] = useState<SelectedAct[]>([]);
  const [recommendationsApplied, setRecommendationsApplied] = useState(false);
  // Статус должника (банкротство): отсутствующий / ликвидируемый / умерший.
  // Взаимоисключающие, но ОПЦИОНАЛЬНЫ и НЕЗАВИСИМЫ от вида заявления.
  const [debtorStatus, setDebtorStatus] = useState<DebtorStatus | null>(null);
  // Вид заявления (независимый блок): ВКЛ в РТК / инициирование / самобанкрот.
  // По умолчанию — рядовое инициирование.
  const [applicationKind, setApplicationKind] = useState<ApplicationKind>('other');
  // Чекбокс «Короткий текст»: доп. генерация резолютивки основной процедуры.
  const [shortText, setShortText] = useState<boolean>(false);
  // Вид ипотеки (только режим mortgage): гражданская / военная (ЦЖЗ). Военная
  // перестраивает блок «Финансовые данные».
  const [mortgageKind, setMortgageKind] = useState<MortgageKind>('civil');

  // Статус лица влияет на рекомендацию финального СА:
  // отсутствующий/ликвидируемый ЮЛ → «Решение конкурсное»; умерший ФЛ → «Решение реализация».
  useEffect(() => {
    if (!debtorStatus) return;
    // Статус подразумевает тип лица: отсутствующий/ликвидируемый — ЮЛ, умерший — ФЛ.
    setEntityType(debtorStatus === 'deceased' ? 'individual' : 'legal');
    // При ВКЛ в РТК финал уже занят (final_rtk_inclusion) — процедурный не навязываем.
    if (applicationKind === 'rtk') return;
    const finalByStatus: Partial<Record<DebtorStatus, string>> = {
      absent: 'final_competition',
      liquidation: 'final_competition',
      deceased: 'final_realization',
    };
    const targetFinal = finalByStatus[debtorStatus];
    setSelectedActs(prev => prev.map(act =>
      act.category === 'final' ? { ...act, selected: act.id === targetFinal } : act
    ));
  }, [debtorStatus, applicationKind]);

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

        // Авто-статус должника: по флагу backend (debtorStatusHint) либо, для
        // умершего, по процедуре — процедурный путь остаётся как запасной для
        // документов, где детект по тексту не сработал.
        const procType = (analysisResult.fields as any)?.procedureType
          || (analysisResult.fields as any)?.procedureTypeRaw || '';
        if (String(procType).toLowerCase().includes('умер') || String(procType).toLowerCase() === 'deceased') {
          setDebtorStatus('deceased');
        } else if (analysisResult.debtorStatusHint === 'liquidation') {
          setDebtorStatus('liquidation');
        } else if (analysisResult.debtorStatusHint === 'absent') {
          setDebtorStatus('absent');
        } else if (analysisResult.debtorStatusHint === 'deceased') {
          setDebtorStatus('deceased');
        }

        // Вид заявления из рекомендаций: самобанкротство (детектор backend) →
        // «Самобанкрот» (скрывает блок кредитора); рекомендация ВКЛ в РТК → 'rtk'.
        if (analysisResult.applicationKind === 'self_bankruptcy') {
          setApplicationKind('self');
        } else if (recommendedActs.recommendedActIds?.includes('final_rtk_inclusion')) {
          setApplicationKind('rtk');
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
        // У ФНС-заявлений (уполномоченный орган) залога не бывает — принудительно
        // «Без залога», даже если детектор ошибочно нашёл предмет в тексте.
        if (isFnsCreditor(propExtractedData.fields?.creditorName)) {
          setCollateralKinds({ realEstate: false, auto: false, other: false });
        } else {
          const hasRealEstate = initialCollaterals.some(c => c.collateralType === 'real_estate');
          const hasAuto = initialCollaterals.some(c => c.collateralType === 'auto');
          const hasOther = initialCollaterals.some(c => c.collateralType === 'other');
          setCollateralKinds({ realEstate: hasRealEstate, auto: hasAuto, other: hasOther });
        }

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

        // Наследники умершего должника: backend отдаёт их без id (как третьих лиц) —
        // проставляем свои, иначе ключи карточек и правка по индексу поедут.
        const initialHeirs: Heir[] = (propExtractedData.heirs || []).map((h, i) => ({
          ...h,
          id: h.id || `heir-${Date.now()}-${i}-${Math.random().toString(36).slice(2)}`
        }));

        // Ипотека: маппинг ролей (согласовано). Ответчик ← ВСЕ должники (можно
        // несколько); Третье лицо ← третьи лица (как в банкротстве); Созаёмщик и
        // Поручитель — ПУСТЫЕ (вводятся вручную: созаёмщик может совпадать с
        // ответчиком, поручитель ≠ третье лицо, backend их не выделяет). В режиме
        // банкротства coborrowers/guarantors пусты (блоки скрыты).
        const initialCoborrowers: PartyLite[] = [];
        const initialGuarantors: PartyLite[] = [];

        // Предмет ипотеки: первый объект засеваем из извлечённых плоских полей
        // (объектов может быть несколько — добавляются вручную). Если извлечение
        // пустое — оставляем один пустой предмет, чтобы карточка была видна.
        const pmf = propExtractedData.fields || {};
        // Предмет(ы) ипотеки: приоритет — структурированный массив с бэкенда
        // (несколько объектов, стоимость/НПЦ/ЕГРН реконсилированы). Фолбэк на один
        // объект из плоских полей — если бэкенд массив не дал (нестандартный формат).
        const backendProps = propExtractedData.mortgageProperties;
        const initialMortgageProperties: MortgageProperty[] =
          Array.isArray(backendProps) && backendProps.length > 0
            ? backendProps.map((p, i) => ({
                id: p.id || `mortgageProperty-${i}-${Math.random().toString(36).slice(2)}`,
                description: p.description || '',
                cadastralNumber: p.cadastralNumber || '',
                address: p.address || '',
                value: p.value || '',
                startingPrice: p.startingPrice || '',
                appraisalReport: p.appraisalReport || '',
                egrnRecord: p.egrnRecord || '',
                egrnRecordDate: p.egrnRecordDate || '',
                npcStrategy: p.npcStrategy || '',
                dduContract: p.dduContract || '',
                dduDate: p.dduDate || '',
              }))
            : [{
                id: `mortgageProperty-${Date.now()}-${Math.random().toString(36).slice(2)}`,
                description: pmf.mortgageCollateralDescription1221 || '',
                cadastralNumber: pmf.mortgageCadastralNumber || '',
                address: pmf.mortgagePropertyAddress || '',
                value: pmf.mortgageCollateralValue1224 || '',
                startingPrice: pmf.mortgageStartingPrice1225 || '',
                appraisalReport: pmf.mortgageAppraisalReport1223 || '',
              }];

        // Ипотека: период взыскания извлекается в плоские поля [120]/[121];
        // объект обязательства их не несёт — сеем в (единственное) обязательство,
        // если период на нём ещё не задан. Только для ипотеки.
        const initialObligations = (propExtractedData.obligations || []).map((o, i) =>
          isMortgage && i === 0
            ? {
                ...o,
                collectionPeriodFrom: o.collectionPeriodFrom || pmf.mortgagePeriodStart120 || '',
                collectionPeriodTo: o.collectionPeriodTo || pmf.mortgagePeriodEnd121 || '',
              }
            : o,
        );

        const fullAnalysisResult = {
          ...propExtractedData,
          obligations: initialObligations,
          collaterals: initialCollaterals,
          thirdParties: initialThirdParties,
          debtors: initialDebtors,
          heirs: initialHeirs,
          coborrowers: initialCoborrowers,
          guarantors: initialGuarantors,
          mortgageProperties: initialMortgageProperties
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
        // Ипотека: представитель истца из поля шаблона + дефолты суда
        // (email/сайт/адрес) по справочнику, если название суда распознано.
        if (isMortgage) {
          if (!cleanFields.representativeName && cleanFields.mortgageRepresentative22) {
            cleanFields.representativeName = cleanFields.mortgageRepresentative22;
          }
          // Вид ипотеки — авто-детект бэкендом (военная/гражданская). Инициализирует
          // переключатель; пользователь может переопределить вручную.
          if (propExtractedData.mortgageKind) {
            setMortgageKind(propExtractedData.mortgageKind);
          }
          // Название/адрес суда извлекаются бэкендом в плоские поля с маркерами
          // [002]/[001]; форма читает courtName/courtAddress — переносим, если пусто.
          if (!cleanFields.courtName && cleanFields.mortgageCourtName002) {
            cleanFields.courtName = cleanFields.mortgageCourtName002;
          }
          if (!cleanFields.courtAddress && cleanFields.mortgageCourtAddress001) {
            cleanFields.courtAddress = cleanFields.mortgageCourtAddress001;
          }
          const courtDefaults = findCourtDefaults(cleanFields.courtName);
          if (courtDefaults) {
            if (!cleanFields.courtEmail) cleanFields.courtEmail = courtDefaults.email;
            if (!cleanFields.courtSite) cleanFields.courtSite = courtDefaults.site;
            if (!cleanFields.courtAddress && courtDefaults.address) cleanFields.courtAddress = courtDefaults.address;
            if (!cleanFields.mortgageCourtNameGenitive) cleanFields.mortgageCourtNameGenitive = courtDefaults.genitive;
          }
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
  }, [documentData, propExtractedData, isMortgage]);

  const handleFieldChange = (fieldName: string, value: string) => {
    setEditedFields(prev => ({
      ...prev,
      [fieldName]: value
    }));
  };

  const handleCreditorChange = (value: string) => {
    if (value === FNS_CREDITOR_KEY) {
      // Выбрана «ФНС»: сохраняем уже распознанное детальное имя налогового органа
      // («ФНС России в лице Межрайонной ИФНС № N …») и его юр-адрес из реестра —
      // не затираем. Если имя не было ФНС, ставим общий «ФНС России» для ручного ввода.
      setEditedFields(prev => ({
        ...prev,
        creditorName: isFnsCreditor(prev.creditorName) ? prev.creditorName : 'ФНС России'
      }));
    } else if (value === 'OTHER') {
      // Если выбран "Другой банк", очищаем автозаполненные данные, но оставляем creditorName пустым для ручного ввода
      setEditedFields(prev => ({
        ...prev,
        creditorName: '',
        creditorAddress: '',
        creditorOgrn: '',
        creditorInn: ''
      }));
    } else if (value && banks.find(b => b.display === value)) {
      // Если выбран банк из реестра (с бэкенда), автозаполняем данные
      const bankData = banks.find(b => b.display === value)!;
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

  // Ипотека: при вводе/распознавании названия суда подставляем дефолты
  // (email/сайт/адрес) по справочнику, НЕ затирая уже введённые значения.
  const handleCourtNameChange = (value: string) => {
    setEditedFields(prev => {
      const next: Record<string, string> = { ...prev, courtName: value };
      const d = findCourtDefaults(value);
      if (d) {
        if (!next.courtEmail) next.courtEmail = d.email;
        if (!next.courtSite) next.courtSite = d.site;
        if (!next.courtAddress && d.address) next.courtAddress = d.address;
        // Родительный падеж — «якорь» для акта: гарантированно верная форма для
        // известного суда, минуя морфологию бэкенда.
        if (!next.mortgageCourtNameGenitive) next.mortgageCourtNameGenitive = d.genitive;
      }
      return next;
    });
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
      ogrn: '',
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

  // --- Предметы ипотеки (ипотека): динамический список (как третьи лица) ---
  const addMortgageProperty = () => {
    if (!analysisResult) return;
    const newProperty: MortgageProperty = {
      id: `mortgageProperty-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      description: '',
      cadastralNumber: '',
      address: '',
      value: '',
      startingPrice: '',
      appraisalReport: ''
    };
    const mortgageProperties = [...(analysisResult.mortgageProperties || []), newProperty];
    setAnalysisResult({ ...analysisResult, mortgageProperties });
  };

  const updateMortgageProperty = (index: number, field: keyof MortgageProperty, value: string) => {
    if (!analysisResult?.mortgageProperties) return;
    const updated = [...analysisResult.mortgageProperties];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, mortgageProperties: updated });
  };

  const removeMortgageProperty = (index: number) => {
    if (!analysisResult?.mortgageProperties) return;
    const updated = analysisResult.mortgageProperties.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, mortgageProperties: updated });
  };

  // --- Созаёмщики (ипотека): динамический список (как третьи лица) ---
  const addCoborrower = () => {
    if (!analysisResult) return;
    const newCoborrower: PartyLite = {
      id: `coborrower-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: '', inn: '', address: ''
    };
    const coborrowers = [...(analysisResult.coborrowers || []), newCoborrower];
    setAnalysisResult({ ...analysisResult, coborrowers });
  };

  const updateCoborrower = (index: number, field: keyof PartyLite, value: string) => {
    if (!analysisResult?.coborrowers) return;
    const updated = [...analysisResult.coborrowers];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, coborrowers: updated });
  };

  const removeCoborrower = (index: number) => {
    if (!analysisResult?.coborrowers) return;
    const updated = analysisResult.coborrowers.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, coborrowers: updated });
  };

  // --- Поручители (ипотека): динамический список (как третьи лица) ---
  const addGuarantor = () => {
    if (!analysisResult) return;
    const newGuarantor: PartyLite = {
      id: `guarantor-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: '', inn: '', address: ''
    };
    const guarantors = [...(analysisResult.guarantors || []), newGuarantor];
    setAnalysisResult({ ...analysisResult, guarantors });
  };

  const updateGuarantor = (index: number, field: keyof PartyLite, value: string) => {
    if (!analysisResult?.guarantors) return;
    const updated = [...analysisResult.guarantors];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, guarantors: updated });
  };

  const removeGuarantor = (index: number) => {
    if (!analysisResult?.guarantors) return;
    const updated = analysisResult.guarantors.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, guarantors: updated });
  };

  // --- Наследники умершего должника: динамический список (как третьи лица) ---
  const addHeir = () => {
    if (!analysisResult) return;
    const newHeir: Heir = {
      id: `heir-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: '',
      address: ''
    };
    const heirs = [...(analysisResult.heirs || []), newHeir];
    setAnalysisResult({ ...analysisResult, heirs });
  };

  const updateHeir = (index: number, field: keyof Heir, value: string) => {
    if (!analysisResult?.heirs) return;
    const updated = [...analysisResult.heirs];
    updated[index] = { ...updated[index], [field]: value };
    setAnalysisResult({ ...analysisResult, heirs: updated });
  };

  const removeHeir = (index: number) => {
    if (!analysisResult?.heirs) return;
    const updated = analysisResult.heirs.filter((_, i) => i !== index);
    setAnalysisResult({ ...analysisResult, heirs: updated });
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

  // Единый радио-блок «Вид заявления» объединяет две оси: вид (ВКЛ в РТК /
  // Вид заявления (независимый от статуса лица блок). Драйвер ВКЛ в РТК — акт
  // final_rtk_inclusion (синхронен с чекбоксом в «3. Финальные СА»). При уходе из
  // РТК, если задан статус лица, возвращаем его процедурный финал (competition/
  // realization); иначе просто снимаем ВКЛ в РТК, оставляя финал рекомендации/выбору.
  const handleApplicationKindChange = (v: ApplicationKind) => {
    setApplicationKind(v);
    if (v === 'rtk') {
      // Только ВКЛ в РТК среди финальных.
      setSelectedActs(prev => prev.map(a =>
        a.category === 'final' ? { ...a, selected: a.id === 'final_rtk_inclusion' } : a));
      return;
    }
    const procFinal = debtorStatus === 'deceased' ? 'final_realization'
      : (debtorStatus === 'absent' || debtorStatus === 'liquidation') ? 'final_competition'
      : null;
    setSelectedActs(prev => prev.map(a => {
      if (a.category !== 'final') return a;
      if (procFinal) return { ...a, selected: a.id === procFinal };
      return a.id === 'final_rtk_inclusion' ? { ...a, selected: false } : a;
    }));
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
        applicationKind,
        selectedActs,
        shortText,
        documentCategory: isMortgage ? 'mortgage' : 'bankruptcy',
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

  // Поле «Саморегулируемая организация» управляется видом заявления: «Включение в
  // РТК» → управляющий уже утверждён, СРО скрыта; иначе (инициирование/самобанкрот)
  // — суд утверждает управляющего из предложенной СРО, поле показывается.
  const rtkInclusion = applicationKind === 'rtk';
  const showSroField = !rtkInclusion;
  // Поле «ФИО» управляющего скрывается там, где конкретный управляющий ещё не
  // утверждён и в заявлении названа только СРО: банк-инициирование и самобанкрот.
  // Показывается при РТК (управляющий уже утверждён) и во всех ФНС-заявлениях
  // (уполномоченный орган указывает кандидатуру). Матрица: см. блок «Управляющий».
  const isSelf = applicationKind === 'self';
  const isFns = isFnsCreditor(editedFields.creditorName);
  const showFioField = !isSelf && (rtkInclusion || isFns);

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
                  label={isMortgage ? 'Ипотека' : 'Заявление о включении в РТК'}
                  color="primary"
                  size="small"
                />
              </Box>

            </CardContent>
          </Card>
        </Grid>

        {/* Блок выбора судебных актов — только в режиме банкротства. */}
        {!isMortgage && (
        <Grid item xs={12}>
          <ActSelectionSection
            entityType={entityType}
            setEntityType={setEntityType}
            collateralOption={collateralOption}
            collateralKinds={collateralKinds}
            setCollateralKinds={setCollateralKinds}
            applicationKind={applicationKind}
            setApplicationKind={handleApplicationKindChange}
            debtorStatus={debtorStatus}
            setDebtorStatus={setDebtorStatus}
            selectedActs={selectedActs}
            toggleActSelection={toggleActSelection}
            updateActAdditionalFields={updateActAdditionalFields}
            updateActRtkVariant={updateActRtkVariant}
            recommendationsApplied={recommendationsApplied}
            recommendedActs={analysisResult?.recommendedActs}
            shortText={shortText}
            setShortText={setShortText}
          />
        </Grid>
        )}

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

              {/* Адресный список подозрительных полей от контракта (backend
                  field_contract): что вычищено и что стоит сверить. Стоит ПЕРВЫМ —
                  это то, что юрист смотрит раньше остальной формы. */}
              <FieldIssuesPanel issues={analysisResult?.fieldIssues} />

              <Grid container spacing={2} sx={{ width: '100%' }}>
                {/* Вид ипотеки (гражданская/военная) — только в ипотеке, во всю ширину. */}
                {isMortgage && (
                <Grid item xs={12} sx={{ display: 'flex', minWidth: 0 }}>
              <MortgageKindSection mortgageKind={mortgageKind} onChange={setMortgageKind} />
                </Grid>
                )}

                {/* Удовлетворение иска — только в ипотеке, полностью ручной выбор. */}
                {isMortgage && (
                <Grid item xs={12} sx={{ display: 'flex', minWidth: 0 }}>
              <ClaimResolutionSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>
                )}

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Судебная информация */}
              <CourtSection
                editedFields={editedFields}
                onFieldChange={handleFieldChange}
                mode={mode}
                onCourtNameChange={isMortgage ? handleCourtNameChange : undefined}
              />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Даты и сроки */}
              <DatesSection editedFields={editedFields} onFieldChange={handleFieldChange} mode={mode} />
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Данные должника / ответчика (ипотека) */}
              <DebtorsSection
                debtors={analysisResult?.debtors || []}
                entityType={entityType}
                onUpdate={updateDebtor}
                onAdd={addDebtor}
                onRemove={removeDebtor}
                fieldQuality={analysisResult?.fieldQuality}
                mode={mode}
              />
                </Grid>

                {/* Информация о кредиторе / истце (ипотека). У самобанкрота
                    кредитора-заявителя нет — блок скрываем. */}
                {!isSelf && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <CreditorSection
                editedFields={editedFields}
                onFieldChange={handleFieldChange}
                onCreditorChange={handleCreditorChange}
                banks={banks}
                fieldQuality={analysisResult?.fieldQuality}
                mode={mode}
              />
                </Grid>
                )}

                {/* Представитель истца — только в ипотеке (ФИО + срок доверенности). */}
                {isMortgage && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <RepresentativeSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>
                )}

                {/* Представитель ответчика — только в ипотеке (ФИО). */}
                {isMortgage && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <RespondentRepresentativeSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>
                )}

                {/* ФНС: две независимые колонки — слева «Управляющий» + «Финансы»
                    встык, справа «Сведения о взыскании». Построчный Grid даёт masonry-
                    пустоту (высокие Финансы), поэтому для ФНС колонки собираем вручную.
                    В режиме ипотеки ФНС-раскладки нет. */}
                {!isMortgage && isFnsCreditor(editedFields.creditorName) && (
                <Grid item xs={12}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <ManagerSection editedFields={editedFields} onFieldChange={handleFieldChange} showSro={showSroField} showFio={showFioField} />
                      <Box sx={{ mt: 3 }}>
                        <FinancesSection editedFields={editedFields} onFieldChange={handleFieldChange} financeBreakdown={analysisResult?.financeBreakdown} fieldQuality={analysisResult?.fieldQuality} />
                      </Box>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <PriorCollectionSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                    </Grid>
                  </Grid>
                </Grid>
                )}

                {/* Арбитражный управляющий (не-ФНС; у ФНС — в колонке выше).
                    В ипотеке управляющего нет. */}
                {!isMortgage && !isFnsCreditor(editedFields.creditorName) && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <ManagerSection editedFields={editedFields} onFieldChange={handleFieldChange} showSro={showSroField} showFio={showFioField} />
                </Grid>
                )}

                {/* Объявление о ликвидации — только при статусе «Ликвидируемый» (ЮЛ). */}
                {!isMortgage && debtorStatus === 'liquidation' && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <LiquidationSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>
                )}

                {/* Информация по счетам — только при статусе «Отсутствующий» (ЮЛ). */}
                {!isMortgage && debtorStatus === 'absent' && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <AbsentDebtorSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>
                )}

                {/* Сведения о смерти — только при статусе «Умерший» (физлицо). */}
                {!isMortgage && debtorStatus === 'deceased' && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <DeceasedSection
                editedFields={editedFields}
                onFieldChange={handleFieldChange}
                heirs={analysisResult?.heirs || []}
                onHeirUpdate={updateHeir}
                onHeirAdd={addHeir}
                onHeirRemove={removeHeir}
              />
                </Grid>
                )}

                {/* Третьи лица — показываем в банкротстве (не-ФНС) и в ипотеке
                    (роль «Третье лицо» ≠ поручитель). У ФНС третьих лиц нет. */}
                {!isFnsCreditor(editedFields.creditorName) && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Третьи лица */}
              <ThirdPartiesSection
                thirdParties={analysisResult?.thirdParties || []}
                onUpdate={updateThirdParty}
                onAdd={addThirdParty}
                onRemove={removeThirdParty}
                mode={mode}
              />
                </Grid>
                )}

                {/* Созаёмщик — только в режиме ипотеки. */}
                {isMortgage && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <CoborrowerSection
                coborrowers={analysisResult?.coborrowers || []}
                onUpdate={updateCoborrower}
                onAdd={addCoborrower}
                onRemove={removeCoborrower}
              />
                </Grid>
                )}

                {/* Информация о поручителе — только в режиме ипотеки. */}
                {isMortgage && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <GuarantorSection
                guarantors={analysisResult?.guarantors || []}
                onUpdate={updateGuarantor}
                onAdd={addGuarantor}
                onRemove={removeGuarantor}
              />
                </Grid>
                )}

                {/* Предмет ипотеки (недвижимость) — только в режиме ипотеки. */}
                {isMortgage && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <MortgagePropertySection
                mortgageProperties={analysisResult?.mortgageProperties || []}
                onUpdate={updateMortgageProperty}
                onAdd={addMortgageProperty}
                onRemove={removeMortgageProperty}
                mortgageKind={mortgageKind}
              />
                </Grid>
                )}

                {/* Финансовые данные (не-ФНС; у ФНС — в колонке выше). У самобанкрота
                    финансов из просительной нет (суммы по каждому кредитору в теле) —
                    блок скрываем вместе с кредитором. */}
                {!isFnsCreditor(editedFields.creditorName) && !isSelf && (
                <Grid item xs={12} md={isMortgage && mortgageKind === 'military' ? 12 : 6} sx={{ display: 'flex', minWidth: 0 }}>
              <FinancesSection editedFields={editedFields} onFieldChange={handleFieldChange} financeBreakdown={analysisResult?.financeBreakdown} mode={mode} mortgageKind={mortgageKind} />
                </Grid>
                )}

                {/* Сведения о взыскании (не-ФНС; у ФНС — в правой колонке выше).
                    В ипотеке блока прежнего взыскания нет. */}
                {!isMortgage && !isFnsCreditor(editedFields.creditorName) && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              <PriorCollectionSection editedFields={editedFields} onFieldChange={handleFieldChange} />
                </Grid>
                )}

                {/* Обязательства — у ФНС-заявлений (уполномоченный орган) кредитных
                    обязательств/поручительств нет, блок скрываем. */}
                {!isFnsCreditor(editedFields.creditorName) && (
                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Блок обязательств */}
              <ObligationsSection
                obligations={analysisResult?.obligations || []}
                onUpdate={updateObligation}
                onAdd={addObligation}
                onRemove={removeObligation}
                mode={mode}
              />
                </Grid>
                )}

                {/* Залог — у ФНС-заявлений (уполномоченный орган) залога не бывает,
                    блок скрываем. В ипотеке предмет — в блоке «Предмет ипотеки». */}
                {!isMortgage && !isFnsCreditor(editedFields.creditorName) && (
                <Grid item xs={12} sx={{ display: 'flex', minWidth: 0 }}>
                  <CollateralSection
                    collaterals={analysisResult?.collaterals || []}
                    onUpdate={updateCollateral}
                    onAdd={addCollateral}
                    onRemove={removeCollateral}
                  />
                </Grid>
                )}
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
