import React, { useState } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box, Container, Typography, AppBar, Toolbar } from '@mui/material';
import { LocalOffer as DocumentIcon } from '@mui/icons-material';
import DocumentUpload from './components/DocumentUpload';
import DocumentAnalysis from './components/DocumentAnalysis';
import TemplateSelection from './components/TemplateSelection';
import DocumentPreview from './components/DocumentPreview';
import { DocumentData, TemplateType, ExtractedData } from './types';

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
  const [currentStep, setCurrentStep] = useState<'upload' | 'analysis' | 'template' | 'preview'>('upload');
  const [documentData, setDocumentData] = useState<DocumentData | null>(null);
  const [extractedData, setExtractedData] = useState<ExtractedData | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateType | null>(null);
  const [generatedDocument, setGeneratedDocument] = useState<string | null>(null);

  const handleDocumentUploaded = (data: DocumentData, analysisResult?: any) => {
    console.log('App: handleDocumentUploaded called with:', { data, analysisResult });
    setDocumentData(data);
    if (analysisResult && analysisResult.data) {
      console.log('App: setting extractedData to:', analysisResult.data);
      console.log('App: obligations in analysisResult.data:', analysisResult.data.obligations);
      setExtractedData(analysisResult.data);
    } else {
      console.log('App: no analysisResult.data, analysisResult:', analysisResult);
    }
    setCurrentStep('analysis');
  };

  const handleAnalysisComplete = (data: ExtractedData) => {
    setExtractedData(data);
    setCurrentStep('template');
  };

  const handleTemplateSelected = (template: TemplateType) => {
    setSelectedTemplate(template);
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
  };

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 'upload':
        return <DocumentUpload onDocumentUploaded={handleDocumentUploaded} />;
      case 'analysis':
        return (
          <DocumentAnalysis
            documentData={documentData!}
            extractedData={extractedData || undefined}
            onAnalysisComplete={handleAnalysisComplete}
            onBack={() => setCurrentStep('upload')}
          />
        );
      case 'template':
        return (
          <TemplateSelection
            extractedData={extractedData!}
            onTemplateSelected={handleTemplateSelected}
            onBack={() => setCurrentStep('analysis')}
          />
        );
      case 'preview':
        return (
          <DocumentPreview
            extractedData={extractedData!}
            selectedTemplate={selectedTemplate!}
            onDocumentGenerated={handleDocumentGenerated}
            onBack={() => setCurrentStep('template')}
            onNewDocument={resetToUpload}
          />
        );
      default:
        return <DocumentUpload onDocumentUploaded={handleDocumentUploaded} />;
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static" elevation={0} sx={{ backgroundColor: 'white', color: 'primary.main' }}>
          <Toolbar>
            <DocumentIcon sx={{ mr: 2, fontSize: 32 }} />
            <Typography variant="h4" component="div" sx={{ flexGrow: 1, fontWeight: 600 }}>
              SberAct Document Generator
            </Typography>
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
