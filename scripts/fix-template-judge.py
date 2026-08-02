# -*- coding: utf-8 -*-
"""Меняет вписанное в шаблон ФИО судьи на маркер [415].

В «продление БД.docx» и «принятие иниц залог недвига.docx» подпись судьи была
задана текстом («Судья К.О. Панова»), поэтому в готовый акт всегда попадала она
же — независимо от того, кого выбрали в интерфейсе.

Правка идёт по runs, чтобы сохранить форматирование подписи.

Запуск:
    python scripts/fix-template-judge.py [--dry-run] [--templates <путь>]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from docx import Document

# «Судья И.О. Фамилия» / «Судья Фамилия И.О.» — до маркера дела/конца строки.
HARDCODED = re.compile(
    r"^(\s*Судья\b)\s*[\s\.]*"
    r"((?:[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*[А-ЯЁ][а-яё]+)|(?:[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.))\s*$"
)


def fix_paragraph(paragraph) -> bool:
    text = paragraph.text
    m = HARDCODED.match(text)
    if not m or "[415]" in text:
        return False
    # Собираем абзац заново из одного run: подпись — короткая строка, её
    # форматирование задаётся первым run, дробить смысла нет.
    keep = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    for run in list(paragraph.runs[1:]):
        run.text = ""
    keep.text = f"{m.group(1).strip()}\t[415]"
    return True


def process(path: Path, dry_run: bool, backup_root: Path, rel: Path) -> int:
    doc = Document(str(path))
    fixed = 0
    for i, paragraph in enumerate(doc.paragraphs):
        before = paragraph.text.strip()
        if fix_paragraph(paragraph):
            fixed += 1
            print(f"    para {i}: {before!r} -> {paragraph.text!r}")
    if fixed and not dry_run:
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy(path, backup)
        doc.save(str(path))
    return fixed


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
        if not any(HARDCODED.match(p.text) and "[415]" not in p.text for p in doc.paragraphs):
            continue
        rel = path.relative_to(root)
        print(f"== {rel}")
        total += process(path, args.dry_run, backup_root, rel)
    print(f"\nисправлено подписей: {total}{' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
