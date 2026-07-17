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
  /** Выбранные акты, которые сгенерировать не удалось (нет шаблона/ветки маппинга). */
  warnings?: string[];
}

export interface DownloadMessage {
  type: 'success' | 'error';
  text: string;
}
