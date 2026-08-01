import React from 'react';
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
import { ExtractedData, SelectedAct, TemplateType } from '../../types';
import { useGenerateDocument } from './hooks/useGenerateDocument';
import { useDownloadDocument } from './hooks/useDownloadDocument';
import TemplatePreview from './TemplatePreview';
import { buildMortgagePackage } from './lib/mortgagePackage';

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
  // Логика генерации/скачивания вынесена в хуки фичи preview (см. features/preview/hooks).
  const { isGenerating, generationResult, generate } = useGenerateDocument(
    extractedData,
    selectedTemplate,
    onDocumentGenerated
  );
  const { isDownloading, downloadMessage, download, dismissMessage } = useDownloadDocument();

  const handleGenerateDocument = generate;
  const handleDownloadDocument = () => download(generationResult);

  const getFieldValue = (fieldName: string) => {
    return extractedData.fields[fieldName] || 'Не указано';
  };

  // Ипотека не пользуется каталогом актов: пакет фиксированный (5 штук), а
  // selectedActsData заполняет только банкротный ActSelectionSection. Без этой
  // ветки предпросмотр показывал чужие акты либо пустоту.
  const isMortgage = (extractedData.fields as any)?.documentCategory === 'mortgage';
  const mortgageActs = buildMortgagePackage({
    mortgageKind: extractedData.mortgageKind,
    fields: extractedData.fields as Record<string, string | undefined>,
  });

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
                  {/* Ипотека: фиксированный пакет из 5 актов */}
                  {isMortgage && (
                    <Grid item xs={12}>
                      <Card variant="outlined" sx={{ backgroundColor: 'common.white', width: '100%' }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                            Будут сформированы {mortgageActs.length} актов
                          </Typography>
                          <List dense>
                            {mortgageActs.map((act, i) => (
                              <ListItem key={act.id} sx={{ py: 0.25 }}>
                                <ListItemIcon sx={{ minWidth: 28 }}>
                                  <DocumentIcon fontSize="small" color="primary" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={`${i + 1}. ${act.name}`}
                                  primaryTypographyProps={{ variant: 'body2' }}
                                />
                              </ListItem>
                            ))}
                          </List>
                        </CardContent>
                      </Card>
                    </Grid>
                  )}

                  {/* Окна по каждому акту (банкротный каталог) */}
                  {!isMortgage && getSelectedActs().filter((a) => a?.selected).map((act) => {
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
                    <TemplatePreview
                      extractedData={extractedData}
                      templateId={selectedTemplate.id}
                    />
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

                {/* Выбранные акты, которые сгенерировать не удалось (нет шаблона/ветки маппинга) */}
                {generationResult.warnings && generationResult.warnings.length > 0 && (
                  <Alert severity="warning" sx={{ mb: 3, textAlign: 'left' }}>
                    <Typography variant="body2" sx={{ fontWeight: 'bold', mb: 1 }}>
                      Сгенерированы не все выбранные акты:
                    </Typography>
                    {generationResult.warnings.map((warning) => (
                      <Typography key={warning} variant="body2" component="div">
                        • {warning}
                      </Typography>
                    ))}
                  </Alert>
                )}

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
                    onClose={dismissMessage}
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
