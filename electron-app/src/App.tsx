import React, { useState, useEffect } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box, Container, Typography, AppBar, Toolbar, IconButton, Tooltip } from '@mui/material';
import { LocalOffer as DocumentIcon, BugReport as DevToolsIcon } from '@mui/icons-material';
import DocumentUpload from './features/upload/DocumentUpload';
import DocumentAnalysis from './features/analysis/DocumentAnalysis';
import DocumentPreview from './features/preview/DocumentPreview';
import ConvertScreen from './features/convert/ConvertScreen';
import { DocumentData, TemplateType, ExtractedData, AnalysisResult } from './types';
import { pickTemplate } from './templates';
import { getAppVersion } from './services/electronApi';
import { toggleDevTools } from './services/electronApi';

const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        },
      },
    },
  },
});

function App() {
  const [currentStep, setCurrentStep] = useState<'upload' | 'convert' | 'analysis' | 'preview'>('upload');
  const [documentData, setDocumentData] = useState<DocumentData | null>(null);
  const [extractedData, setExtractedData] = useState<ExtractedData | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateType | null>(null);
  const [generatedDocument, setGeneratedDocument] = useState<string | null>(null);
  /** PDF, ожидающий OCR-конвертации (шаг convert). */
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [appVersion, setAppVersion] = useState<string>('');

  useEffect(() => {
    getAppVersion().then(setAppVersion).catch(() => setAppVersion(''));
  }, []);

  const handleDocumentUploaded = (data: DocumentData, analysisResult?: AnalysisResult) => {
    setDocumentData(data);
    if (analysisResult?.data) {
      setExtractedData(analysisResult.data);
    }
    setCurrentStep('analysis');
  };

  // PDF идёт через конвертер: сначала предпросмотр с правкой, потом анализ
  const handlePdfSelected = (file: File) => {
    setPdfFile(file);
    setCurrentStep('convert');
  };

  const handleConvertComplete = (result: AnalysisResult) => {
    if (!pdfFile) return;
    handleDocumentUploaded(
      {
        filePath: pdfFile.name,
        fileName: pdfFile.name,
        fileSize: pdfFile.size,
        uploadDate: new Date(),
      },
      result
    );
  };

  const handleAnalysisComplete = (data: ExtractedData) => {
    setExtractedData(data);
    // Шаблон судебного акта подбирается автоматически — отдельной страницы выбора нет.
    setSelectedTemplate(pickTemplate(data));
    setCurrentStep('preview');
  };

  const handleDocumentGenerated = (documentPath: string) => {
    setGeneratedDocument(documentPath);
  };

  const resetToUpload = () => {
    setCurrentStep('upload');
    setDocumentData(null);
    setExtractedData(null);
    setSelectedTemplate(null);
    setGeneratedDocument(null);
    setPdfFile(null);
    // Конвертер намеренно НЕ гасим: его убивает сторож простоя на бэкенде
    // (CONVERTER_IDLE_TIMEOUT_S). Остановка отсюда означала холодный старт с
    // загрузкой LLM на КАЖДОМ следующем заявлении.
  };

  const handleOpenDevTools = () => {
    toggleDevTools();
  };

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 'upload':
        return (
          <DocumentUpload
            onDocumentUploaded={handleDocumentUploaded}
            onPdfSelected={handlePdfSelected}
          />
        );
      case 'convert':
        return (
          <ConvertScreen
            file={pdfFile!}
            onComplete={handleConvertComplete}
            onBack={resetToUpload}
          />
        );
      case 'analysis':
        return (
          <DocumentAnalysis
            documentData={documentData!}
            extractedData={extractedData || undefined}
            onAnalysisComplete={handleAnalysisComplete}
            onBack={() => setCurrentStep('upload')}
          />
        );
      case 'preview':
        return (
          <DocumentPreview
            extractedData={extractedData!}
            selectedTemplate={selectedTemplate!}
            onDocumentGenerated={handleDocumentGenerated}
            onBack={() => setCurrentStep('analysis')}
            onNewDocument={resetToUpload}
          />
        );
      default:
        return (
          <DocumentUpload
            onDocumentUploaded={handleDocumentUploaded}
            onPdfSelected={handlePdfSelected}
          />
        );
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static" elevation={0} sx={{ backgroundColor: 'white', color: 'primary.main' }}>
          <Toolbar>
            <DocumentIcon sx={{ mr: 2, fontSize: 32 }} />
            <Typography variant="h4" component="div" sx={{ fontWeight: 600 }}>
              SberAct Document Generator
            </Typography>
            {appVersion && (
              <Typography
                variant="body2"
                sx={{ ml: 1.5, color: 'text.secondary', fontWeight: 500 }}
              >
                v{appVersion}
              </Typography>
            )}
            <Box sx={{ flexGrow: 1 }} />
            <Tooltip title="Открыть консоль разработчика (F12)">
              <IconButton
                color="inherit"
                onClick={handleOpenDevTools}
                sx={{ ml: 2 }}
              >
                <DevToolsIcon />
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
          {renderCurrentStep()}
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default App;
