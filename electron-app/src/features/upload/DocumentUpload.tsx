import React, { useCallback, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Alert,
  CircularProgress,
  Paper
} from '@mui/material';
import { CloudUpload as UploadIcon, Description as FileIcon } from '@mui/icons-material';
import { useDropzone } from 'react-dropzone';
import { DocumentData, AnalysisResult } from '../../types';
import {
  analyzeDocument,
  selectFile,
  hasElectronAPI,
  getElectronAPI,
} from '../../services/electronApi';

interface DocumentUploadProps {
  onDocumentUploaded: (data: DocumentData, analysisResult?: AnalysisResult) => void;
  /** PDF идёт на convert-шаг (OCR + предпросмотр), а не сразу в анализ. */
  onPdfSelected?: (file: File) => void;
}

const DocumentUpload: React.FC<DocumentUploadProps> = ({ onDocumentUploaded, onPdfSelected }) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;

    const file = acceptedFiles[0];

    // Проверяем тип файла (.docx или .pdf)
    const nameLower = file.name.toLowerCase();
    if (!nameLower.endsWith('.docx') && !nameLower.endsWith('.pdf')) {
      setError('Поддерживаются только файлы формата .docx и .pdf');
      return;
    }

    // PDF — через OCR-конвертер (convert-шаг). Прогрев sidecar убран намеренно:
    // ConvertScreen монтируется сразу за onPdfSelected и сам зовёт converterStart,
    // так что выигрыш был нулевой, а параллельные вызовы плодили гонку на бэкенде
    // и глушили ошибку старта в .catch().
    if (nameLower.endsWith('.pdf') && onPdfSelected) {
      setError(null);
      setUploadedFile(file);
      onPdfSelected(file);
      return;
    }

    setError(null);
    setUploadedFile(file);
    setIsAnalyzing(true);

    try {
      // Анализируем документ (Electron — через мост, браузер — через webApi/fetch)
      const analysisResult = await analyzeDocument(file);

      if (analysisResult.success) {
        const documentData: DocumentData = {
          filePath: file.name,
          fileName: file.name,
          fileSize: file.size,
          uploadDate: new Date()
        };

        onDocumentUploaded(documentData, analysisResult);
      } else {
        setError(analysisResult.error || 'Ошибка при анализе документа');
      }
    } catch (err) {
      console.error('Error analyzing document:', err);
      setError('Ошибка при анализе документа. Попробуйте еще раз.');
    } finally {
      setIsAnalyzing(false);
    }
  }, [onDocumentUploaded, onPdfSelected]);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf']
    },
    multiple: false
  });

  const handleManualUpload = async () => {
    // Браузер: диалога по пути нет (webApi.selectFile всегда null — кнопка молча
    // «не работала»). Открываем системный выбор файла через input дропзоны;
    // выбранный файл идёт обычным onDrop-потоком (валидация + анализ).
    if (!hasElectronAPI()) {
      open();
      return;
    }
    try {
      // Electron: системный диалог по пути через мост preload.
      const filePath = await selectFile();
      if (filePath) {
        // PDF — на convert-шаг: читаем байты через мост и отдаём как File
        if (filePath.toLowerCase().endsWith('.pdf') && onPdfSelected) {
          const fileName = filePath.split(/[\\/]/).pop() || 'document.pdf';
          const bytes = getElectronAPI().readFile(filePath);
          const file = new File([new Uint8Array(bytes)], fileName, { type: 'application/pdf' });
          setError(null);
          setUploadedFile(file);
          onPdfSelected(file);
          return;
        }

        // Сразу запускаем анализ по выбранному пути
        setIsAnalyzing(true);
        setError(null);

        const analysisResult = await analyzeDocument(filePath);

        if (analysisResult.success) {
          const fileName = filePath.split(/[\\/]/).pop() || 'document.docx';
          const documentData: DocumentData = {
            filePath,
            fileName,
            fileSize: 0,
            uploadDate: new Date()
          };
          onDocumentUploaded(documentData, analysisResult);
        } else {
          setError(analysisResult.error || 'Ошибка при анализе документа');
        }
      }
    } catch (err) {
      console.error('Error selecting file:', err);
      setError('Ошибка при выборе файла');
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto' }}>
      <Typography variant="h4" component="h1" gutterBottom align="center" sx={{ mb: 4 }}>
        Загрузка заявления
      </Typography>

      <Typography variant="body1" color="text.secondary" align="center" sx={{ mb: 4 }}>
        Загрузите заявление в формате Word (.docx) или PDF для анализа. Генерация актов — в формате .docx
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <div {...getRootProps()}>
            <Box
              sx={{
                border: '2px dashed',
                borderColor: isDragActive ? 'primary.main' : 'grey.300',
                borderRadius: 2,
                p: 4,
                textAlign: 'center',
                cursor: 'pointer',
                backgroundColor: isDragActive ? 'primary.light' : 'grey.100',
                transition: 'all 0.2s ease-in-out',
                '&:hover': {
                  borderColor: 'primary.main',
                  backgroundColor: 'primary.light'
                }
              }}
            >
              <input {...getInputProps()} />

              {uploadedFile ? (
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
                  <FileIcon sx={{ fontSize: 48, color: 'primary.main', mr: 2 }} />
                  <Box>
                    <Typography variant="h6" component="div">
                      {uploadedFile.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {(((uploadedFile?.size || 0) / 1024 / 1024).toFixed(2))} MB
                    </Typography>
                  </Box>
                </Box>
              ) : (
                <UploadIcon sx={{ fontSize: 64, color: 'primary.main', mb: 2 }} />
              )}

              <Typography variant="h6" component="div" gutterBottom>
                {isDragActive ? 'Отпустите файл здесь' : 'Перетащите файл сюда или нажмите для выбора'}
              </Typography>

              <Typography variant="body2" color="text.secondary">
                Поддерживаются файлы .docx и .pdf
              </Typography>
            </Box>
          </div>
        </CardContent>
      </Card>

      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Или выберите файл вручную
        </Typography>

        <Button
          variant="outlined"
          size="large"
          onClick={handleManualUpload}
          disabled={isAnalyzing}
          startIcon={isAnalyzing ? <CircularProgress size={20} /> : null}
        >
          {isAnalyzing ? 'Анализ...' : 'Выбрать файл'}
        </Button>
      </Box>

      {isAnalyzing && (
        <Paper sx={{ p: 3, mt: 3, textAlign: 'center' }}>
          <CircularProgress sx={{ mb: 2 }} />
          <Typography variant="body1">
            Анализируем документ...
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Это может занять несколько секунд
          </Typography>
        </Paper>
      )}
    </Box>
  );
};

export default DocumentUpload;
