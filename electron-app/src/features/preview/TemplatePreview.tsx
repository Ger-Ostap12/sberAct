import React from 'react';
import { Box, Typography } from '@mui/material';
import { ExtractedData } from '../../types';
import { TEMPLATE_PREVIEW_SPECS, PreviewRow, TemplatePreviewSpec } from './templatePreviewSpecs';

interface TemplatePreviewProps {
  extractedData: ExtractedData;
  templateId: string;
  /**
   * Кастомные рендереры для шаблонов, чей предпросмотр не укладывается в
   * декларативную модель строк (передаёт DocumentPreview). Ключ — id шаблона.
   */
  customRenderers?: Record<string, () => React.ReactElement>;
}

const specById = new Map<string, TemplatePreviewSpec>(
  TEMPLATE_PREVIEW_SPECS.map((s) => [s.id, s])
);

/** Одна строка предпросмотра. Разметка воспроизводит исходный getTemplatePreview 1:1. */
const RowView: React.FC<{
  row: PreviewRow;
  getFieldValue: (name: string) => string;
  obligationsCount: number;
}> = ({ row, getFieldValue, obligationsCount }) => {
  switch (row.kind) {
    case 'field':
      return (
        <Typography variant="body2" paragraph>
          <strong>{row.label}</strong> {getFieldValue(row.field)}
          {row.unit ? ` ${row.unit}` : ''}
        </Typography>
      );
    case 'count':
      return (
        <Typography variant="body2" paragraph>
          <strong>{row.label}</strong> {obligationsCount}
        </Typography>
      );
    case 'contract':
      return (
        <Typography variant="body2" paragraph>
          <strong>{row.label}</strong> №{getFieldValue(row.numberField)} от {getFieldValue(row.dateField)}
        </Typography>
      );
    case 'tpl': {
      // Разбиваем шаблон на чередующиеся литералы и плейсхолдеры {поле}, рендерим
      // отдельными узлами — так структура DOM совпадает с исходным JSX
      // `{getFieldValue(a)} текст {getFieldValue(b)}` (важно для snapshot-сверки).
      const parts = row.template.split(/(\{\w+\})/).filter((p) => p !== '');
      return (
        <Typography variant="body2" paragraph>
          <strong>{row.label}</strong>{' '}{parts.map((part, i) => {
            const m = part.match(/^\{(\w+)\}$/);
            return m ? (
              <React.Fragment key={i}>{getFieldValue(m[1])}</React.Fragment>
            ) : (
              part
            );
          })}
        </Typography>
      );
    }
    case 'text':
      return (
        <Typography variant="body2" paragraph>
          {row.text}
        </Typography>
      );
    default:
      return null;
  }
};

/**
 * Декларативный предпросмотр судебного акта по шаблону. Пришёл на смену
 * гигантской функции getTemplatePreview (25+ веток if/else) — теперь данные
 * (TEMPLATE_PREVIEW_SPECS) отделены от разметки, добавить шаблон = добавить запись.
 */
const TemplatePreview: React.FC<TemplatePreviewProps> = ({
  extractedData,
  templateId,
  customRenderers,
}) => {
  const custom = customRenderers?.[templateId];
  if (custom) return custom();

  const spec = specById.get(templateId);
  if (!spec) {
    // Дефолт из исходного getTemplatePreview для незнакомого шаблона.
    return (
      <Typography variant="body2" color="text.secondary">
        Предварительный просмотр недоступен для данного шаблона
      </Typography>
    );
  }

  const getFieldValue = (name: string): string =>
    extractedData.fields[name] || 'Не указано';
  const obligationsCount = extractedData.obligations?.length || 0;

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        {spec.title}
      </Typography>
      {spec.rows.map((row, index) => (
        <RowView
          key={index}
          row={row}
          getFieldValue={getFieldValue}
          obligationsCount={obligationsCount}
        />
      ))}
    </Box>
  );
};

export default TemplatePreview;
