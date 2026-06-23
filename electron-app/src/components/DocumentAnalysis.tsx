import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Grid,
  TextField,
  Chip,
  Alert,
  CircularProgress,
  Divider,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  RadioGroup,
  Radio,
  FormControlLabel,
  Checkbox,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import { ArrowBack as BackIcon, CheckCircle as CheckIcon, Add as AddIcon, Close as CloseIcon, ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import { DocumentData, ExtractedData, Obligation, Collateral, CollateralType, EntityType, CollateralOption, SelectedAct, ThirdParty, Debtor } from '../types';

// Данные банков для автозаполнения
const BANK_DATA: Record<string, { address: string; ogrn: string; inn: string }> = {
  'ПАО ВТБ Банк': {
    address: '191144, г. Санкт-Петербург, пер. Дегтярный, д. 11 литер а',
    ogrn: '1027739609391',
    inn: '7702070139'
  },
  'Т-банк': {
    address: '127287, г. Москва, вн. тер. г. Муниципальный округ Савеловский, ул. Хуторская 2-Я, д. 38а, стр. 26',
    ogrn: '1027739642281',
    inn: '7710140679'
  },
  'Альфа банк': {
    address: '107078, г. Москва, ул. Каланчевская, д.27',
    ogrn: '1027700067328',
    inn: '7728168971'
  },
  'МТС банк': {
    address: '115432, г. Москва, пр-т Андропова, д. 18, корп. 1.',
    ogrn: '1027739053704',
    inn: '7702045051'
  },
  'банк Центр-инвест': {
    address: '344000, г. Ростов-на-Дону, пр. Соколова, д. 62.',
    ogrn: '1026100001949',
    inn: '6163011391'
  },
  'ПСБ банк': {
    address: '150003, Ярославская область, г. Ярославль, ул. Республиканская, д. 16',
    ogrn: '1027739019142',
    inn: '7744000912'
  },
  'Газпромбанк': {
    address: '117420, г. Москва, ул. Намёткина, д. 16, корп. 1.',
    ogrn: '1027700167110',
    inn: '7744001497'
  },
  'Сбербанк': {
    address: '117997, г. Москва, вн. тер. г. муниципальный округ Академический, ул. Вавилова, д. 19',
    ogrn: '1027700132195',
    inn: '7707083893'
  }
};

// Преобразование дат между форматом ДД.ММ.ГГГГ и форматом для input[type="date"] (ГГГГ-ММ-ДД)
const toInputDate = (value?: string): string => {
  if (!value) return '';
  // Если уже в ISO-формате, возвращаем как есть
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  const match = value.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!match) return '';
  const [, day, month, year] = match;
  const dd = day.padStart(2, '0');
  const mm = month.padStart(2, '0');
  return `${year}-${mm}-${dd}`;
};

const fromInputDate = (value: string): string => {
  if (!value) return '';
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
};

const BANK_NAMES = Object.keys(BANK_DATA);

// Распознавание банка по вариантам названия из документа («ПАО Сбербанк»,
// «Сбербанк России», «в лице филиала …») → ключ в BANK_DATA, чтобы банк
// автоматически выделялся в выпадающем списке. Данные (ИНН/ОГРН/адрес) при этом
// остаются document-first и не перезаписываются.
const BANK_ALIASES: Array<{ key: string; keywords: string[] }> = [
  { key: 'Сбербанк', keywords: ['сбербанк', 'сбер банк'] },
  { key: 'ПАО ВТБ Банк', keywords: ['втб'] },
  { key: 'Т-банк', keywords: ['тинькофф', 'т-банк', 'тбанк'] },
  { key: 'Альфа банк', keywords: ['альфа'] },
  { key: 'МТС банк', keywords: ['мтс'] },
  { key: 'банк Центр-инвест', keywords: ['центр-инвест', 'центр инвест'] },
  { key: 'ПСБ банк', keywords: ['промсвязь', 'псб'] },
  { key: 'Газпромбанк', keywords: ['газпромбанк', 'газпром банк'] },
];

const matchBankKey = (name?: string): string | null => {
  if (!name) return null;
  if (BANK_DATA[name]) return name; // точное совпадение с ключом
  const low = name.toLowerCase();
  for (const { key, keywords } of BANK_ALIASES) {
    if (keywords.some(k => low.includes(k))) return key;
  }
  return null;
};

// Функция для преобразования полного ФИО в формат "Фамилия И.О."
const formatJudgeName = (fullName: string): string => {
  if (!fullName || !fullName.trim()) return fullName;

  // Разбиваем ФИО на части
  const parts = fullName.trim().split(/\s+/);

  if (parts.length < 2) {
    // Если только одно слово, возвращаем как есть
    return fullName;
  }

  // Фамилия - первое слово
  const lastName = parts[0];

  // Имя и отчество - остальные слова
  const firstName = parts[1] || '';
  const middleName = parts[2] || '';

  // Берем первые буквы имени и отчества
  const firstInitial = firstName.charAt(0).toUpperCase();
  const middleInitial = middleName.charAt(0).toUpperCase();

  // Формируем результат: "Фамилия И.О."
  if (middleInitial) {
    return `${lastName} ${firstInitial}.${middleInitial}.`;
  } else if (firstInitial) {
    return `${lastName} ${firstInitial}.`;
  } else {
    return lastName;
  }
};

// Список судей
const JUDGES = [
  'Абдулина Светлана Витальевна',
  'Агальцова Ксения Владимировна',
  'Алмазова Зинаида Петровна',
  'Андрианова Юлия Юрьевна',
  'Апостолова Ольга Фёдоровна',
  'Бабаян Валентина Гарегиновна',
  'Батурина Екатерина Александровна',
  'Бондарева Зоя Ивановна',
  'Бондарчук Елена Владимировна',
  'Бруевич Валентина Сергеевна',
  'Бычкова Ольга Геннадиевна',
  'Власова Наталья Юрьевна',
  'Волуйских Илья Игоревич',
  'Ганюшкина Ольга Борисовна',
  'Гафиулина Анна Васильевна',
  'Демченко Ольга Александровна',
  'Ерёмин Филипп Фёдорович',
  'Жигало Наталья Александровна',
  'Захарова Виктория Михайловна',
  'Захарченко Ольга Петровна',
  'Золотарёва Ольга Валерьевна',
  'Исаченко Анна Николаевна',
  'Капелюха Ольга Ивановна',
  'Ковалёва Валентина Юрьевна',
  'Козин Денис Васильевич',
  'Колесник Ирина Валентиновна',
  'Комурджиева Ирина Петровна',
  'Комягин Виталий Михайлович',
  'Конева Марина Александровна',
  'Константинов Дмитрий Валентинович',
  'Королькова Нелли Николаевна',
  'Корх Сергей Эдуардович',
  'Косулина Екатерина Олеговна',
  'Кривоносова Ольга Валерьевна',
  'Кузина Наталия Владимировна',
  'Латышева Кристина Витальевна',
  'Лебедев Александр Михайлович',
  'Лебедева Юлия Валерьевна',
  'Лёвина Марьяна Алексеевна',
  'Ложечник Дмитрий Александрович',
  'Маковкина Ирина Владимировна',
  'Малыгина Марина Айдамировна',
  'Мариненко Екатерина Никитична',
  'Мацыпаева Елена Николаевна',
  'Меленчук Илья Сергеевич',
  'Мишаков Олег Григорьевич',
  'Новожилова Марина Александровна',
  'Овчаренко Наталия Николаевна',
  'Овчинникова Виктория Витальевна',
  'Палий Юлия Анатольевна',
  'Панова Кристина Олеговна',
  'Положий Кристина Владимировна',
  'Рябова Татьяна Павловна',
  'Сергеева Ксения Александровна',
  'Смородина Юлия Александровна',
  'Солуянова Татьяна Александровна',
  'Стрельникова Елена Сергеевна',
  'Танова Диана Григорьевна',
  'Тимина Екатерина Юрьевна',
  'Тютюник Павел Николаевич',
  'Фаргиева Ася Ибрагимовна',
  'Хатламаджиян Арташес Семенович',
  'Чумина Ксения Сергеевна',
  'Ширинская Ирина Борисовна',
  'Штрауб Валентина Леонидовна'
];

// Стили для подписи, наложенной на верхнюю границу поля (граница «пропадает» под текстом)
const LABEL_OVERLAP_BOX = { position: 'relative' as const, pt: 1.5 };
const BLOCK_BOX_SX = {
  width: '100%',
  boxSizing: 'border-box' as const,
  border: '1px solid',
  borderColor: 'divider',
  borderRadius: 1,
  p: 2,
};
const LABEL_OVERLAP_SX = {
  position: 'absolute' as const,
  left: 14,
  top: 12,
  transform: 'translateY(-50%)',
  backgroundColor: 'background.paper',
  pl: 0.5,
  pr: 1,
  zIndex: 1,
  fontSize: '0.875rem',
  color: 'text.secondary'
};

// Функция для извлечения адреса и кадастрового номера из описания предмета залога
const extractCollateralData = (description: string): { address?: string; cadastralNumber?: string } => {
  if (!description) return {};

  const result: { address?: string; cadastralNumber?: string } = {};

  // Извлекаем адрес (формат: индекс (6 цифр) + адрес)
  // Паттерн: 6 цифр, затем запятая/пробел, затем русские буквы и адресные данные
  // Ищем адрес после слов "адрес", "расположен", "находится", "по адресу"
  const addressPatterns = [
    /(?:адрес|расположен|находится|по\s+адресу)[:\s]*([0-9]{6}[,\s]+[А-ЯЁа-яё][^,\n]{10,200}?(?:[,\s]+[А-ЯЁа-яё][^,\n]{5,100}?)*)/i,
    /([0-9]{6}[,\s]+[А-ЯЁа-яё][^,\n]{10,200}?(?:[,\s]+[А-ЯЁа-яё][^,\n]{5,100}?)*)/,
    /([А-ЯЁа-яё]+[,\s]+[А-ЯЁа-яё]+[,\s]+(?:ул|улица|проспект|пр|переулок|пер|площадь|пл|бульвар|б-р)[^,\n]{5,100}?)/i
  ];

  for (const pattern of addressPatterns) {
    const match = description.match(pattern);
    if (match) {
      const address = match[1].trim();
      // Проверяем, что это действительно адрес (содержит индекс или адресные слова)
      if (address.length > 10 && (address.match(/^\d{6}/) || address.match(/(?:ул|улица|проспект|пр|переулок|пер|площадь|пл|бульвар|б-р|дом|д\.|квартира|кв\.|офис|оф\.)/i))) {
        result.address = address;
        break;
      }
    }
  }

  // Извлекаем кадастровый номер
  // Паттерны: XX:XX:XXXXXX:XX или просто набор цифр с двоеточиями
  // Также ищем после слов "кадастровый номер", "кадастр", "кадастровый"
  const cadastralPatterns = [
    /кадастровый\s+номер[:\s]*([\d:]+(?:\d|:)+)/i,
    /кадастр[:\s]*([\d:]+(?:\d|:)+)/i,
    /кадастровый[:\s]*([\d:]+(?:\d|:)+)/i,
    /([\d]{2}:[\d]{2}:[\d]{6,}:[\d]{1,})/, // Формат XX:XX:XXXXXX:XX
    /([\d]{2}:[\d]{2}:[\d]{4,}:[\d]{1,})/, // Формат XX:XX:XXXX:XX
    /([\d]{2}:[\d]{2}:[\d]{2,}:[\d]{1,})/, // Формат XX:XX:XX:XX
    /([\d]{10,})/ // Просто длинный номер (10+ цифр подряд)
  ];

  for (const pattern of cadastralPatterns) {
    const match = description.match(pattern);
    if (match) {
      const cadastral = match[1].trim();
      // Проверяем, что это действительно кадастровый номер (содержит двоеточия или достаточно длинный)
      if (cadastral.includes(':') || cadastral.length >= 10) {
        result.cadastralNumber = cadastral;
        break;
      }
    }
  }

  return result;
};

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
        console.log('DocumentAnalysis: applying recommendations:', recommendedActs);

        // Устанавливаем рекомендуемый тип лица
        if (recommendedActs.entityType) {
          setEntityType(recommendedActs.entityType as EntityType);
        }

        // Устанавливаем рекомендуемый тип залога
        if (recommendedActs.collateralOption) {
          setCollateralOption(recommendedActs.collateralOption as CollateralOption);
        }

        // Устанавливаем рекомендуемые акты
        if (recommendedActs.recommendedActIds && recommendedActs.recommendedActIds.length > 0) {
          setSelectedActs(prevActs => {
            const updatedActs = prevActs.map(act => ({
              ...act,
              selected: recommendedActs.recommendedActIds!.includes(act.id)
            }));
            console.log('DocumentAnalysis: applied recommended acts:', recommendedActs.recommendedActIds);
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
        console.log('DocumentAnalysis: timeout reached, stopping analysis');
        setIsAnalyzing(false);
        setError('Превышено время ожидания анализа документа');
      }
    }, 25000); // 25 секунд

    return () => clearTimeout(timeout);
  }, [isAnalyzing]);

  useEffect(() => {
    // Анализ уже выполнен в DocumentUpload, данные переданы через props
    if (documentData) {
      console.log('DocumentAnalysis: documentData received:', documentData);

      if (propExtractedData) {
        // Используем данные, переданные через props
        console.log('DocumentAnalysis: received extractedData:', propExtractedData);
        console.log('DocumentAnalysis: obligations from extractedData:', propExtractedData.obligations);

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
              console.log(`DocumentAnalysis: извлеченные данные из описания залога ${idx + 1}:`, extractedData);

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
          console.log(`DocumentAnalysis: обработано ${initialCollaterals.length} предметов залога из backend`);
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
          console.log('DocumentAnalysis: извлеченные данные из описания залога:', extractedData);

          const collateral: Collateral = {
            ...defaultCollateral(),
            collateralType: detectedType,
            objectName: detectedType !== 'other' ? (mortgageCollateralDescription.length < 200 ? mortgageCollateralDescription : mortgageCollateralDescription.substring(0, 200)) : '',
            otherDescription: mortgageCollateralDescription,
            address: extractedData.address || '',
            cadastralNumber: extractedData.cadastralNumber || ''
          };
          initialCollaterals = [collateral];
          console.log('DocumentAnalysis: создан залог из mortgageCollateralDescription1221:', collateral);
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
            ogrnip: pf.ogrnip || pf.ogrn || '',
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
        console.log('DocumentAnalysis: setting full analysisResult:', fullAnalysisResult);
        console.log('DocumentAnalysis: obligations in fullAnalysisResult:', fullAnalysisResult.obligations);
        setAnalysisResult(fullAnalysisResult);

        const fields = propExtractedData.fields || {};
        console.log('DocumentAnalysis: fields from extractedData:', fields);

        // Устанавливаем статичные значения и фильтруем undefined
        const cleanFields: Record<string, string> = {};
        Object.keys(fields).forEach(key => {
          if (fields[key] !== undefined && fields[key] !== null) {
            cleanFields[key] = String(fields[key]);
            console.log(`DocumentAnalysis: setting field ${key} = ${cleanFields[key]}`);
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
        console.log('DocumentAnalysis: cleanFields after processing:', cleanFields);
        setEditedFields(cleanFields);
        setIsAnalyzing(false);
      } else {
        // Fallback: получаем данные из electronAPI
        console.log('DocumentAnalysis: no propExtractedData, trying electronAPI');
        const extractedData = (window as any).electronAPI?.getExtractedData();
        if (extractedData) {
          console.log('DocumentAnalysis: got data from electronAPI:', extractedData);
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
          console.log('DocumentAnalysis: no data from electronAPI either');
        }
        setIsAnalyzing(false);
      }
    } else {
      console.log('DocumentAnalysis: no documentData');
      setIsAnalyzing(false);
    }
  }, [documentData, propExtractedData]);

  // Функция для форматирования сумм
  const formatAmount = (amount: string | number | undefined): string => {
    if (!amount) return '';
    const num = typeof amount === 'string' ? parseFloat(amount.replace(/[^\d.,]/g, '').replace(',', '.')) : amount;
    if (isNaN(num)) return String(amount);
    // Форматируем с пробелами для тысяч, но без символа валюты
    return new Intl.NumberFormat('ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      useGrouping: true
    }).format(num).replace(/\s/g, ' ');
  };

  // Функция для парсинга суммы из форматированной строки
  const parseAmount = (formattedAmount: string): string => {
    // Убираем все кроме цифр, точки и запятой
    return formattedAmount.replace(/[^\d.,]/g, '').replace(',', '.');
  };

  // Функция для обработки изменения суммы с форматированием при потере фокуса
  const handleAmountChange = (fieldName: string, value: string) => {
    // Сохраняем сырое значение (только цифры, точка или запятая)
    const rawValue = value.replace(/[^\d.,]/g, '').replace(',', '.');
    handleFieldChange(fieldName, rawValue);
  };

  // Функция для форматирования при потере фокуса
  const handleAmountBlur = (fieldName: string, value: string) => {
    const rawValue = value.replace(/[^\d.,]/g, '').replace(',', '.');
    if (rawValue && !isNaN(parseFloat(rawValue))) {
      const formatted = formatAmount(rawValue);
      handleFieldChange(fieldName, rawValue); // Сохраняем сырое значение для дальнейшей обработки
    }
  };

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
    ogrnip: 'ogrnip', birthDate: 'birthDate', birthPlace: 'birthPlace', snils: 'snils'
  };

  const addDebtor = () => {
    if (!analysisResult) return;
    const newDebtor: Debtor = {
      id: `debtor-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: '', address: '', inn: '', ogrnip: '', birthDate: '', birthPlace: '', snils: ''
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
    if (analysisResult) {
      // Определяем финальный тип лица: выбранный пользователем или автоматически определенный
      const finalEntityType: 'individual' | 'legal' = entityType
        ? (entityType === 'ip' || entityType === 'kfh' ? 'individual' : (entityType === 'legal' ? 'legal' : 'individual'))
        : (analysisResult.entityType || 'individual');

      // Объединяем извлеченные данные с отредактированными полями
      // Приоритет у отредактированных полей
      const updatedData: ExtractedData = {
        ...analysisResult,
        // Используем выбранный пользователем тип лица (с преобразованием для совместимости)
        entityType: finalEntityType,
        fields: {
          ...analysisResult.fields,
          ...editedFields,
          // Сохраняем выбранные параметры в полях для передачи (оригинальный выбор пользователя)
          selectedEntityType: entityType || undefined,
          selectedCollateralOption: collateralOption || undefined,
          selectedActsIds: selectedActs.filter(a => a.selected).map(a => a.id).join(',') || undefined,
          selectedActsData: JSON.stringify(selectedActs.filter(a => a.selected)) || undefined
        },
        collaterals: analysisResult.collaterals || [],
        thirdParties: analysisResult.thirdParties || [],
        debtors: analysisResult.debtors || []
      };

      // Преобразуем ФИО судьи в формат "Фамилия И.О."
      if (updatedData.fields && updatedData.fields.judge) {
        updatedData.fields.judge = formatJudgeName(updatedData.fields.judge);
        console.log('DocumentAnalysis: преобразовано ФИО судьи:', updatedData.fields.judge);
      }

      // Убеждаемся, что все суммы передаются корректно
      // Синхронизируем loanDebt и principalDebt перед отправкой
      if (updatedData.fields) {
        if (updatedData.fields.loanDebt && !updatedData.fields.principalDebt) {
          updatedData.fields.principalDebt = updatedData.fields.loanDebt;
          updatedData.fields.principalDebt13 = updatedData.fields.loanDebt;
        } else if (updatedData.fields.principalDebt && !updatedData.fields.loanDebt) {
          updatedData.fields.loanDebt = updatedData.fields.principalDebt;
        }

        // Синхронизируем другие поля сумм
        if (updatedData.fields.interest && !updatedData.fields.interest14) {
          updatedData.fields.interest14 = updatedData.fields.interest;
        }
        if (updatedData.fields.interest14 && !updatedData.fields.interest) {
          updatedData.fields.interest = updatedData.fields.interest14;
        }

        if (updatedData.fields.forfeit && !updatedData.fields.forfeit15) {
          updatedData.fields.forfeit15 = updatedData.fields.forfeit;
        }
        if (updatedData.fields.forfeit15 && !updatedData.fields.forfeit) {
          updatedData.fields.forfeit = updatedData.fields.forfeit15;
        }

        if (updatedData.fields.penalties && !updatedData.fields.forfeit15) {
          updatedData.fields.forfeit15 = updatedData.fields.penalties;
          updatedData.fields.forfeit = updatedData.fields.penalties;
        }

        if (updatedData.fields.stateDuty && !updatedData.fields.stateDuty16) {
          updatedData.fields.stateDuty16 = updatedData.fields.stateDuty;
        }
        if (updatedData.fields.stateDuty16 && !updatedData.fields.stateDuty) {
          updatedData.fields.stateDuty = updatedData.fields.stateDuty16;
        }
      }

      console.log('DocumentAnalysis: sending updated data:', updatedData);
      console.log('DocumentAnalysis: editedFields:', editedFields);
      console.log('DocumentAnalysis: updatedData.fields:', updatedData.fields);
      console.log('DocumentAnalysis: creditorName in updatedData.fields:', updatedData.fields?.creditorName);
      console.log('DocumentAnalysis: inn in updatedData.fields:', updatedData.fields?.inn);
      console.log('DocumentAnalysis: loanDebt in updatedData.fields:', updatedData.fields?.loanDebt);
      console.log('DocumentAnalysis: principalDebt in updatedData.fields:', updatedData.fields?.principalDebt);
      console.log('DocumentAnalysis: stateDuty in updatedData.fields:', updatedData.fields?.stateDuty);
      console.log('DocumentAnalysis: judge in updatedData.fields:', updatedData.fields?.judge);
      console.log('DocumentAnalysis: date in updatedData.fields:', updatedData.fields?.date);
      onAnalysisComplete(updatedData);
    }
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

  const detectedEntityType =
    analysisResult.entityType ||
    (analysisResult.fields && (analysisResult.fields as any).entityType) ||
    'individual';

  const renderEntityIndicator = (label: string, active: boolean) => (
    <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
      <Box
        sx={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          bgcolor: active ? 'success.main' : 'grey.400',
          mr: 1
        }}
      />
      <Typography variant="body2" color={active ? 'text.primary' : 'text.secondary'}>
        {label}
      </Typography>
    </Box>
  );

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
                {recommendationsApplied && (analysisResult as any)?.recommendedActs?.entityType && (
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

            {/* Выбор залога */}
            <Box sx={{ mb: 4 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', mb: 0 }}>
                  Выбор залога
                </Typography>
                {recommendationsApplied && (analysisResult as any)?.recommendedActs?.collateralOption && (
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
                            (analysisResult as any)?.recommendedActs?.recommendedActIds?.includes(act.id);
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
                            (analysisResult as any)?.recommendedActs?.recommendedActIds?.includes(act.id);
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
                            (analysisResult as any)?.recommendedActs?.recommendedActIds?.includes(act.id);
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
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Судебная информация
                </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Название суда:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.courtName || ''}
                        onChange={(e) => handleFieldChange('courtName', e.target.value)}
                    size="small"
                    margin="dense"
                        placeholder="Арбитражный суд Ростовской области"
                  />
                    </Box>
                </Grid>

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер дела:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.caseNumber || ''}
                        onChange={(e) => handleFieldChange('caseNumber', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                    </Box>
                </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Судья:</Typography>
                      <FormControl fullWidth size="small" margin="dense">
                        <Select
                          value={editedFields.judge || ''}
                          onChange={(e) => handleFieldChange('judge', e.target.value)}
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

                <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер обособленного спора:</Typography>
                  <TextField
                    fullWidth
                        value={editedFields.separateDisputeNumber22 ?? ''}
                        onChange={(e) => handleFieldChange('separateDisputeNumber22', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                    </Box>
                  </Grid>
                </Grid>
              </Box>
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Даты и сроки */}
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
                        onChange={(e) => handleFieldChange('date', e.target.value)}
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
                        onChange={(e) => handleFieldChange('courtSubmissionDate24', e.target.value)}
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
                        onChange={(e) => handleFieldChange('applicationReceiptDate23', e.target.value)}
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
                        onChange={(e) => handleFieldChange('objectionsDeadline18', e.target.value)}
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
                        onChange={(e) => handleFieldChange('considerationDeadline19', e.target.value)}
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
                        onChange={(e) => handleFieldChange('withoutMovementDeadline20', e.target.value)}
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
                        onChange={(e) => handleFieldChange('courtHearingDateTime99', e.target.value)}
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
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Данные должника */}
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Данные должника
                </Typography>
                {(analysisResult?.debtors || []).map((debtor: Debtor, index: number) => (
                  <Card key={debtor.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
                    {(analysisResult?.debtors?.length || 0) > 1 && (
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                          Должник {index + 1}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => removeDebtor(index)}
                          aria-label="Удалить должника"
                          sx={{ color: 'text.secondary' }}
                        >
                          <CloseIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    )}
                    <Grid container spacing={2}>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО/наименование:</Typography>
                          <TextField
                            fullWidth
                            value={debtor.name || ''}
                            onChange={(e) => updateDebtor(index, 'name', e.target.value)}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес должника:</Typography>
                          <TextField
                            fullWidth
                            value={debtor.address || ''}
                            onChange={(e) => updateDebtor(index, 'address', e.target.value)}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН:</Typography>
                          <TextField
                            fullWidth
                            value={debtor.inn || ''}
                            onChange={(e) => updateDebtor(index, 'inn', e.target.value)}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ОГРНИП:</Typography>
                          <TextField
                            fullWidth
                            value={debtor.ogrnip || ''}
                            onChange={(e) => updateDebtor(index, 'ogrnip', e.target.value)}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Город/место рождения:</Typography>
                          <TextField
                            fullWidth
                            value={debtor.birthPlace ?? ''}
                            onChange={(e) => updateDebtor(index, 'birthPlace', e.target.value)}
                            size="small"
                            margin="dense"
                            placeholder="например: г. Москва"
                          />
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата рождения:</Typography>
                          <TextField
                            fullWidth
                            type="date"
                            value={toInputDate(debtor.birthDate)}
                            onChange={(e) => updateDebtor(index, 'birthDate', fromInputDate(e.target.value))}
                            size="small"
                            margin="dense"
                            InputLabelProps={{ shrink: true }}
                          />
                        </Box>
                      </Grid>
                    </Grid>
                  </Card>
                ))}
                <Button
                  startIcon={<AddIcon />}
                  onClick={addDebtor}
                  variant="outlined"
                  size="small"
                  sx={{ mt: 1 }}
                >
                  Добавить должника
                </Button>
              </Box>
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Информация о кредиторе */}
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Информация о кредиторе
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Кредитор:</Typography>
                      <FormControl fullWidth size="small" margin="dense">
                        <Select
                          value={matchBankKey(editedFields.creditorName) || (editedFields.creditorName ? 'OTHER' : '')}
                          onChange={(e) => handleCreditorChange(e.target.value)}
                          displayEmpty
                        >
                          <MenuItem value="">
                            <em>Выберите банк</em>
                          </MenuItem>
                          {BANK_NAMES.map((bankName) => (
                            <MenuItem key={bankName} value={bankName}>
                              {bankName}
                            </MenuItem>
                          ))}
                          <MenuItem value="OTHER">
                            <em>Другой банк (ввести вручную)</em>
                          </MenuItem>
                        </Select>
                      </FormControl>
                      {!matchBankKey(editedFields.creditorName) ? (
                        <Box sx={{ mt: 1, ...LABEL_OVERLAP_BOX }}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Название кредитора:</Typography>
                          <TextField
                            fullWidth
                            value={editedFields.creditorName || ''}
                            onChange={(e) => handleFieldChange('creditorName', e.target.value)}
                            size="small"
                            margin="dense"
                            placeholder="Введите название банка вручную"
                          />
                        </Box>
                      ) : null}
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Юридический адрес кредитора:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.creditorAddress || ''}
                        onChange={(e) => handleFieldChange('creditorAddress', e.target.value)}
                        size="small"
                        margin="dense"
                        placeholder="117312, г. Москва, ул. Вавилова, д. 19"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ОГРН кредитора:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.creditorOgrn || ''}
                        onChange={(e) => handleFieldChange('creditorOgrn', e.target.value)}
                        size="small"
                        margin="dense"
                        placeholder="1027700132195"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН кредитора:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.creditorInn || ''}
                        onChange={(e) => handleFieldChange('creditorInn', e.target.value)}
                        size="small"
                        margin="dense"
                        placeholder="7707083893"
                      />
                    </Box>
                  </Grid>
                </Grid>
              </Box>
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Арбитражный управляющий */}
              <Box sx={{ ...BLOCK_BOX_SX, mt: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Арбитражный управляющий
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                    <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО:</Typography>
                    <TextField
                      fullWidth
                      value={editedFields.managerName || ''}
                      onChange={(e) => handleFieldChange('managerName', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Box>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                    <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:</Typography>
                    <TextField
                      fullWidth
                      value={editedFields.managerAddress || ''}
                      onChange={(e) => handleFieldChange('managerAddress', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Box>
                  </Grid>
                </Grid>
              </Box>
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Третьи лица */}
              <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Третьи лица
                </Typography>
                {(analysisResult?.thirdParties || []).map((thirdParty: ThirdParty, index: number) => (
                  <Card key={thirdParty.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                        Третье лицо {index + 1}
                      </Typography>
                      <IconButton
                        size="small"
                        onClick={() => removeThirdParty(index)}
                        aria-label="Удалить третье лицо"
                        sx={{ color: 'text.secondary' }}
                      >
                        <CloseIcon fontSize="small" />
                      </IconButton>
                    </Box>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ФИО/наименование :</Typography>
                    <TextField
                      fullWidth
                            value={thirdParty.name || ''}
                            onChange={(e) => updateThirdParty(index, 'name', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                        </Box>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата рождения:</Typography>
                    <TextField
                      fullWidth
                            type="date"
                            value={toInputDate(thirdParty.birthDate)}
                            onChange={(e) => updateThirdParty(index, 'birthDate', fromInputDate(e.target.value))}
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
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:</Typography>
                          <TextField
                            fullWidth
                            value={thirdParty.address || ''}
                            onChange={(e) => updateThirdParty(index, 'address', e.target.value)}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>ИНН:</Typography>
                          <TextField
                            fullWidth
                            value={thirdParty.inn || ''}
                            onChange={(e) => updateThirdParty(index, 'inn', e.target.value)}
                            size="small"
                            margin="dense"
                          />
              </Box>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>СНИЛС:</Typography>
                          <TextField
                            fullWidth
                            value={thirdParty.snils || ''}
                            onChange={(e) => updateThirdParty(index, 'snils', e.target.value)}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                      </Grid>
                    </Grid>
                  </Card>
                ))}
                <Button
                  startIcon={<AddIcon />}
                  onClick={addThirdParty}
                  variant="outlined"
                  size="small"
                  sx={{ mt: 1 }}
                >
                  Добавить третье лицо
                </Button>
              </Box>
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Финансовые данные */}
              <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Финансовые данные
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Ссудная задолженность (просроченный основной долг):</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.principalDebt || editedFields.loanDebt || ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('principalDebt', value);
                          handleFieldChange('loanDebt', value);
                        }}
                        onBlur={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          if (value && !isNaN(parseFloat(value))) {
                            const formatted = formatAmount(value);
                            // Не форматируем в поле, оставляем сырое значение для удобства редактирования
                          }
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Проценты:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.interest || ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('interest', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Штрафные санкции:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.penalties || ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('penalties', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Неустойка:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.forfeit || ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('forfeit', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Общая сумма долга:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.totalDebt || ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('totalDebt', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Банкротная госпошлина:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.stateDuty16 ?? editedFields.stateDuty ?? ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('stateDuty16', value);
                          handleFieldChange('stateDuty', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Ссудная госпошлина:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.loanStateDuty17 ?? ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('loanStateDuty17', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Комиссия Банка:</Typography>
                      <TextField
                        fullWidth
                        value={editedFields.bankCommission || ''}
                        onChange={(e) => {
                          const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                          handleFieldChange('bankCommission', value);
                        }}
                        size="small"
                        margin="dense"
                        placeholder="0.00"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <Box sx={LABEL_OVERLAP_BOX}>
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ПП депозит:</Typography>
                      <TextField
                        fullWidth
                        type="date"
                        value={toInputDate(editedFields.ppDepositDate80)}
                        onChange={(e) => handleFieldChange('ppDepositDate80', fromInputDate(e.target.value))}
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
                      <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Дата ПП ГП:</Typography>
                      <TextField
                        fullWidth
                        type="date"
                        value={toInputDate(editedFields.ppStateDutyDate81)}
                        onChange={(e) => handleFieldChange('ppStateDutyDate81', fromInputDate(e.target.value))}
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
                </Grid>

                <Grid item xs={12} md={6} sx={{ display: 'flex', minWidth: 0 }}>
              {/* Блок обязательств */}
              <Box sx={{ ...BLOCK_BOX_SX, mt: 3, width: '100%' }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                    Обязательства
                  </Typography>
                {(analysisResult?.obligations || []).map((obligation: Obligation, index: number) => (
                    <Card key={obligation.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                        Обязательство {index + 1}
                      </Typography>
                      <IconButton
                        size="small"
                        onClick={() => removeObligation(index)}
                        aria-label="Удалить обязательство"
                        sx={{ color: 'text.secondary' }}
                      >
                        <CloseIcon fontSize="small" />
                      </IconButton>
                    </Box>
                      <Grid container spacing={2}>
                        <Grid item xs={12} sm={4}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Номер договора:</Typography>
                          <TextField
                            fullWidth
                            value={obligation.contractNumber || ''}
                            onChange={(e) => {
                              const updatedObligations = [...(analysisResult.obligations || [])];
                              updatedObligations[index] = { ...obligation, contractNumber: e.target.value };
                              setAnalysisResult({ ...analysisResult, obligations: updatedObligations });
                            }}
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
                            onChange={(e) => {
                              const updatedObligations = [...(analysisResult.obligations || [])];
                              updatedObligations[index] = { ...obligation, contractDate: fromInputDate(e.target.value) };
                              setAnalysisResult({ ...analysisResult, obligations: updatedObligations });
                            }}
                            size="small"
                            margin="dense"
                            InputLabelProps={{
                              shrink: true,
                            }}
                          />
                        </Box>
                        </Grid>
                        <Grid item xs={12} sm={4}>
                        <Box sx={LABEL_OVERLAP_BOX}>
                          <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Тип обязательства:</Typography>
                          <TextField
                            fullWidth
                            value={obligation.obligationType || ''}
                            onChange={(e) => {
                              const updatedObligations = [...(analysisResult.obligations || [])];
                              updatedObligations[index] = { ...obligation, obligationType: e.target.value };
                              setAnalysisResult({ ...analysisResult, obligations: updatedObligations });
                            }}
                            size="small"
                            margin="dense"
                          />
                        </Box>
                        </Grid>
                      </Grid>
                    </Card>
                  ))}
                <Button
                  startIcon={<AddIcon />}
                  onClick={addObligation}
                  variant="outlined"
                  size="small"
                  sx={{ mt: 1 }}
                >
                  Добавить обязательство
                </Button>
                </Box>
                </Grid>

                {/* Залог */}
                <Grid item xs={12} sx={{ display: 'flex', minWidth: 0 }}>
                  <Box sx={{ ...BLOCK_BOX_SX, width: '100%', mt: 2 }}>
                    <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                      Залог
                    </Typography>
                    {(analysisResult?.collaterals || []).map((collateral: Collateral, index: number) => (
                      <Card key={collateral.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                            Залог {index + 1}
                          </Typography>
                          <IconButton
                            size="small"
                            onClick={() => removeCollateral(index)}
                            aria-label="Удалить залог"
                            sx={{ color: 'text.secondary' }}
                          >
                            <CloseIcon fontSize="small" />
                          </IconButton>
                        </Box>
                        <Grid container spacing={2}>
                          {/* Описание предмета залога — только для типа «Иное».
                              Для недвижимости/авто описание не показываем. */}
                          {collateral.collateralType === 'other' && collateral.otherDescription && collateral.otherDescription.trim() && (
                <Grid item xs={12}>
                              <Box sx={LABEL_OVERLAP_BOX}>
                                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Описание предмета залога:</Typography>
                  <TextField
                    fullWidth
                                  multiline
                                  rows={4}
                    size="small"
                    margin="dense"
                                  value={collateral.otherDescription || ''}
                                  onChange={(e) => updateCollateral(index, 'otherDescription', e.target.value)}
                                  placeholder="Описание предмета залога"
                                />
                              </Box>
                            </Grid>
                          )}
                          <Grid item xs={12} sm={6}>
                            <Box sx={LABEL_OVERLAP_BOX}>
                              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Наименование объекта:</Typography>
                              <TextField
                                fullWidth
                                size="small"
                                margin="dense"
                                value={collateral.objectName || ''}
                                onChange={(e) => updateCollateral(index, 'objectName', e.target.value)}
                              />
                            </Box>
                          </Grid>
                          <Grid item xs={12} sm={6}>
                            <Box sx={LABEL_OVERLAP_BOX}>
                              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Залоговая стоимость:</Typography>
                              <TextField
                                fullWidth
                                size="small"
                                margin="dense"
                                value={collateral.collateralValue || ''}
                                onChange={(e) => updateCollateral(index, 'collateralValue', e.target.value)}
                                placeholder="0.00"
                              />
                            </Box>
                          </Grid>
                          <Grid item xs={12}>
                            <Box sx={LABEL_OVERLAP_BOX}>
                              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Тип залога:</Typography>
                              <FormControl fullWidth size="small" margin="dense">
                                <Select
                                  value={collateral.collateralType || 'real_estate'}
                                  onChange={(e) => updateCollateral(index, 'collateralType', e.target.value as CollateralType)}
                                >
                                  <MenuItem value="real_estate">Недвижимость</MenuItem>
                                  <MenuItem value="auto">Транспортное средство</MenuItem>
                                  <MenuItem value="other">Иное</MenuItem>
                                </Select>
                              </FormControl>
                            </Box>
                          </Grid>
                          {collateral.collateralType === 'real_estate' && (
                            <>
                              <Grid item xs={12} sm={6}>
                                <Box sx={LABEL_OVERLAP_BOX}>
                                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Кадастровый номер:</Typography>
                                  <TextField
                                    fullWidth
                                    size="small"
                                    margin="dense"
                                    value={collateral.cadastralNumber || ''}
                                    onChange={(e) => updateCollateral(index, 'cadastralNumber', e.target.value)}
                                  />
                                </Box>
                              </Grid>
                              <Grid item xs={12} sm={6}>
                                <Box sx={LABEL_OVERLAP_BOX}>
                                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Адрес:</Typography>
                                  <TextField
                                    fullWidth
                                    size="small"
                                    margin="dense"
                                    value={collateral.address || ''}
                                    onChange={(e) => updateCollateral(index, 'address', e.target.value)}
                                  />
                                </Box>
                              </Grid>
                            </>
                          )}
                          {collateral.collateralType === 'auto' && (
                            <>
                              <Grid item xs={12} sm={6}>
                                <Box sx={LABEL_OVERLAP_BOX}>
                                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>VIN:</Typography>
                                  <TextField
                                    fullWidth
                                    size="small"
                                    margin="dense"
                                    value={collateral.vin || ''}
                                    onChange={(e) => updateCollateral(index, 'vin', e.target.value)}
                                  />
                                </Box>
                              </Grid>
                              <Grid item xs={12} sm={6}>
                                <Box sx={LABEL_OVERLAP_BOX}>
                                  <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Марка / модель:</Typography>
                                  <TextField
                                    fullWidth
                                    size="small"
                                    margin="dense"
                                    value={collateral.brandModel || ''}
                                    onChange={(e) => updateCollateral(index, 'brandModel', e.target.value)}
                                  />
                                </Box>
                              </Grid>
                            </>
                          )}
                          {/* Для типа "other" показываем поле описания, если оно пустое или уже заполнено */}
                          {collateral.collateralType === 'other' && (
                            <Grid item xs={12}>
                              <Box sx={LABEL_OVERLAP_BOX}>
                                <Typography variant="body2" sx={LABEL_OVERLAP_SX}>Описание:</Typography>
                                <TextField
                                  fullWidth
                    multiline
                                  rows={4}
                                  size="small"
                                  margin="dense"
                                  value={collateral.otherDescription || ''}
                                  onChange={(e) => updateCollateral(index, 'otherDescription', e.target.value)}
                                  placeholder="Опишите предмет залога"
                                />
                              </Box>
                            </Grid>
                          )}
                        </Grid>
                      </Card>
                    ))}
                    <Button
                      startIcon={<AddIcon />}
                      onClick={addCollateral}
                      variant="outlined"
                      size="small"
                      sx={{ mt: 1 }}
                    >
                      Добавить залог
                    </Button>
                  </Box>
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
