# -*- coding: utf-8 -*-
"""
Применение текстовых правок пользователя к DOCX с сохранением исходной вёрстки.

Сценарий convert-шага: пользователь правит ПЛОСКИЙ текст (тот же, что уходит в
анализ), а «Скачать с правками» должен отдать DOCX с оригинальной вёрсткой
конвертера, где правки вставлены в соответствующие абзацы/ячейки.

Сопоставление построчное: текст предпросмотра — это _extract_text_from_docx
анализатора, где ПЕРВЫМИ идут строки тела (абзацы, затем ячейки таблиц) в том
же порядке, что и объекты python-docx. Поэтому N первых строк текста
детерминированно маппятся на объекты тела; правки этих строк применяются
заменой текста абзаца (форматирование первого run'а сохраняется). Правки строк
за пределами тела (колонтитулы, надписи, сноски) в DOCX не переносятся — они
влияют только на анализ.
"""
import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from docx import Document
from docx.table import _Cell
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """Заменяет текст абзаца, сохраняя стиль абзаца и формат первого run'а."""
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    elif text:
        paragraph.add_run(text)


def _insert_paragraph_after(anchor: Paragraph, text: str) -> Paragraph:
    """Новый абзац сразу после anchor (тот же стиль абзаца)."""
    new_p = anchor._p.makeelement(anchor._p.tag, {})
    anchor._p.addnext(new_p)
    new_par = Paragraph(new_p, anchor._parent)
    new_par.style = anchor.style
    new_par.add_run(text)
    return new_par


class _LineTarget:
    """Строка предпросмотра объект DOCX, куда её правка применяется."""

    def __init__(self, paragraph: Paragraph, cell: Optional[_Cell] = None):
        self.paragraph = paragraph
        self.cell = cell  # не None — строка живёт в ячейке таблицы


def _body_line_targets(doc: Document) -> Tuple[List[str], List[_LineTarget]]:
    """
    Строки тела документа в порядке _extract_text_from_docx (абзацы, затем
    ячейки таблиц) + их объекты. Пустые абзацы/ячейки пропускаются — как в
    экстракторе.
    """
    lines: List[str] = []
    targets: List[_LineTarget] = []

    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            lines.append(paragraph.text.strip())
            targets.append(_LineTarget(paragraph))

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if not cell.text.strip():
                    continue
                # cell.text == '\n'.join(текстов абзацев ячейки); экстрактор
                # кладёт cell.text.strip() одной частью при split('\n') это
                # строки соответствующих абзацев без пустых краёв.
                cell_paragraph_texts = [p.text for p in cell.paragraphs]
                first = 0
                last = len(cell_paragraph_texts) - 1
                while first <= last and not cell_paragraph_texts[first].strip():
                    first += 1
                while last >= first and not cell_paragraph_texts[last].strip():
                    last -= 1
                for idx in range(first, last + 1):
                    text = cell_paragraph_texts[idx]
                    lines.append(text.strip() if idx in (first, last) else text)
                    targets.append(_LineTarget(cell.paragraphs[idx], cell))

    return lines, targets


def apply_text_edits(docx_path: str, edited_text: str, original_text: str) -> Document:
    """
    Вставляет правки пользователя в DOCX, сохраняя вёрстку.

    docx_path      — исходный DOCX (оригинал конвертера);
    edited_text    — текст после правок пользователя;
    original_text  — текст, который показывался пользователю (extract_text
                     этого же DOCX) — база для diff'а.

    Возвращает изменённый Document (сохранение — на вызывающей стороне).
    """
    doc = Document(docx_path)
    body_lines, targets = _body_line_targets(doc)

    original_lines = original_text.split("\n")
    edited_lines = edited_text.split("\n")

    # Строки тела — префикс полного текста; если это не так (неожиданный
    # формат), применяем только совпавшую часть, не портя документ.
    body_len = len(body_lines)
    if original_lines[:body_len] != body_lines:
        matched = 0
        while (matched < body_len
               and matched < len(original_lines)
               and original_lines[matched] == body_lines[matched]):
            matched += 1
        logger.warning(
            "docx_edit: строки тела разошлись с текстом предпросмотра "
            f"(совпало {matched} из {body_len}) — правки применяются частично"
        )
        body_len = matched

    matcher = SequenceMatcher(None, original_lines, edited_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        # Замены: попарно старая строка -> новая
        pair_count = min(i2 - i1, j2 - j1) if tag == "replace" else 0
        for k in range(pair_count):
            oi = i1 + k
            if oi < body_len:
                _set_paragraph_text(targets[oi].paragraph, edited_lines[j1 + k])

        # Удалённые строки (delete или излишек replace) — очищаем абзац
        for oi in range(i1 + pair_count, i2):
            if oi < body_len:
                _set_paragraph_text(targets[oi].paragraph, "")

        # Добавленные строки (insert или излишек replace) — после якоря
        extra = edited_lines[j1 + pair_count : j2]
        if extra:
            anchor_idx = min(max(i1 + pair_count - 1, 0), body_len - 1)
            if body_len == 0:
                continue
            anchor = targets[anchor_idx]
            if anchor.cell is not None:
                for text in extra:
                    _set_paragraph_text(anchor.cell.add_paragraph(), text)
            else:
                prev = anchor.paragraph
                for text in extra:
                    prev = _insert_paragraph_after(prev, text)

    return doc
