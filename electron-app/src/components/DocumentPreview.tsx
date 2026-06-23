import React, { useState } from 'react';
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
  Divider,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemIcon
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  CheckCircle as CheckIcon,
  Download as DownloadIcon,
  Add as AddIcon,
  Description as DocumentIcon
} from '@mui/icons-material';
import { ExtractedData, SelectedAct, TemplateType } from '../types';

interface DocumentPreviewProps {
  extractedData: ExtractedData;
  selectedTemplate: TemplateType;
  onDocumentGenerated: (documentPath: string) => void;
  onBack: () => void;
  onNewDocument: () => void;
}

const DocumentPreview: React.FC<DocumentPreviewProps> = ({
  extractedData,
  selectedTemplate,
  onDocumentGenerated,
  onBack,
  onNewDocument
}) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [generationResult, setGenerationResult] = useState<{
    success: boolean;
    documentId?: string;
    documentPath?: string;
    documents?: any;
    documentIds?: string[];
    count?: number;
    error?: string;
  } | null>(null);

  const handleGenerateDocument = async () => {
    try {
      setIsGenerating(true);
      setGenerationResult(null);

      // Генерируем документ через Electron API
      if (!extractedData || !extractedData.fields) {
        throw new Error('Нет данных для генерации документа');
      }

      if (!selectedTemplate) {
        throw new Error('Не выбран шаблон документа');
      }

      // Подготавливаем данные для генерации, включая obligations
      console.log('DocumentPreview: extractedData:', extractedData);
      console.log('DocumentPreview: extractedData.fields:', extractedData.fields);
      console.log('DocumentPreview: extractedData.obligations:', extractedData.obligations);
      console.log('DocumentPreview: type of obligations:', typeof extractedData.obligations);

      const generationData = {
        ...extractedData.fields,
        // sourceDocumentType из полей анализа (если есть) приоритетнее, чтобы не терять корректную классификацию
        sourceDocumentType: (extractedData.fields as any)?.sourceDocumentType || extractedData.documentType,
        obligations: extractedData.obligations || []
      };

      console.log('DocumentPreview: generating document with:', {
        template_type: selectedTemplate.id,
        data: generationData
      });
      console.log('DocumentPreview: generationData.obligations:', generationData.obligations);

      const generationResult = await (window as any).electronAPI.generateDocument({
        template_type: selectedTemplate.id,
        data: generationData
      });

      if (generationResult.success) {
        // Проверяем, генерируется ли один документ или несколько
        if (generationResult.documents && generationResult.document_ids) {
          // Генерируется несколько документов
          setGenerationResult({
            success: true,
            documents: generationResult.documents,
            documentIds: generationResult.document_ids,
            count: generationResult.count
          });
          console.log('Generated multiple documents:', generationResult.documents);
        } else {
          // Генерируется один документ (старый формат)
          setGenerationResult({
            success: true,
            documentId: generationResult.document_id,
            documentPath: generationResult.file_path
          });
          onDocumentGenerated(generationResult.file_path);
        }
      } else {
        // Показываем конкретное сообщение об ошибке из API
        setGenerationResult({
          success: false,
          error: generationResult.error || 'Ошибка при генерации документа'
        });
        return;
      }
    } catch (err: any) {
      console.error('Error generating document:', err);
      setGenerationResult({
        success: false,
        error: err?.message || err?.error || 'Ошибка при генерации документа'
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownloadDocument = async () => {
    setIsDownloading(true);
    setDownloadMessage(null);

    try {
      // Проверяем доступность Electron API
      console.log('[DocumentPreview] Checking Electron API availability...');
      console.log('[DocumentPreview] window.electronAPI exists:', !!(window as any).electronAPI);

      if (!(window as any).electronAPI) {
        console.error('[DocumentPreview] Electron API is not available!');
        throw new Error('Electron API не доступен. Убедитесь, что приложение запущено в Electron.');
      }

      console.log('[DocumentPreview] Electron API methods:', Object.keys((window as any).electronAPI));
      console.log('[DocumentPreview] downloadAllDocuments exists:', !!(window as any).electronAPI.downloadAllDocuments);
      console.log('[DocumentPreview] downloadAllDocuments type:', typeof (window as any).electronAPI.downloadAllDocuments);

      if (!(window as any).electronAPI.downloadAllDocuments) {
        console.error('[DocumentPreview] downloadAllDocuments method is missing!');
        throw new Error('Метод downloadAllDocuments не доступен в Electron API.');
      }

      if (generationResult?.documentIds && generationResult.documentIds.length > 0) {
        console.log('[DocumentPreview] ========== STARTING DOWNLOAD ==========');
        console.log('[DocumentPreview] Downloading documents with IDs:', generationResult.documentIds);
        console.log('[DocumentPreview] Electron API object:', (window as any).electronAPI);
        console.log('[DocumentPreview] downloadAllDocuments function:', (window as any).electronAPI.downloadAllDocuments);
        console.log('[DocumentPreview] downloadAllDocuments type:', typeof (window as any).electronAPI.downloadAllDocuments);
        console.log('[DocumentPreview] Calling Electron API downloadAllDocuments...');

        // Проверяем, что метод действительно функция перед вызовом
        if (typeof (window as any).electronAPI.downloadAllDocuments !== 'function') {
          console.error('[DocumentPreview] ERROR: downloadAllDocuments is not a function!');
          console.error('[DocumentPreview] Available methods:', Object.keys((window as any).electronAPI));
          throw new Error('Метод downloadAllDocuments не является функцией. Возможно, используется fallback web-api.js');
        }

        // Скачиваем все документы через Electron API
        const downloadResult = await (window as any).electronAPI.downloadAllDocuments({
          document_ids: generationResult.documentIds.join(','),
          download_path: '' // Пустой путь - будет показан диалог выбора места сохранения
        });

        console.log('[DocumentPreview] ========== DOWNLOAD COMPLETE ==========');

        console.log('[DocumentPreview] Download result:', downloadResult);

        if (downloadResult.success) {
          const filePath = downloadResult.filePath;
          console.log('[DocumentPreview] Documents downloaded successfully to:', filePath);

          // Показываем сообщение об успехе
          setDownloadMessage({
            type: 'success',
            text: filePath
              ? `Документы успешно сохранены в: ${filePath}`
              : 'Документы успешно скачаны в папку загрузок'
          });
        } else {
          throw new Error(downloadResult.error || 'Ошибка скачивания документов');
        }
      } else if (generationResult?.documentId) {
        console.log('Downloading single document with ID:', generationResult.documentId);
        console.log('Using Electron API:', typeof (window as any).electronAPI.downloadDocument);
        // Скачиваем один документ через Electron API
        const downloadResult = await (window as any).electronAPI.downloadDocument(
          generationResult.documentId
        );

        if (downloadResult.success) {
          console.log('Document downloaded successfully to:', downloadResult.filePath);
          setDownloadMessage({
            type: 'success',
            text: `Документ успешно сохранен в: ${downloadResult.filePath || 'выбранную папку'}`
          });
        } else {
          throw new Error(downloadResult.error || 'Ошибка скачивания документа');
        }
      } else {
        throw new Error('Нет доступных документов для скачивания');
      }
    } catch (err: any) {
      console.error('Error downloading document:', err);
      setDownloadMessage({
        type: 'error',
        text: err?.message || 'Ошибка при скачивании документа'
      });
    } finally {
      setIsDownloading(false);
      // Автоматически скрываем сообщение через 5 секунд
      setTimeout(() => {
        setDownloadMessage(null);
      }, 5000);
    }
  };

  const getFieldValue = (fieldName: string) => {
    return extractedData.fields[fieldName] || 'Не указано';
  };

  const getSelectedActs = (): SelectedAct[] => {
    const raw = (extractedData.fields as any)?.selectedActsData;
    if (!raw) return [];
    try {
      const parsed = JSON.parse(String(raw));
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(Boolean) as SelectedAct[];
    } catch {
      return [];
    }
  };

  type DateFieldKey =
    | 'date'
    | 'courtSubmissionDate24'
    | 'applicationReceiptDate23'
    | 'objectionsDeadline18'
    | 'considerationDeadline19'
    | 'withoutMovementDeadline20'
    | 'courtHearingDateTime99';

  const DATE_FIELD_LABELS: Record<DateFieldKey, string> = {
    date: 'Дата принятия определения',
    courtSubmissionDate24: 'Дата направления в суд',
    applicationReceiptDate23: 'Дата поступления заявления в суд (согласно штампу)',
    objectionsDeadline18: 'Установка срока на предоставление возражений',
    considerationDeadline19: 'На рассмотрение заявления в срок',
    withoutMovementDeadline20: 'Срок для оставления без движения',
    courtHearingDateTime99: 'Дата и время судебного заседания',
  };

  const formatMaybeDateTime = (value: string) => {
    // datetime-local обычно "YYYY-MM-DDTHH:mm"
    if (!value || value === 'Не указано') return value;
    return value.replace('T', ' ');
  };

  const getDateFieldsForAct = (act: SelectedAct): DateFieldKey[] => {
    const keys: DateFieldKey[] = ['date'];

    const isIntermediate = act.category === 'intermediate';
    const containsNoMotion = act.name?.includes('Б/Д') || act.id?.includes('no_motion');

    // Дата направления/поступления: все, кроме Б/Д и всех промежуточных
    if (!isIntermediate && !containsNoMotion) {
      keys.push('courtSubmissionDate24', 'applicationReceiptDate23');
    }

    // Возражения / Рассмотрение / Заседание: Определение о принятии, Принятие после Б/Д
    if (act.id === 'acceptance_definition' || act.id === 'acceptance_after_no_motion') {
      keys.push('objectionsDeadline18', 'considerationDeadline19', 'courtHearingDateTime99');
    }

    // Срок для оставления без движения: все, что содержит Б/Д
    if (containsNoMotion) {
      keys.push('withoutMovementDeadline20');
    }

    // Убираем повторы (на всякий)
    return Array.from(new Set(keys));
  };

  const getTemplatePreview = () => {
    if (selectedTemplate.id === 'rtk_single_obligation') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Решение о включении в РТК (одно обязательство)
          </Typography>
          <Typography variant="body2" paragraph>
            В Арбитражный суд города Москвы
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ФИО должника:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес должника:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Ссудная задолженность:</strong> {getFieldValue('loanDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Штрафные санкции:</strong> {getFieldValue('penalties')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитор:</strong> {getFieldValue('creditorName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('debtorName')}
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'rtk_multiple_obligations') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Решение о включении в РТК (несколько обязательств)
          </Typography>
          <Typography variant="body2" paragraph>
            В Арбитражный суд города Москвы
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ФИО должника:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес должника:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Ссудная задолженность:</strong> {getFieldValue('loanDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Штрафные санкции:</strong> {getFieldValue('penalties')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Количество обязательств:</strong> {extractedData.obligations?.length || 0}
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'observation_single' || selectedTemplate.id === 'observation_multiple') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Наблюдение — комплект судебных актов ({selectedTemplate.id === 'observation_multiple' ? 'несколько обязательств' : 'одно обязательство'})
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Юридический адрес:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Количество обязательств:</strong> {extractedData.obligations?.length || 0}
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: основное определение, резолютивная часть и определение о принятии требований.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'observation_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Наблюдение с залогом — комплект судебных актов
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Юридический адрес:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Количество обязательств:</strong> {extractedData.obligations?.length || 0}
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие РТК наблюдение, наблюдение ВКЛ в РТК с залогом.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'competition_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Конкурсное производство с залогом — комплект судебных актов
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Юридический адрес:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Количество обязательств:</strong> {extractedData.obligations?.length || 0}
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие РТК конкурсное, конкурсное ВКЛ в РТК с залогом.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'initiation_physical') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Инициирование банкротства физического лица
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дата рождения:</strong> {getFieldValue('birthDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма задолженности:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН:</strong> {getFieldValue('inn')}
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие заявления, определение о введении реструктуризации долгов, определение о введении реализации имущества.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'ip_collection') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскания ИП
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИП:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРНИП:</strong> {getFieldValue('inn')} / {getFieldValue('ogrnip')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма кредита:</strong> {getFieldValue('creditAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Срок кредита:</strong> {getFieldValue('creditTermMonths')} мес.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Процентная ставка:</strong> {getFieldValue('creditInterestRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Ставка неустойки:</strong> {getFieldValue('creditPenaltyRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дата расчета задолженности:</strong> {getFieldValue('debtSnapshotDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt13')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest14')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Комиссия Банка:</strong> {getFieldValue('bankCommission')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: Решение взыскание с ИП, Принятие иска о взыскании с ИП.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'ip_collection_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскания ИП + Залог
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИП:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРНИП:</strong> {getFieldValue('inn')} / {getFieldValue('ogrnip')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма кредита:</strong> {getFieldValue('creditAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Срок кредита:</strong> {getFieldValue('creditTermMonths')} мес.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Процентная ставка:</strong> {getFieldValue('creditInterestRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Ставка неустойки:</strong> {getFieldValue('creditPenaltyRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дата расчета задолженности:</strong> {getFieldValue('debtSnapshotDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt13')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest14')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Комиссия Банка:</strong> {getFieldValue('bankCommission')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: Решение о взысканнии с ИП залог, Принятие иска о взыскании с ИП Залог.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'ip_collection_collateral_auto') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскание ИП залог авто
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИП:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРНИП:</strong> {getFieldValue('inn')} / {getFieldValue('ogrnip')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога (авто) [1221]:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма кредита:</strong> {getFieldValue('creditAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Срок кредита:</strong> {getFieldValue('creditTermMonths')} мес.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Процентная ставка:</strong> {getFieldValue('creditInterestRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Ставка неустойки:</strong> {getFieldValue('creditPenaltyRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дата расчета задолженности:</strong> {getFieldValue('debtSnapshotDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt13')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest14')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Комиссия Банка:</strong> {getFieldValue('bankCommission')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: Решение о взыскании с ИП залог авто, Принятие иска о взыскании с ИП залог авто.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'legal_collection_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскание с ЮЛ + Залог
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Организация:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРН:</strong> {getFieldValue('inn')} / {getFieldValue('ogrn')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Юридический адрес:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt13')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest14')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: Решение о взыскании с ЮЛ Залог, Принятие иска о взыскании с ЮЛ Залог.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'legal_collection_collateral_auto') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскание с ЮЛ залог авто
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Организация:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРН:</strong> {getFieldValue('inn')} / {getFieldValue('ogrn')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Юридический адрес:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога (авто):</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt13')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest14')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: Решение о взыскании с ЮЛ Залог авто, Принятие иска о взыскании с ЮЛ Залог авто.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'legal_collection') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскание с ЮЛ
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Организация:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРН:</strong> {getFieldValue('inn')} / {getFieldValue('ogrn')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Юридический адрес:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Основной долг:</strong> {getFieldValue('principalDebt13')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Проценты:</strong> {getFieldValue('interest14')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Неустойка:</strong> {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Общая сумма долга:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: Решение о взыскании с ЮЛ, Принятие иска о взыскании с ЮЛ.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'ip_enforcement_realization' || selectedTemplate.id === 'ip_enforcement_restructuring') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскание с индивидуального предпринимателя ({selectedTemplate.id.includes('realization') ? 'реализация' : 'реструктуризация'})
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИП:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРНИП:</strong> {getFieldValue('inn')} / {getFieldValue('ogrnip')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Условия кредита:</strong> {getFieldValue('creditAmount')} руб., срок {getFieldValue('creditTermMonths')} мес., ставка {getFieldValue('creditInterestRate')} %
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Просроченный долг:</strong> {getFieldValue('principalDebt13')} руб., проценты {getFieldValue('interest14')} руб., неустойка {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие иска о взыскании с ИП, решение взыскание с ИП.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'ip_enforcement_realization_collateral' || selectedTemplate.id === 'ip_enforcement_restructuring_collateral') {
      const procedureType = selectedTemplate.id.includes('realization') ? 'реализация' : 'реструктуризация';
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Взыскание с индивидуального предпринимателя ({procedureType} с залогом)
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИП:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>ИНН / ОГРНИП:</strong> {getFieldValue('inn')} / {getFieldValue('ogrnip')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Просроченный долг:</strong> {getFieldValue('principalDebt13')} руб., проценты {getFieldValue('interest14')} руб., неустойка {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Госпошлина:</strong> {getFieldValue('stateDuty16')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие РТК с залогом, решение о включении в РТК с залогом, резолютивная часть.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'physical_realization_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Реализация имущества физического лица с залогом
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дата рождения:</strong> {getFieldValue('birthDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>СНИЛС:</strong> {getFieldValue('snils')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Просроченный долг:</strong> {getFieldValue('principalDebt13')} руб., проценты {getFieldValue('interest14')} руб., неустойка {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие РТК с залогом, решение о включении в РТК с залогом, резолютивная часть.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'physical_restructuring_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Реструктуризация долгов физического лица с залогом
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дата рождения:</strong> {getFieldValue('birthDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>СНИЛС:</strong> {getFieldValue('snils')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Кредитный договор:</strong> №{getFieldValue('contractNumber')} от {getFieldValue('contractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Просроченный долг:</strong> {getFieldValue('principalDebt13')} руб., проценты {getFieldValue('interest14')} руб., неустойка {getFieldValue('forfeit15')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие РТК с залогом, решение о включении в РТК с залогом, резолютивная часть.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'kfh_observation') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            КФХ — комплект судебных актов (наблюдение)
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Глава КФХ:</strong> {getFieldValue('kfhHeadName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Количество обязательств:</strong> {extractedData.obligations?.length || 0}
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие и инициирование КФХ, наблюдение КФХ.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'kfh_observation_collateral') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            КФХ с залогом — комплект судебных актов (наблюдение с залогом)
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Глава КФХ:</strong> {getFieldValue('kfhHeadName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Адрес регистрации:</strong> {getFieldValue('applicantAddress')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Договор залога:</strong> №{getFieldValue('ipCollateralContractNumber')} от {getFieldValue('ipCollateralContractDate')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований в реестре:</strong> {getFieldValue('ipCollateralClaimAmount')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Описание предмета залога:</strong> {getFieldValue('mortgageCollateralDescription1221')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Количество обязательств:</strong> {extractedData.obligations?.length || 0}
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие и инициирование КФХ (залог), наблюдение КФХ залог.
          </Typography>
        </Box>
      );
    } else if (selectedTemplate.id === 'deceased') {
      return (
        <Box>
          <Typography variant="h6" gutterBottom>
            Умерший — комплект судебных актов
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Должник:</strong> {getFieldValue('applicantName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Суд:</strong> {getFieldValue('courtName')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Дело №:</strong> {getFieldValue('caseNumber')}
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Сумма требований:</strong> {getFieldValue('totalDebt')} руб.
          </Typography>
          <Typography variant="body2" paragraph>
            В комплект входят: принятие заявления о признании должника банкротом умерший, решение умерший.
          </Typography>
        </Box>
      );
    }

    return (
      <Typography variant="body2" color="text.secondary">
        Предварительный просмотр недоступен для данного шаблона
      </Typography>
    );
  };

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
          Предварительный просмотр
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Информация о шаблоне */}
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Выбранный шаблон
              </Typography>

              <Box sx={{ mb: 2 }}>
                <Chip
                  label={selectedTemplate.category}
                  color="primary"
                  size="small"
                  sx={{ mb: 1 }}
                />
                <Typography variant="body1" fontWeight="medium">
                  {selectedTemplate.name}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {selectedTemplate.description}
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Typography variant="body2" color="text.secondary" gutterBottom>
                Поля шаблона:
              </Typography>

              <List dense>
                {selectedTemplate.fields.map((field) => (
                  <ListItem key={field.name} sx={{ py: 0.5 }}>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      <DocumentIcon fontSize="small" color="primary" />
                    </ListItemIcon>
                    <ListItemText
                      primary={field.label}
                      secondary={getFieldValue(field.name)}
                      primaryTypographyProps={{ variant: 'body2', fontWeight: 'medium' }}
                      secondaryTypographyProps={{ variant: 'body2' }}
                    />
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* Предварительный просмотр */}
        <Grid item xs={12} md={9}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Предварительный просмотр документа
              </Typography>

              <Paper sx={{ p: 3, backgroundColor: 'grey.50', border: '1px solid', borderColor: 'grey.300' }}>
                <Grid container spacing={2}>
                  {/* Окна по каждому акту */}
                  {getSelectedActs().filter((a) => a?.selected).map((act) => {
                    const fields = getDateFieldsForAct(act);
                    return (
                      <Grid key={act.id} item xs={12}>
                        <Card
                          variant="outlined"
                          sx={{
                            backgroundColor: 'common.white',
                            width: '100%',
                          }}
                        >
                          <CardContent sx={{ pb: 2 }}>
                            <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                              {act.name}
                            </Typography>
                            <Grid container spacing={2}>
                              {fields.map((key) => (
                                <Grid key={key} item xs={12} sm={6} lg={4}>
                                  <Typography variant="body2">
                                    <strong>{DATE_FIELD_LABELS[key]}:</strong>{' '}
                                    {formatMaybeDateTime(getFieldValue(key))}
                                  </Typography>
                                </Grid>
                              ))}
                            </Grid>
                          </CardContent>
                        </Card>
                      </Grid>
                    );
                  })}

                  {/* Старый превью-блок (общий контент) */}
                  <Grid item xs={12}>
                    <Divider sx={{ my: 1 }} />
                    {getTemplatePreview()}
                  </Grid>
                </Grid>
              </Paper>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Генерация документа */}
      {!generationResult && (
        <Box sx={{ textAlign: 'center', mt: 4 }}>
          <Button
            variant="contained"
            size="large"
            onClick={handleGenerateDocument}
            disabled={isGenerating}
            startIcon={isGenerating ? <CircularProgress size={20} /> : <CheckIcon />}
            sx={{ px: 4 }}
          >
            {isGenerating ? 'Генерируем документ...' : 'Сгенерировать документ'}
          </Button>
        </Box>
      )}

      {/* Результат генерации */}
      {generationResult && (
        <Card sx={{ mt: 4 }}>
          <CardContent>
            {generationResult.success ? (
              <Box sx={{ textAlign: 'center' }}>
                <CheckIcon sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
                <Typography variant="h5" gutterBottom color="success.main">
                  {generationResult.count ? `${generationResult.count} документов успешно сгенерированы!` : 'Документ успешно сгенерирован!'}
                </Typography>
                <Typography variant="body1" sx={{ mb: 3 }}>
                  {generationResult.count ? 'Все документы готовы к скачиванию' : 'Судебный акт готов к скачиванию'}
                </Typography>

                {/* Показываем список сгенерированных документов */}
                {generationResult.documents && (
                  <Box sx={{ mb: 3, textAlign: 'left' }}>
                    <Typography variant="h6" gutterBottom>
                      Сгенерированные документы:
                    </Typography>
                    <List>
                      {Object.entries(generationResult.documents).map(([key, doc]: [string, any]) => (
                        <ListItem key={key} sx={{ py: 1 }}>
                          <ListItemIcon>
                            <DocumentIcon color="primary" />
                          </ListItemIcon>
                          <ListItemText
                            primary={doc.name}
                            secondary={`ID: ${doc.document_id}`}
                          />
                        </ListItem>
                      ))}
                    </List>
                  </Box>
                )}

                {downloadMessage && (
                  <Alert
                    severity={downloadMessage.type}
                    sx={{ mb: 2 }}
                    onClose={() => setDownloadMessage(null)}
                  >
                    {downloadMessage.text}
                  </Alert>
                )}

                <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
                  <Button
                    variant="contained"
                    size="large"
                    onClick={handleDownloadDocument}
                    disabled={isDownloading}
                    startIcon={isDownloading ? <CircularProgress size={20} /> : <DownloadIcon />}
                    sx={{ px: 4 }}
                  >
                    {isDownloading
                      ? 'Скачивание...'
                      : generationResult.count
                        ? 'Скачать все документы'
                        : 'Скачать документ'}
                  </Button>

                  <Button
                    variant="outlined"
                    size="large"
                    onClick={onNewDocument}
                    startIcon={<AddIcon />}
                    sx={{ px: 4 }}
                  >
                    Создать новый документ
                  </Button>
                </Box>
              </Box>
            ) : (
              <Box sx={{ textAlign: 'center' }}>
                <Alert severity="error" sx={{ mb: 3 }}>
                  {generationResult.error}
                </Alert>
                <Button
                  variant="outlined"
                  onClick={handleGenerateDocument}
                  startIcon={<CheckIcon />}
                >
                  Попробовать снова
                </Button>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {/* Прогресс генерации */}
      {isGenerating && (
        <Paper sx={{ p: 3, mt: 3, textAlign: 'center' }}>
          <CircularProgress sx={{ mb: 2 }} />
          <Typography variant="body1">
            Генерируем судебный акт...
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Это может занять несколько секунд
          </Typography>
        </Paper>
      )}
    </Box>
  );
};

export default DocumentPreview;
