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
import { DocumentData } from '../types';

interface DocumentUploadProps {
  onDocumentUploaded: (data: DocumentData, analysisResult?: any) => void;
}

const DocumentUpload: React.FC<DocumentUploadProps> = ({ onDocumentUploaded }) => {
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

    setError(null);
    setUploadedFile(file);
    setIsAnalyzing(true);

    try {
      // Анализируем документ через Electron API
      const api = (window as any).electronAPI;
      if (!api || typeof api.analyzeDocument !== 'function') {
        console.error('electronAPI is not available');
        setError('Внутренняя ошибка: electronAPI не инициализирован');
        setIsAnalyzing(false);
        return;
      }
      const analysisResult = await api.analyzeDocument(file);
      console.log('DocumentUpload: analysis result:', analysisResult);
      console.log('DocumentUpload: analysisResult.success:', analysisResult.success);
      console.log('DocumentUpload: analysisResult.data:', analysisResult.data);

      if (analysisResult.success) {
        const documentData: DocumentData = {
          filePath: file.name,
          fileName: file.name,
          fileSize: file.size,
          uploadDate: new Date()
        };

        console.log('DocumentUpload: calling onDocumentUploaded with:', { documentData, analysisResult });
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
  }, [onDocumentUploaded]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf']
    },
    multiple: false
  });

  const handleManualUpload = async () => {
    try {
      const api = (window as any).electronAPI;
      if (!api) {
        setError('Electron preload не инициализирован');
        return;
      }
      const filePath = await api.selectFile();
      if (filePath) {
        // Сразу запускаем анализ по выбранному пути
        setIsAnalyzing(true);
        setError(null);

        const analysisResult = await api.analyzeDocument(filePath);
        console.log('DocumentUpload: analysis result (manual):', analysisResult);

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
