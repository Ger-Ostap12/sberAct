import { SxProps, Theme } from '@mui/material/styles';

// Стили формы, перенесённые 1:1 из DocumentAnalysis. Подпись «наложена» на верхнюю
// границу поля (граница визуально пропадает под текстом метки).

/** Обёртка поля: относительное позиционирование под абсолютную метку. */
export const LABEL_OVERLAP_BOX: SxProps<Theme> = { position: 'relative', pt: 1.5 };

/** Рамочный контейнер логического блока (секции формы). */
export const BLOCK_BOX_SX: SxProps<Theme> = {
  width: '100%',
  boxSizing: 'border-box',
  border: '1px solid',
  borderColor: 'divider',
  borderRadius: 1,
  p: 2,
};

/** Метка, наложенная на верхнюю границу поля. */
export const LABEL_OVERLAP_SX: SxProps<Theme> = {
  position: 'absolute',
  left: 14,
  top: 12,
  transform: 'translateY(-50%)',
  backgroundColor: 'background.paper',
  pl: 0.5,
  pr: 1,
  zIndex: 1,
  fontSize: '0.875rem',
  color: 'text.secondary',
};

/** Карточка редактируемой сущности (должник/обязательство/залог/третье лицо). */
export const CARD_SX: SxProps<Theme> = {
  mb: 2,
  p: 2,
  border: '1px solid #e0e0e0',
};

/** Шапка карточки: заголовок слева, кнопка удаления справа. */
export const CARD_HEADER_SX: SxProps<Theme> = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  mb: 1,
};

/** Заголовок карточки. */
export const CARD_TITLE_SX: SxProps<Theme> = {
  fontWeight: 'bold',
  color: 'primary.main',
};

/** Кнопка удаления в шапке карточки. */
export const CARD_REMOVE_BTN_SX: SxProps<Theme> = { color: 'text.secondary' };

/** Заголовок логического блока-секции формы. */
export const SECTION_TITLE_SX: SxProps<Theme> = { mb: 2, color: 'primary.main' };
