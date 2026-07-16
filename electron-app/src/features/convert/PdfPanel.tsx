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
        // LEGACY-билд намеренно: обычный pdfjs 6.x зовёт Map.prototype.getOrInsertComputed
        // (свежий TC39-proposal), которого нет в Chromium 140 из Electron 38 — на
        // первом же getDocument() падало «getOrInsertComputed is not a function».
        // В legacy-сборку вшит core-js-полифилл. Воркер в public/ — тоже legacy.
        const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
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

          // Свой canvas на КАЖДУЮ страницу: переиспользование одного canvas между
          // page.render() в pdfjs v6 оставляло средние страницы пустыми (баг
          // Андрея). Страница отдаётся как <img> (PNG), затем canvas сразу
          // освобождается — живым остаётся максимум один, лимит памяти не растёт.
          const canvas = document.createElement('canvas');
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          const context = canvas.getContext('2d');
          if (!context) continue;
          await page.render({ canvas, canvasContext: context, viewport }).promise;
          if (cancelled) return;

          const img = document.createElement('img');
          img.src = canvas.toDataURL('image/png');
          img.width = viewport.width;
          img.height = viewport.height;
          img.style.display = 'block';
          img.style.marginBottom = '8px';
          img.style.boxShadow = '0 1px 4px rgba(0,0,0,0.3)';
          img.style.maxWidth = '100%';
          container.appendChild(img);
          page.cleanup();
          canvas.width = 0;
          canvas.height = 0;
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
