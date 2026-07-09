import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

export interface DocxPreviewEditorHandle {
  /** Корень contentEditable-области (для extractPlainText / экспорта HTML). */
  getRoot: () => HTMLDivElement | null;
}

interface DocxPreviewEditorProps {
  /** Готовый DOCX из конвертера. */
  docx: Blob;
}

/**
 * Word-подобный редактируемый предпросмотр: DOCX → HTML через mammoth
 * (локально, в браузере) → contentEditable «лист». HTML вставляется в DOM
 * один раз через ref — React не перерендеривает область и не затирает
 * правки пользователя. Обратная конвертация правок в DOCX здесь не нужна:
 * анализ ест плоский текст, а экспорт «с правками» собирается из innerHTML.
 */
const DocxPreviewEditor = forwardRef<DocxPreviewEditorHandle, DocxPreviewEditorProps>(
  ({ docx }, ref) => {
    const editorRef = useRef<HTMLDivElement | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useImperativeHandle(ref, () => ({ getRoot: () => editorRef.current }));

    useEffect(() => {
      let cancelled = false;
      const convert = async () => {
        setLoading(true);
        setError(null);
        try {
          const mammoth = (await import('mammoth/mammoth.browser')).default;
          const arrayBuffer = await docx.arrayBuffer();
          const result = await mammoth.convertToHtml({ arrayBuffer });
          if (cancelled) return;
          if (editorRef.current) {
            editorRef.current.innerHTML = result.value;
          }
        } catch (e) {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : 'Не удалось открыть DOCX');
          }
        } finally {
          if (!cancelled) setLoading(false);
        }
      };
      convert();
      return () => {
        cancelled = true;
      };
    }, [docx]);

    return (
      <Box sx={{ height: '100%', overflowY: 'auto', backgroundColor: 'grey.200', p: 2 }}>
        {loading && (
          <Box sx={{ textAlign: 'center', p: 3 }}>
            <CircularProgress size={24} />
            <Typography variant="body2" color="text.secondary">
              Открываем распознанный документ…
            </Typography>
          </Box>
        )}
        {error && (
          <Typography variant="body2" color="error" sx={{ p: 2 }}>
            {error}
          </Typography>
        )}
        <Box
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          data-testid="docx-editor"
          sx={{
            // «Лист Word»: белая страница с полями и тенью, Times New Roman
            display: loading ? 'none' : 'block',
            backgroundColor: 'white',
            maxWidth: 760,
            minHeight: 400,
            mx: 'auto',
            px: 6,
            py: 5,
            boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
            outline: 'none',
            fontFamily: '"Times New Roman", Times, serif',
            fontSize: '12pt',
            lineHeight: 1.4,
            '& table': {
              borderCollapse: 'collapse',
              width: '100%',
              my: 1,
            },
            '& td, & th': {
              border: '1px solid #999',
              padding: '2px 6px',
              verticalAlign: 'top',
            },
            '& p': { my: 0.5 },
          }}
        />
      </Box>
    );
  }
);

DocxPreviewEditor.displayName = 'DocxPreviewEditor';

export default DocxPreviewEditor;
