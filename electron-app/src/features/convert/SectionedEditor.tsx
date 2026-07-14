import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { DocxSection } from '../../services/electronApi';

interface SectionedEditorProps {
  /** Секции из /docx-text — представление строк extract_text (3 блока). */
  sections: DocxSection[];
  /** Канонический текст (строки по исходному index) после любой правки. */
  onChange: (canonicalText: string) => void;
}

/**
 * Непрерывный прогон строк одного блока. Каждый блок правится независимой
 * textarea; на выходе блоки соединяются в ПОРЯДКЕ исходного `startIndex` — так
 * канонический текст байт-в-байт совпадает с extract_text (пока строки не
 * тронуты), а анализ и «Скачать с правками» работают как раньше.
 */
interface Segment {
  key: string;
  sectionId: string;
  title: string;
  startIndex: number;
  text: string;
}

/** Разбивает секции на сегменты (непрерывные прогоны по исходному index). */
function buildSegments(sections: DocxSection[]): Segment[] {
  const segments: Segment[] = [];
  for (const section of sections) {
    const lines = [...section.lines].sort((a, b) => a.index - b.index);
    let run: typeof lines = [];
    const flush = () => {
      if (run.length === 0) return;
      segments.push({
        key: `${section.id}-${run[0].index}`,
        sectionId: section.id,
        title: section.title,
        startIndex: run[0].index,
        text: run.map((l) => l.text).join('\n'),
      });
      run = [];
    };
    for (const line of lines) {
      if (run.length > 0 && line.index !== run[run.length - 1].index + 1) flush();
      run.push(line);
    }
    flush();
  }
  return segments;
}

/**
 * Textarea, растущая под содержимое: собственного скролла НЕТ — прокручивается
 * только колонка целиком (иначе непонятно, что листать). Высота = scrollHeight
 * при монтировании и на каждой правке.
 */
const AutoTextarea: React.FC<{
  value: string;
  onChange: (v: string) => void;
  testId: string;
}> = ({ value, onChange, testId }) => {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <Box
      component="textarea"
      ref={ref}
      value={value}
      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
      data-testid={testId}
      rows={1}
      sx={{
        width: '100%',
        border: '1px solid',
        borderColor: 'grey.300',
        borderRadius: 1,
        resize: 'none',
        overflow: 'hidden',
        outline: 'none',
        backgroundColor: 'white',
        boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
        px: 2,
        py: 1.5,
        fontFamily: '"Times New Roman", Times, serif',
        fontSize: '12pt',
        lineHeight: 1.5,
        '&:focus': { borderColor: 'primary.main' },
      }}
    />
  );
};

const SectionedEditor: React.FC<SectionedEditorProps> = ({ sections, onChange }) => {
  const baseSegments = useMemo(() => buildSegments(sections), [sections]);
  const [texts, setTexts] = useState<Record<string, string>>({});

  // Сброс правок при новом документе (смене секций).
  useEffect(() => {
    const initial: Record<string, string> = {};
    for (const seg of baseSegments) initial[seg.key] = seg.text;
    setTexts(initial);
  }, [baseSegments]);

  // Пересборка канонического текста: сегменты в порядке исходного startIndex.
  useEffect(() => {
    if (baseSegments.length === 0) return;
    const canonical = [...baseSegments]
      .sort((a, b) => a.startIndex - b.startIndex)
      .map((seg) => texts[seg.key] ?? seg.text)
      .join('\n');
    onChange(canonical);
  }, [texts, baseSegments, onChange]);

  // Заголовки-блоки в порядке отображения (Шапка → Основной текст → Просительная).
  const grouped = useMemo(() => {
    const order: { id: string; title: string; segs: Segment[] }[] = [];
    for (const seg of baseSegments) {
      const last = order[order.length - 1];
      if (last && last.id === seg.sectionId) last.segs.push(seg);
      else order.push({ id: seg.sectionId, title: seg.title, segs: [seg] });
    }
    return order;
  }, [baseSegments]);

  return (
    // Единственный скролл на всю колонку: блоки идут друг за другом сверху вниз.
    <Box sx={{ flex: 1, minWidth: 0, height: '100%', overflowY: 'auto', px: 1, py: 0.5 }}>
      {grouped.map((group) => (
        <Box key={`${group.id}-${group.segs[0].startIndex}`} sx={{ mb: 2.5 }}>
          <Typography
            variant="subtitle2"
            sx={{
              color: 'primary.main',
              fontWeight: 700,
              mb: 0.75,
              textTransform: 'uppercase',
              fontSize: '0.72rem',
              letterSpacing: 0.5,
            }}
          >
            {group.title}
          </Typography>
          {group.segs.map((seg) => (
            <AutoTextarea
              key={seg.key}
              value={texts[seg.key] ?? seg.text}
              onChange={(v) => setTexts((prev) => ({ ...prev, [seg.key]: v }))}
              testId={`section-${seg.sectionId}`}
            />
          ))}
        </Box>
      ))}
    </Box>
  );
};

export default SectionedEditor;
