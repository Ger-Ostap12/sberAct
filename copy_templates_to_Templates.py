# -*- coding: utf-8 -*-
"""
Копирует .docx шаблоны из старых папок проекта в папку Templates.
Запустите из корня проекта (sberAct). Если каких-то папок/файлов нет — они будут пропущены.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "Templates"

# Пары: (источник относительно корня, назначение относительно Templates)
# Назначение = тот же относительный путь под Templates
MAPPING = [
    ("шаблоны актов без залогов", "шаблоны актов без залогов"),
    ("Залог", "Залог"),
    ("умерший", "умерший"),
    ("КФХ", "КФХ"),
    ("Проект Никите/ипотека", "Проект Никите/ипотека"),
    ("СУдебные акты физики/Взыскание", "СУдебные акты физики/Взыскание"),
    ("Взыскания ИП + Залог", "Взыскания ИП + Залог"),
    ("Взыскание ИП залог авто", "Взыскание ИП залог авто"),
    ("Взыскание ЮЛ", "Взыскание ЮЛ"),
    ("ЮЛ взыскание залог", "ЮЛ взыскание залог"),
    ("взыскание ЮЛ залог авто", "взыскание ЮЛ залог авто"),
    ("на 19.02", "на 19.02"),
]

def main():
    for src_rel, dst_rel in MAPPING:
        src = ROOT / src_rel
        dst = TEMPLATES / dst_rel
        if not src.is_dir():
            print("Пропуск (нет папки):", src_rel)
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*.docx"):
            rel = f.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            print("Скопировано:", rel)
    print("Готово. Шаблоны в папке Templates.")

if __name__ == "__main__":
    main()
