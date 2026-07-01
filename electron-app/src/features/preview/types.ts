// Локальные типы страницы предпросмотра/генерации.

/** Нормализованное состояние результата генерации (camelCase для UI). */
export interface GenerationState {
  success: boolean;
  documentId?: string;
  documentPath?: string;
  documents?: Record<string, unknown>;
  documentIds?: string[];
  count?: number;
  error?: string;
}

export interface DownloadMessage {
  type: 'success' | 'error';
  text: string;
}
