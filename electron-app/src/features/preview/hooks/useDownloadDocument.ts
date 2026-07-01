import { useState, useCallback } from 'react';
import {
  hasElectronAPI,
  downloadDocument,
  downloadAllDocuments,
} from '../../../services/electronApi';
import { GenerationState, DownloadMessage } from '../types';

interface UseDownloadDocument {
  isDownloading: boolean;
  downloadMessage: DownloadMessage | null;
  download: (generationResult: GenerationState | null) => Promise<void>;
  /** Скрыть сообщение вручную (крестик в Alert). */
  dismissMessage: () => void;
}

/** Через сколько мс автоматически скрыть сообщение о скачивании. */
const MESSAGE_TIMEOUT_MS = 5000;

/**
 * Скачивание сгенерированных документов (пакет или один). Логика перенесена 1:1
 * из DocumentPreview.handleDownloadDocument, очищена от отладочных логов.
 */
export const useDownloadDocument = (): UseDownloadDocument => {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState<DownloadMessage | null>(null);

  const download = useCallback(async (generationResult: GenerationState | null) => {
    setIsDownloading(true);
    setDownloadMessage(null);

    try {
      if (!hasElectronAPI()) {
        throw new Error(
          'Electron API не доступен. Убедитесь, что приложение запущено в Electron.'
        );
      }

      if (generationResult?.documentIds && generationResult.documentIds.length > 0) {
        // Пакет документов
        const result = await downloadAllDocuments({
          document_ids: generationResult.documentIds.join(','),
          download_path: '', // Пустой путь → диалог выбора места сохранения
        });
        if (result.success) {
          setDownloadMessage({
            type: 'success',
            text: result.filePath
              ? `Документы успешно сохранены в: ${result.filePath}`
              : 'Документы успешно скачаны в папку загрузок',
          });
        } else {
          throw new Error(result.error || 'Ошибка скачивания документов');
        }
      } else if (generationResult?.documentId) {
        // Один документ
        const result = await downloadDocument(generationResult.documentId);
        if (result.success) {
          setDownloadMessage({
            type: 'success',
            text: `Документ успешно сохранён в: ${result.filePath || 'выбранную папку'}`,
          });
        } else {
          throw new Error(result.error || 'Ошибка скачивания документа');
        }
      } else {
        throw new Error('Нет доступных документов для скачивания');
      }
    } catch (err) {
      const e = err as { message?: string };
      console.error('Error downloading document:', err);
      setDownloadMessage({
        type: 'error',
        text: e?.message || 'Ошибка при скачивании документа',
      });
    } finally {
      setIsDownloading(false);
      // Автоматически скрываем сообщение через 5 секунд
      setTimeout(() => setDownloadMessage(null), MESSAGE_TIMEOUT_MS);
    }
  }, []);

  const dismissMessage = useCallback(() => setDownloadMessage(null), []);

  return { isDownloading, downloadMessage, download, dismissMessage };
};
