# -*- coding: utf-8 -*-
"""Прижимает колонку получателей извещения правее врезки-шапки.

Врезка с реквизитами суда стоит слева (120.35..340.35pt от края страницы), а
адреса получателей («Копия: ПАО Сбербанк …») идут обычными абзацами. Без
левого отступа их длинные строки переносились под врезку и левее неё — в акте
это выглядело как «д.29» слева от рамки и адрес ФГКУ во всю ширину под ней.

Ставим абзацам шапки левый отступ по правому краю врезки. Трогаем только
блок получателей — он идёт до первого абзаца основного текста (выключка по
ширине); сам текст письма и подпись судьи остаются на всю ширину.

Запуск:
    python scripts/fix-notice-column.py [--dry-run] [--templates <путь>]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Emu, Pt

RELATIVE_PATH = Path("ипотека/Извещение_МАРКИРОВАННЫЙ.docx")

# Врезка: margin-left 120.35pt + width 220pt (см. scripts/verify — тест
# test_notice_header_box.py следит, чтобы ширина не выросла обратно).
BOX_RIGHT_EDGE_PT = 340.35
GAP_PT = 6.0  # зазор между рамкой и текстом


def process(path: Path, dry_run: bool, backup_root: Path, rel: Path) -> int:
    doc = Document(str(path))
    left_margin_pt = Emu(doc.sections[0].left_margin).pt
    indent_pt = BOX_RIGHT_EDGE_PT - left_margin_pt + GAP_PT

    changed = 0
    for i, paragraph in enumerate(doc.paragraphs):
        # Основной текст письма выключен по ширине — на нём шапка заканчивается.
        if paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
            break
        if not paragraph.text.strip():
            continue
        fmt = paragraph.paragraph_format
        fmt.left_indent = Pt(indent_pt)
        # Красная строка внутри шапки не нужна: она сдвигала первую строку
        # адреса обратно влево.
        fmt.first_line_indent = Pt(0)
        changed += 1
        print(f"    para {i}: отступ {indent_pt:.0f}pt -> {paragraph.text.strip()[:50]!r}")

    if changed and not dry_run:
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
    path = root / RELATIVE_PATH
    if not path.exists():
        print(f"!! нет файла: {path}")
        return 1
    backup_root = Path(__file__).resolve().parents[1] / ".template-backups"
    print(f"== {RELATIVE_PATH}")
    changed = process(path, args.dry_run, backup_root, RELATIVE_PATH)
    print(f"\nисправлено абзацев: {changed}{' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
