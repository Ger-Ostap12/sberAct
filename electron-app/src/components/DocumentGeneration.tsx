import React, { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from '@mui/material';
import {
  ArrowBack,
  Download,
  Description,
  PictureAsPdf,
} from '@mui/icons-material';
import { DocumentData, DocumentType, ExtractedField } from '../types';

interface DocumentGenerationProps {
  documentData: DocumentData;
  documentTypes: DocumentType[];
  onBack: () => void;
  onComplete: () => void;
}

const DocumentGeneration: React.FC<DocumentGenerationProps> = ({
  documentData,
  documentTypes,
  onBack,
  onComplete,
}) => {
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [outputFormat, setOutputFormat] = useState<'docx' | 'pdf'>('docx');
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [savePath, setSavePath] = useState('');

  const handleGenerate = async () => {
    if (!selectedTemplate) {
      setError('Выберите тип судебного акта');
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      // В реальном приложении здесь будет вызов API
      await new Promise((resolve) => setTimeout(resolve, 3000));

      setShowExportDialog(true);
    } catch (err) {
      setError('Ошибка при генерации документа');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExport = async () => {
    try {
      const defaultPath = `Судебный_акт_${
        new Date().toISOString().split('T')[0]
      }.${outputFormat}`;
      const filePath = await (window as any).electronAPI.saveFile(defaultPath);

      if (filePath) {
        // Здесь будет сохранение файла
        onComplete();
      }
    } catch (err) {
      setError('Ошибка при сохранении файла');
    }
  };

  const getSuggestedTemplate = () => {
    // Простая логика для определения подходящего шаблона
    if (documentData.documentType.includes('bankruptcy')) {
      return documentTypes.find((t: DocumentType) =>
        t.name.toLowerCase().includes('банкротство')
      );
    }
    if (documentData.documentType.includes('inheritance')) {
      return documentTypes.find((t: DocumentType) =>
        t.name.toLowerCase().includes('наследство')
      );
    }
    return documentTypes[0];
  };

  const suggestedTemplate = getSuggestedTemplate();

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Button startIcon={<ArrowBack />} onClick={onBack} sx={{ mr: 2 }}>
          Назад
        </Button>
        <Typography variant="h4">Генерация судебного акта</Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Выбор шаблона
              </Typography>

              <FormControl fullWidth sx={{ mb: 3 }}>
                <InputLabel>Тип судебного акта</InputLabel>
                <Select
                  value={selectedTemplate}
                  onChange={(e: React.ChangeEvent<{ value: unknown }>) => setSelectedTemplate(e.target.value as string)}
                  label="Тип судебного акта"
                >
                  {documentTypes.map((type: DocumentType) => (
                    <MenuItem key={type.id} value={type.id}>
                      {type.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {suggestedTemplate && !selectedTemplate && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  Рекомендуемый тип: <strong>{suggestedTemplate.name}</strong>
                </Alert>
              )}

              <FormControl fullWidth sx={{ mb: 3 }}>
                <InputLabel>Формат экспорта</InputLabel>
                <Select
                  value={outputFormat}
                  onChange={(e: React.ChangeEvent<{ value: unknown }>) =>
                    setOutputFormat(e.target.value as 'docx' | 'pdf')
                  }
                  label="Формат экспорта"
                >
                  <MenuItem value="docx">
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Description sx={{ mr: 1 }} />
                      Word Document (.docx)
                    </Box>
                  </MenuItem>
                  <MenuItem value="pdf">
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <PictureAsPdf sx={{ mr: 1 }} />
                      PDF Document (.pdf)
                    </Box>
                  </MenuItem>
                </Select>
              </FormControl>

              <Button
                variant="contained"
                size="large"
                fullWidth
                onClick={handleGenerate}
                disabled={!selectedTemplate || isGenerating}
                startIcon={
                  isGenerating ? <CircularProgress size={20} /> : <Download />
                }
              >
                {isGenerating ? 'Генерируем...' : 'Сгенерировать документ'}
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Данные для переноса
              </Typography>

              <Box sx={{ mb: 2 }}>
                <Chip
                  label={`Тип заявления: ${documentData.documentType}`}
                  color="primary"
                  sx={{ mr: 1, mb: 1 }}
                />
                <Chip
                  label={`Уверенность: ${Math.round(
                    documentData.confidence * 100
                  )}%`}
                  color="success"
                  sx={{ mb: 1 }}
                />
              </Box>

              <Typography variant="subtitle2" gutterBottom>
                Извлеченные поля:
              </Typography>

              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {documentData.extractedFields.map((
                  field: ExtractedField,
                  index: number
                ) => (
                  <Chip
                    key={index}
                    label={`${field.name}: ${field.value}`}
                    variant="outlined"
                    size="small"
                  />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Dialog
        open={showExportDialog}
        onClose={() => setShowExportDialog(false)}
      >
        <DialogTitle>Сохранение документа</DialogTitle>
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 2 }}>
            Документ успешно сгенерирован! Выберите место для сохранения.
          </Typography>
          <TextField
            fullWidth
            label="Путь для сохранения"
            value={savePath}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSavePath(e.target.value)}
            placeholder={`Судебный_акт_${
              new Date().toISOString().split('T')[0]
            }.${outputFormat}`}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowExportDialog(false)}>Отмена</Button>
          <Button onClick={handleExport} variant="contained">
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DocumentGeneration;
