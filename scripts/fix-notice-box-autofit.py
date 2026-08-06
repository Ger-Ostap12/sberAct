# -*- coding: utf-8 -*-
"""Возвращает врезке-шапке извещения автоподбор высоты (mso-fit-shape-to-text).

Врезка с реквизитами суда имеет фиксированную высоту в стиле VML-фигуры
(height:150pt). Пока рядом стоит mso-fit-shape-to-text:t, Word/Р7 растягивают её
под текст: адрес суда переносится на вторую строку — рамка становится выше.
Без этого флага высота остаётся жёсткой и текст обрезается.

Флаг теряется при пересохранении шаблона в Р7-Офисе (05.08 так и вышло: ширина
220pt уцелела, автоподбор пропал). python-docx до VML-фигуры не достаёт, поэтому
правим на уровне zip — как и ширину в своё время.

Запуск:
    python scripts/fix-notice-box-autofit.py [--dry-run] [--templates <путь>]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

RELATIVE_PATH = Path("ипотека/Извещение_МАРКИРОВАННЫЙ.docx")
PART = "word/document.xml"
FLAG = "mso-fit-shape-to-text:t"
# Стиль VML-фигуры узнаём по ширине: другого style= с width: в документе нет.
STYLE_RE = re.compile(r'style="([^"]*width:[^"]*)"')


def patch_xml(xml: str) -> tuple[str, int]:
    changed = 0

    def repl(match: re.Match) -> str:
        nonlocal changed
        style = match.group(1)
        if FLAG in style:
            return match.group(0)
        changed += 1
        # Ставим сразу после height — там же, где флаг стоит у Word.
        if "height:" in style:
            style = re.sub(r"(height:[\d.]+pt)", r"\1;" + FLAG, style, count=1)
        else:
            style = style + ";" + FLAG
        return f'style="{style}"'

    return STYLE_RE.sub(repl, xml), changed


def process(path: Path, dry_run: bool, backup_root: Path, rel: Path) -> int:
    with zipfile.ZipFile(path) as zin:
        items = [(info, zin.read(info.filename)) for info in zin.infolist()]

    patched_items = []
    changed = 0
    for info, data in items:
        if info.filename == PART:
            xml = data.decode("utf-8")
            xml, changed = patch_xml(xml)
            data = xml.encode("utf-8")
        patched_items.append((info, data))

    if not changed:
        print("    автоподбор уже стоит — правка не нужна")
        return 0
    print(f"    добавлен {FLAG}: {changed} шт.")
    if dry_run:
        return changed

    backup = backup_root / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy(path, backup)
    tmp = path.with_suffix(".docx.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in patched_items:
            zout.writestr(info, data)
    tmp.replace(path)
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
    print(f"\nисправлено мест: {changed}{' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
