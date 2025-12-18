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
  Paper
} from '@mui/material';
import { ArrowBack as BackIcon, CheckCircle as CheckIcon } from '@mui/icons-material';
import { DocumentData, ExtractedData, Obligation } from '../types';

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
        const fullAnalysisResult = {
          ...propExtractedData,
          obligations: propExtractedData.obligations || []
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
        cleanFields.courtName = "Арбитражный суд Ростовской области";
        // creditorName берется из извлеченных данных (маркер [987])
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
          cleanFields.courtName = "Арбитражный суд Ростовской области";
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
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(num);
  };

  // Функция для парсинга суммы из форматированной строки
  const parseAmount = (formattedAmount: string): string => {
    return formattedAmount.replace(/[^\d.,]/g, '').replace(',', '.');
  };

  const handleFieldChange = (fieldName: string, value: string) => {
    setEditedFields(prev => ({
      ...prev,
      [fieldName]: value
    }));
  };

  const handleContinue = () => {
    if (analysisResult) {
      const updatedData: ExtractedData = {
        ...analysisResult,
        fields: editedFields || {}
      };
      onAnalysisComplete(updatedData);
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'success';
    if (confidence >= 0.6) return 'warning';
    return 'error';
  };

  const getConfidenceLabel = (confidence: number) => {
    if (confidence >= 0.8) return 'Высокая';
    if (confidence >= 0.6) return 'Средняя';
    return 'Низкая';
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
          Анализ документа
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Информация о документе */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
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

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Тип должника:
                </Typography>
                {renderEntityIndicator('Физ лицо', detectedEntityType !== 'legal')}
                {renderEntityIndicator('Юр лицо', detectedEntityType === 'legal')}
              </Box>

              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Уверенность анализа:
                </Typography>
                <Chip
                  label={`${getConfidenceLabel(analysisResult.confidence || 0)} (${((analysisResult.confidence || 0) * 100).toFixed(0)}%)`}
                  color={getConfidenceColor(analysisResult.confidence || 0) as any}
                  size="small"
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Извлеченные данные */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Извлеченные данные
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Проверьте и при необходимости отредактируйте извлеченные данные
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="ФИО/название должника"
                    value={editedFields.debtorName || editedFields.applicantName || ''}
                    onChange={(e) => handleFieldChange('debtorName', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Адрес должника"
                    value={editedFields.applicantAddress || ''}
                    onChange={(e) => handleFieldChange('applicantAddress', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>


                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Название суда"
                    value={editedFields.courtName || 'Арбитражный суд Ростовской области'}
                    onChange={(e) => handleFieldChange('courtName', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Номер дела"
                    value={editedFields.caseNumber || ''}
                    onChange={(e) => handleFieldChange('caseNumber', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>


                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Кредитор"
                    value={editedFields.creditorName || 'ПАО Сбербанк'}
                    onChange={(e) => handleFieldChange('creditorName', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Основной долг"
                    value={formatAmount(editedFields.principalDebt)}
                    onChange={(e) => handleFieldChange('principalDebt', parseAmount(e.target.value))}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Ссудная задолженность"
                    value={formatAmount(editedFields.loanDebt)}
                    onChange={(e) => handleFieldChange('loanDebt', parseAmount(e.target.value))}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Проценты"
                    value={formatAmount(editedFields.interest)}
                    onChange={(e) => handleFieldChange('interest', parseAmount(e.target.value))}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Штрафные санкции"
                    value={formatAmount(editedFields.penalties)}
                    onChange={(e) => handleFieldChange('penalties', parseAmount(e.target.value))}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Неустойка"
                    value={formatAmount(editedFields.forfeit)}
                    onChange={(e) => handleFieldChange('forfeit', parseAmount(e.target.value))}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Общая сумма долга"
                    value={formatAmount(editedFields.totalDebt)}
                    onChange={(e) => handleFieldChange('totalDebt', parseAmount(e.target.value))}
                    size="small"
                    margin="dense"
                  />
                </Grid>
              </Grid>

              {/* Финансовый управляющий */}
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Финансовый управляющий
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="ФИО финансового управляющего"
                      value={editedFields.managerName || ''}
                      onChange={(e) => handleFieldChange('managerName', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Адрес проживания"
                      value={editedFields.managerAddress || ''}
                      onChange={(e) => handleFieldChange('managerAddress', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                </Grid>
              </Box>

              {/* Третьи лица */}
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Третьи лица
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="ФИО третьего лица"
                      value={editedFields.thirdPartyName || ''}
                      onChange={(e) => handleFieldChange('thirdPartyName', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Адрес проживания"
                      value={editedFields.thirdPartyAddress || ''}
                      onChange={(e) => handleFieldChange('thirdPartyAddress', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                </Grid>
              </Box>

              {/* Блок обязательств */}
              {(() => {
                console.log('DocumentAnalysis: rendering obligations:', analysisResult?.obligations);
                console.log('DocumentAnalysis: obligations length:', analysisResult?.obligations?.length);
                return null;
              })()}
              {analysisResult?.obligations && analysisResult.obligations.length > 0 && (
                <Box sx={{ mt: 3 }}>
                  <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>
                    Обязательства
                  </Typography>
                  {analysisResult.obligations.map((obligation: Obligation, index: number) => (
                    <Card key={obligation.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
                      <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                        Обязательство {index + 1}
                      </Typography>
                      <Grid container spacing={2}>
                        <Grid item xs={12} sm={4}>
                          <TextField
                            fullWidth
                            label="Номер договора"
                            value={obligation.contractNumber}
                            size="small"
                            margin="dense"
                            disabled
                          />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <TextField
                            fullWidth
                            label="Дата договора"
                            value={obligation.contractDate}
                            size="small"
                            margin="dense"
                            disabled
                          />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <TextField
                            fullWidth
                            label="Тип обязательства"
                            value={obligation.obligationType}
                            size="small"
                            margin="dense"
                            disabled
                          />
                        </Grid>
                      </Grid>
                    </Card>
                  ))}
                </Box>
              )}

              <Grid container spacing={2} sx={{ mt: 1 }}>

                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Дополнительная информация"
                    value={editedFields.additionalInfo || ''}
                    onChange={(e) => handleFieldChange('additionalInfo', e.target.value)}
                    size="small"
                    margin="dense"
                    multiline
                    rows={3}
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
        >
          Продолжить
        </Button>
      </Box>
    </Box>
  );
};

export default DocumentAnalysis;
