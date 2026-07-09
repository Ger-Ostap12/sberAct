import React, { useEffect, useRef, useState } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

interface PdfPanelProps {
  /** Исходный PDF — для сверки распознанного текста с оригиналом. */
  file: File;
}

/**
 * Панель исходного PDF (pdfjs-dist, полностью локально): страницы рендерятся
 * в canvas подряд с вертикальной прокруткой. pdfjs импортируется динамически —
 * ESM-пакет не попадает в общий бандл и в jest-окружение.
 */
const PdfPanel: React.FC<PdfPanelProps> = ({ file }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      const container = containerRef.current;
      if (!container) return;
      setLoading(true);
      setError(null);
      container.innerHTML = '';
      try {
        const pdfjs = await import('pdfjs-dist');
        // Worker — статическим файлом из public/ (скопирован из pdfjs-dist),
        // без бандлер-магии: работает и в CRA-dev, и в собранном Electron.
        pdfjs.GlobalWorkerOptions.workerSrc = `${process.env.PUBLIC_URL || ''}/pdf.worker.min.mjs`;

        const data = await file.arrayBuffer();
        const doc = await pdfjs.getDocument({ data }).promise;
        if (cancelled) return;

        const targetWidth = Math.max(container.clientWidth - 16, 300);
        for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
          const page = await doc.getPage(pageNum);
          if (cancelled) return;
          const unscaled = page.getViewport({ scale: 1 });
          const viewport = page.getViewport({ scale: targetWidth / unscaled.width });

          const canvas = document.createElement('canvas');
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.style.display = 'block';
          canvas.style.marginBottom = '8px';
          canvas.style.boxShadow = '0 1px 4px rgba(0,0,0,0.3)';
          const context = canvas.getContext('2d');
          if (!context) continue;
          await page.render({ canvas, canvasContext: context, viewport }).promise;
          if (cancelled) return;
          container.appendChild(canvas);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Не удалось отобразить PDF');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    render();
    return () => {
      cancelled = true;
    };
  }, [file]);

  return (
    <Box sx={{ height: '100%', overflowY: 'auto', backgroundColor: 'grey.300', p: 1 }}>
      {loading && (
        <Box sx={{ textAlign: 'center', p: 3 }}>
          <CircularProgress size={24} />
          <Typography variant="body2" color="text.secondary">
            Загружаем PDF…
          </Typography>
        </Box>
      )}
      {error && (
        <Typography variant="body2" color="error" sx={{ p: 2 }}>
          {error}
        </Typography>
      )}
      <div ref={containerRef} />
    </Box>
  );
};

export default PdfPanel;
