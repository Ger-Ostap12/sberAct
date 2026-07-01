import React from 'react';
import { Card, Box, Typography, IconButton } from '@mui/material';
import { Close as CloseIcon } from '@mui/icons-material';
import {
  CARD_SX,
  CARD_HEADER_SX,
  CARD_TITLE_SX,
  CARD_REMOVE_BTN_SX,
} from '../styles/formStyles';

interface EditableCardProps {
  /** Заголовок карточки, напр. «Обязательство 1». */
  title: string;
  /** Обработчик удаления карточки. */
  onRemove: () => void;
  /** aria-label кнопки удаления (для доступности и тестов). */
  removeLabel: string;
  children: React.ReactNode;
}

/**
 * Карточка редактируемой сущности с шапкой (заголовок + кнопка удаления).
 * Заменяет повторяющийся блок Card+header из списков должников/обязательств/
 * залога/третьих лиц в DocumentAnalysis.
 */
const EditableCard: React.FC<EditableCardProps> = ({
  title,
  onRemove,
  removeLabel,
  children,
}) => (
  <Card sx={CARD_SX}>
    <Box sx={CARD_HEADER_SX}>
      <Typography variant="subtitle1" sx={CARD_TITLE_SX}>
        {title}
      </Typography>
      <IconButton
        size="small"
        onClick={onRemove}
        aria-label={removeLabel}
        sx={CARD_REMOVE_BTN_SX}
      >
        <CloseIcon fontSize="small" />
      </IconButton>
    </Box>
    {children}
  </Card>
);

export default EditableCard;
