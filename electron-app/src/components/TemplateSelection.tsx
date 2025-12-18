import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  Alert,
  CircularProgress,
  Paper,
  Radio,
  RadioGroup,
  FormControlLabel,
  FormControl,
  FormLabel,
  Grid
} from '@mui/material';
import { ArrowBack as BackIcon, CheckCircle as CheckIcon } from '@mui/icons-material';
import { ExtractedData, TemplateType } from '../types';

interface TemplateSelectionProps {
  extractedData: ExtractedData;
  onTemplateSelected: (template: TemplateType) => void;
  onBack: () => void;
}

const TemplateSelection: React.FC<TemplateSelectionProps> = ({
  extractedData,
  onTemplateSelected,
  onBack
}) => {
  const [templates, setTemplates] = useState<TemplateType[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getSourceDocumentType = () =>
    (extractedData.fields && (extractedData.fields as any).sourceDocumentType) ||
    extractedData.documentType ||
    '';

  const loadTemplates = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Имитируем загрузку шаблонов (в реальном приложении здесь будет вызов API)
      const mockTemplates: TemplateType[] = [
        {
          id: 'rtk_single_obligation',
          name: 'Решение о включении в РТК (одно обязательство)',
          description: 'Шаблон для судебного акта о включении в реестр требований кредиторов по одному обязательству',
          category: 'РТК',
          fields: [
            { name: 'applicantName', label: 'ФИО заявителя', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'debtAmount', label: 'Сумма долга', type: 'number', required: true },
            { name: 'creditorName', label: 'Кредитор', type: 'text', required: true },
            { name: 'debtorName', label: 'Должник', type: 'text', required: true }
          ]
        },
        {
          id: 'rtk_multiple_obligations',
          name: 'Решение о включении в РТК (несколько обязательств)',
          description: 'Шаблон для судебного акта о включении в реестр требований кредиторов по нескольким обязательствам',
          category: 'РТК',
          fields: [
            { name: 'applicantName', label: 'ФИО заявителя', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalAmount', label: 'Общая сумма долга', type: 'number', required: true },
            { name: 'obligationsCount', label: 'Количество обязательств', type: 'number', required: true }
          ]
        },
        {
          id: 'mortgage',
          name: 'Решение по ипотеке',
          description: 'Шаблон решения суда по ипотечному иску с предметом залога',
          category: 'Ипотека',
          fields: [
            { name: 'mortgageCourtName002', label: 'Суд [002]', type: 'text', required: true },
            { name: 'mortgageCourtAddress001', label: 'Адрес суда [001]', type: 'text', required: false },
            { name: 'mortgageRepresentative22', label: 'Представитель истца [2.2]', type: 'text', required: false },
            { name: 'mortgageCreditAmount111', label: 'Сумма кредита [111]', type: 'text', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true },
            { name: 'mortgageStartingPrice1225', label: 'Начальная цена продажи [1225]', type: 'text', required: true }
          ]
        },
        {
          id: 'initiation_physical',
          name: 'Инициирование банкротства (физ лицо)',
          description: 'Комплект актов: принятие заявления, введение реструктуризации и введение реализации имущества',
          category: 'Инициирование',
          fields: [
            { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true }
          ]
        },
        {
          id: 'initiation_legal',
          name: 'Инициирование банкротства (юр лицо)',
          description: 'Комплект актов: принятие заявления и введение наблюдения',
          category: 'Инициирование',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true },
            { name: 'debtSnapshotDate88', label: 'Дата состояния задолженности [88]', type: 'text', required: false }
          ]
        },
        {
          id: 'initiation_legal_competition_absent',
          name: 'Инициирование ЮЛ конкурсное (отсутствующий)',
          description: 'Комплект актов: принятие заявления, наблюдение и конкурсное (отсутствующий должник)',
          category: 'Инициирование',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true },
            { name: 'debtSnapshotDate88', label: 'Дата состояния задолженности [88]', type: 'text', required: false }
          ]
        },
        {
          id: 'initiation_legal_competition_liquidation',
          name: 'Инициирование ЮЛ конкурсное (ликвидируемый)',
          description: 'Комплект актов: принятие заявления, наблюдение и конкурсное (ликвидируемый должник)',
          category: 'Инициирование',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Размер задолженности', type: 'number', required: true },
            { name: 'debtSnapshotDate88', label: 'Дата состояния задолженности [88]', type: 'text', required: false }
          ]
        },
        {
          id: 'observation_single',
          name: 'Наблюдение (одно обязательство)',
          description: 'Комплект актов по процедуре наблюдения для юридического лица с одним обязательством',
          category: 'Наблюдение',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
          ]
        },
        {
          id: 'observation_multiple',
          name: 'Наблюдение (несколько обязательств)',
          description: 'Комплект актов по процедуре наблюдения для юридического лица с несколькими обязательствами',
          category: 'Наблюдение',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
          ]
        },
        {
          id: 'observation_collateral',
          name: 'Наблюдение с залогом',
          description: 'Комплект актов по процедуре наблюдения для юридического лица с залогом',
          category: 'Наблюдение',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'competition_collateral',
          name: 'Конкурсное производство с залогом',
          description: 'Комплект актов по процедуре конкурсного производства для юридического лица с залогом',
          category: 'Конкурсное',
          fields: [
            { name: 'applicantName', label: 'Наименование должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'ip_enforcement_realization',
          name: 'ИП Реализация (без залога)',
          description: 'Комплект актов для взыскания с ИП в процедуре реализации (принятие иска и решение)',
          category: 'ИП',
          fields: [
            { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
            { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
            { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
            { name: 'creditAmount', label: 'Сумма кредита', type: 'number', required: true },
            { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
            { name: 'interest14', label: 'Проценты', type: 'number', required: true }
          ]
        },
        {
          id: 'ip_enforcement_realization_collateral',
          name: 'ИП Реализация (с залогом)',
          description: 'Комплект актов для взыскания с ИП в процедуре реализации с залогом',
          category: 'ИП',
          fields: [
            { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
            { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
            { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'ip_enforcement_restructuring',
          name: 'ИП Реструктуризация (без залога)',
          description: 'Комплект актов для взыскания с ИП в процедуре реструктуризации (принятие иска и решение)',
          category: 'ИП',
          fields: [
            { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
            { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
            { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
            { name: 'creditAmount', label: 'Сумма кредита', type: 'number', required: true },
            { name: 'principalDebt13', label: 'Основной долг', type: 'number', required: true },
            { name: 'interest14', label: 'Проценты', type: 'number', required: true }
          ]
        },
        {
          id: 'ip_enforcement_restructuring_collateral',
          name: 'ИП Реструктуризация (с залогом)',
          description: 'Комплект актов для взыскания с ИП в процедуре реструктуризации с залогом',
          category: 'ИП',
          fields: [
            { name: 'applicantName', label: 'ИП (ФИО)', type: 'text', required: true },
            { name: 'inn', label: 'ИНН ИП', type: 'text', required: true },
            { name: 'ogrnip', label: 'ОГРНИП', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'physical_realization_collateral',
          name: 'Реализация ФЛ с залогом',
          description: 'Комплект актов для реализации имущества физического лица с залогом',
          category: 'Реализация',
          fields: [
            { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'physical_restructuring_collateral',
          name: 'Реструктуризация ФЛ с залогом',
          description: 'Комплект актов для реструктуризации долгов физического лица с залогом',
          category: 'Реструктуризация',
          fields: [
            { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'kfh_observation',
          name: 'КФХ',
          description: 'Комплект актов для КФХ (наблюдение): принятие заявления и введение наблюдения',
          category: 'КФХ',
          fields: [
            { name: 'applicantName', label: 'Глава КФХ ИП (ФИО)', type: 'text', required: true },
            { name: 'kfhHeadName', label: 'ФИО главы КФХ', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
          ]
        },
        {
          id: 'kfh_observation_collateral',
          name: 'КФХ с залогом',
          description: 'Комплект актов для КФХ (наблюдение с залогом): принятие заявления и введение наблюдения',
          category: 'КФХ',
          fields: [
            { name: 'applicantName', label: 'Глава КФХ ИП (ФИО)', type: 'text', required: true },
            { name: 'kfhHeadName', label: 'ФИО главы КФХ', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'ipCollateralContractNumber', label: 'Номер договора залога [0005]', type: 'text', required: true },
            { name: 'ipCollateralContractDate', label: 'Дата договора залога [0006]', type: 'text', required: true },
            { name: 'ipCollateralClaimAmount', label: 'Сумма требований [0007]', type: 'number', required: true },
            { name: 'mortgageCollateralDescription1221', label: 'Описание предмета залога [1221]', type: 'textarea', required: true }
          ]
        },
        {
          id: 'deceased',
          name: 'Умерший',
          description: 'Комплект актов для процедуры банкротства умершего должника: принятие заявления и решение',
          category: 'Умерший',
          fields: [
            { name: 'applicantName', label: 'ФИО должника', type: 'text', required: true },
            { name: 'courtName', label: 'Название суда', type: 'text', required: true },
            { name: 'caseNumber', label: 'Номер дела', type: 'text', required: true },
            { name: 'totalDebt', label: 'Сумма требований', type: 'number', required: true }
          ]
        },
      ];

      setTemplates(mockTemplates);

      // Автоматически выбираем подходящий шаблон на основе анализа
      const sourceDocumentType = getSourceDocumentType();

      if (sourceDocumentType === 'mortgage_claim') {
        setSelectedTemplateId('mortgage');
      } else if (sourceDocumentType === 'competition_collateral') {
        setSelectedTemplateId('competition_collateral');
      } else if (sourceDocumentType === 'physical_restructuring_collateral') {
        setSelectedTemplateId('physical_restructuring_collateral');
      } else if (sourceDocumentType === 'physical_realization_collateral') {
        setSelectedTemplateId('physical_realization_collateral');
      } else if (sourceDocumentType === 'ip_enforcement_realization') {
        setSelectedTemplateId('ip_enforcement_realization');
      } else if (sourceDocumentType === 'ip_enforcement_realization_collateral') {
        setSelectedTemplateId('ip_enforcement_realization_collateral');
      } else if (sourceDocumentType === 'ip_enforcement_restructuring') {
        setSelectedTemplateId('ip_enforcement_restructuring');
      } else if (sourceDocumentType === 'ip_enforcement_restructuring_collateral') {
        setSelectedTemplateId('ip_enforcement_restructuring_collateral');
      } else if (sourceDocumentType === 'ip_enforcement_statement' || sourceDocumentType === 'ip_enforcement_statement_collateral') {
        // Для обратной совместимости - по умолчанию реализация
        if (sourceDocumentType === 'ip_enforcement_statement_collateral') {
          setSelectedTemplateId('ip_enforcement_realization_collateral');
        } else {
          setSelectedTemplateId('ip_enforcement_realization');
        }
      } else if (sourceDocumentType === 'initiation_physical') {
        setSelectedTemplateId('initiation_physical');
      } else if (sourceDocumentType === 'initiation_legal') {
        setSelectedTemplateId('initiation_legal_competition_absent');
      } else if ((extractedData.fields as any)?.procedureType === 'deceased' ||
                 (extractedData.fields as any)?.procedureTypeRaw?.toLowerCase().includes('умер') ||
                 (extractedData.fields as any)?.procedureTypeRaw?.toLowerCase().includes('умерший') ||
                 (extractedData.fields as any)?.procedureTypeRaw?.toLowerCase().includes('смерть')) {
        // Процедура "умерший" - автоматически выбираем шаблон
        setSelectedTemplateId('deceased');
      } else if (extractedData.fields?.isKfh || (extractedData.fields as any)?.isKfh) {
        // КФХ - проверяем наличие залога
        const hasCollateral = extractedData.fields?.ipCollateralContractNumber ||
                             extractedData.fields?.mortgageCollateralDescription1221 ||
                             sourceDocumentType === 'observation_collateral';
        if (hasCollateral) {
          setSelectedTemplateId('kfh_observation_collateral');
        } else {
          setSelectedTemplateId('kfh_observation');
        }
      } else if (extractedData.entityType === 'legal' || extractedData.fields?.entityType === 'legal') {
        const obligationsCount = extractedData.obligations?.length || 0;
        setSelectedTemplateId(obligationsCount > 1 ? 'observation_multiple' : 'observation_single');
      } else if (sourceDocumentType === 'rtk_application' || extractedData.documentType === 'rtk_application') {
        // Определяем количество обязательств по реальным данным
        const obligationsCount = extractedData.obligations?.length || 0;
        console.log('TemplateSelection: obligations count:', obligationsCount);

        if (obligationsCount > 1) {
          setSelectedTemplateId('rtk_multiple_obligations');
          console.log('TemplateSelection: selected rtk_multiple_obligations for', obligationsCount, 'obligations');
        } else {
          setSelectedTemplateId('rtk_single_obligation');
          console.log('TemplateSelection: selected rtk_single_obligation for', obligationsCount, 'obligations');
        }
      }

      setIsLoading(false);
    } catch (err) {
      console.error('Error loading templates:', err);
      setError('Ошибка при загрузке шаблонов');
      setIsLoading(false);
    }
  }, [extractedData]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const handleTemplateSelect = (templateId: string) => {
    setSelectedTemplateId(templateId);
  };

  const handleContinue = () => {
    const selectedTemplate = templates.find(t => t.id === selectedTemplateId);
    if (selectedTemplate) {
      onTemplateSelected(selectedTemplate);
    }
  };

  const getTemplateIcon = (templateId: string) => {
    if (templateId === 'mortgage') {
      return '🏠';
    } else if (templateId.includes('kfh')) {
      return '🚜';
    } else if (templateId.includes('ip_enforcement')) {
      return '👤';
    } else if (templateId === 'initiation_physical') {
      return '⚖️';
    } else if (templateId === 'physical_realization_collateral') {
      return '💰';
    } else if (templateId === 'physical_restructuring_collateral') {
      return '🔄';
    } else if (templateId.includes('observation')) {
      return '🧾';
    } else if (templateId === 'competition_collateral') {
      return '⚖️';
    } else if (templateId.includes('single')) {
      return '📄';
    } else if (templateId.includes('multiple')) {
      return '📚';
    }
    return '📋';
  };

  const getTemplateColor = (templateId: string) => {
    if (templateId === 'mortgage') {
      return 'info';
    } else if (templateId.includes('kfh')) {
      return 'success';
    } else if (templateId.includes('ip_enforcement')) {
      return 'warning';
    } else if (templateId === 'initiation_physical') {
      return 'warning';
    } else if (templateId === 'physical_realization_collateral') {
      return 'error';
    } else if (templateId === 'physical_restructuring_collateral') {
      return 'success';
    } else if (templateId === 'competition_collateral') {
      return 'secondary';
    } else if (templateId.includes('observation')) {
      return 'success';
    } else if (templateId.includes('single')) {
      return 'primary';
    } else if (templateId.includes('multiple')) {
      return 'secondary';
    }
    return 'default';
  };

  if (isLoading) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <CircularProgress size={64} sx={{ mb: 3 }} />
        <Typography variant="h5" gutterBottom>
          Загружаем шаблоны...
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Подбираем подходящие типы судебных актов
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
          Вернуться к анализу
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto' }}>
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
          Выбор типа судебного акта
        </Typography>
      </Box>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        На основе анализа вашего заявления мы подобрали подходящие типы судебных актов.
        Выберите наиболее подходящий вариант или оставьте автоматически выбранный.
      </Typography>

      {/* Автоматический выбор */}
      <Card sx={{ mb: 3, backgroundColor: 'primary.50', border: '1px solid', borderColor: 'primary.200' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom color="primary.main">
            🎯 Автоматически подобранный шаблон
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Система проанализировала содержимое заявления и рекомендует следующий тип судебного акта:
          </Typography>

          {selectedTemplateId && (
            <Box sx={{ mt: 2, p: 2, backgroundColor: 'white', borderRadius: 1 }}>
              <Typography variant="body1" fontWeight="medium">
                {templates.find(t => t.id === selectedTemplateId)?.name}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {templates.find(t => t.id === selectedTemplateId)?.description}
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Выбор шаблона */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Выберите тип судебного акта
          </Typography>

          <FormControl component="fieldset" sx={{ width: '100%' }}>
            <FormLabel component="legend" sx={{ mb: 2 }}>
              Доступные шаблоны
            </FormLabel>

            <RadioGroup
              value={selectedTemplateId}
              onChange={(e) => handleTemplateSelect(e.target.value)}
            >
              <Grid container spacing={1.5}>
              {templates.map((template) => (
                  <Grid item xs={6} sm={4} md={3} key={template.id}>
                <Paper
                  sx={{
                        p: 1.5,
                        border: '2px solid',
                    borderColor: selectedTemplateId === template.id ? 'primary.main' : 'grey.300',
                    backgroundColor: selectedTemplateId === template.id ? 'primary.50' : 'white',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease-in-out',
                        height: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                    '&:hover': {
                      borderColor: 'primary.main',
                          backgroundColor: selectedTemplateId === template.id ? 'primary.50' : 'grey.50',
                          transform: 'translateY(-2px)',
                          boxShadow: 2
                    }
                  }}
                  onClick={() => handleTemplateSelect(template.id)}
                >
                  <FormControlLabel
                    value={template.id}
                        control={<Radio size="small" />}
                    label={
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', width: '100%', ml: 0.5 }}>
                            <Box sx={{ fontSize: 20, mb: 0.5 }}>
                          {getTemplateIcon(template.id)}
                        </Box>
                            <Typography variant="body2" fontWeight="medium" sx={{ mb: 0.5, lineHeight: 1.2 }}>
                            {template.name}
                          </Typography>
                            <Chip
                              label={template.category}
                              color={getTemplateColor(template.id) as any}
                              size="small"
                              sx={{ fontSize: '0.65rem', height: 20 }}
                            />
                      </Box>
                    }
                        sx={{ width: '100%', m: 0, alignItems: 'flex-start' }}
                  />
                </Paper>
                  </Grid>
              ))}
              </Grid>
            </RadioGroup>
          </FormControl>
        </CardContent>
      </Card>

      <Box sx={{ textAlign: 'center', mt: 4 }}>
        <Button
          variant="contained"
          size="large"
          onClick={handleContinue}
          disabled={!selectedTemplateId}
          startIcon={<CheckIcon />}
          sx={{ px: 4 }}
        >
          Продолжить
        </Button>
      </Box>
    </Box>
  );
};

export default TemplateSelection;
