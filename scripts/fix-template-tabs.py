# -*- coding: utf-8 -*-
"""Разводит «слипающиеся» строки шаблонов по краям страницы.

Проблема: строки «дата ... Дело № …» и «Судья ... ФИО» разделены ПРОБЕЛАМИ
(иногда цепочкой табов по умолчанию). Пробелы рассчитаны под длину маркеров
([66], [415]), а после подстановки реальных значений длина меняется, и части
строки съезжают друг на друга: «15» августа 2026 года Дело № 2-1142/2010».

Решение то же, что применено к ипотечным решениям 01.08.2026: один символ
табуляции плюс табстоп, выровненный ПО ПРАВОМУ КРАЮ текстовой области. Тогда
правая часть всегда прижата к полю независимо от длины левой.

Табстоп ставим через API python-docx (`paragraph_format.tab_stops`), а не
вставкой XML руками: python-docx кладёт <w:tabs> в позицию, требуемую схемой
OOXML (после <w:pStyle>, до <w:jc>). Ручная вставка в начало <w:pPr> даёт файл,
который Word отвергает.

Запуск:
    python scripts/fix-template-tabs.py [--dry-run] [--templates <путь>]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Emu, Twips

# Обходим ВСЕ шаблоны, а не список: та же болезнь всплывала уже дважды — сперва
# в четырёх актах (продление упрощёнки, переход в основное производство,
# отложение, возврат РТК ГП), потом во всех Б/Д. Файлы без слипшихся строк
# скрипт просто пропускает.

# Правая часть строки, которую надо прижать к полю.
RIGHT_PART_PATTERNS = [
    re.compile(r"Дело\s*№"),      # «<дата> ⇥ Дело № [1]-[22]»
    re.compile(r"\[415\]"),        # «Судья ⇥ [415]»
]


def right_edge_twips(doc: Document) -> int:
    """Правый край текстовой области в twips (ширина страницы минус поля)."""
    section = doc.sections[0]
    # Вычитание Length даёт обычный int (EMU), у которого нет .twips — оборачиваем.
    width = Emu(section.page_width - section.left_margin - section.right_margin)
    return int(width.twips)


def split_point(text: str):
    """Начало правой части и начало разделяющего пробела перед ней.

    Разделителем считаем и пробелы (2+), и табуляцию: часть строк уже была
    разведена табами, но по табстопам ПО УМОЛЧАНИЮ (каждые 1.25 см) — правая
    часть всё равно съезжала. Такие абзацы тоже нормализуем: один таб плюс
    табстоп по правому краю. Повторный прогон ничего не портит.
    """
    for pattern in RIGHT_PART_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        left = text[: m.start()]
        stripped = left.rstrip(" \t\xa0")
        gap = left[len(stripped):]
        if not gap or (len(gap) < 2 and "\t" not in gap):
            continue  # частей не двое
        return len(stripped), m.start()
    return None


def rewrite_runs(paragraph, ws_start: int, ws_end: int) -> None:
    """Меняет пробельный промежуток [ws_start, ws_end) на один символ табуляции,
    не трогая остальной текст и форматирование runs."""
    pos = 0
    tab_written = False
    for run in paragraph.runs:
        text = run.text
        start, end = pos, pos + len(text)
        pos = end
        if end <= ws_start or start >= ws_end:
            continue  # run вне промежутка
        keep_left = text[: max(0, ws_start - start)]
        keep_right = text[max(0, ws_end - start):]
        if not tab_written:
            run.text = keep_left + "\t" + keep_right
            tab_written = True
        else:
            run.text = keep_left + keep_right


def fix_paragraph(paragraph, edge: int) -> bool:
    point = split_point(paragraph.text)
    if not point:
        return False
    ws_start, ws_end = point
    rewrite_runs(paragraph, ws_start, ws_end)
    fmt = paragraph.paragraph_format
    # Старые табстопы (LEFT на 6300) не нужны: они и не использовались, а с
    # символом табуляции сработали бы раньше правого.
    fmt.tab_stops.clear_all()
    fmt.tab_stops.add_tab_stop(Twips(edge), WD_TAB_ALIGNMENT.RIGHT)
    return True


def process(path: Path, dry_run: bool, backup_root: Path, rel: Path) -> int:
    doc = Document(str(path))
    edge = right_edge_twips(doc)
    changed = 0
    for i, paragraph in enumerate(doc.paragraphs):
        before = paragraph.text
        if fix_paragraph(paragraph, edge):
            changed += 1
            print(f"    para {i}: {before.strip()[:40]!r} -> табуляция + правый край {edge} twips")
    if changed and not dry_run:
        # Бэкап кладём ВНЕ Templates: всё содержимое этой папки уходит в сборку
        # бэкенда (SberAct.spec) и на флешку, посторонним файлам там не место.
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy(path, backup)
        doc.save(str(path))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--templates", default=str(Path(__file__).resolve().parents[1] / "Templates"))
    args = parser.parse_args()

    root = Path(args.templates)
    backup_root = Path(__file__).resolve().parents[1] / ".template-backups"
    total = 0
    for path in sorted(root.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        doc = Document(str(path))
        if not any(split_point(p.text) for p in doc.paragraphs):
            continue
        rel = path.relative_to(root)
        print(f"== {rel}")
        total += process(path, args.dry_run, backup_root, rel)
    print(f"\nисправлено абзацев: {total}{' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
