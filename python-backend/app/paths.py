"""Каталоги для записываемых данных (сгенерированные акты, временные файлы).

В установленном приложении папка установки затирается при обновлении, поэтому
пользовательские данные должны лежать вне её. Electron задаёт SBERACT_DATA_DIR
на app.getPath('userData') — туда и пишем. В dev/из исходников переменной нет,
поведение остаётся прежним (корень проекта), чтобы golden не смещался.
"""
import os
import sys
from pathlib import Path


def data_root() -> Path:
    """Корень записываемых данных. Приоритет — SBERACT_DATA_DIR (прод)."""
    env = os.environ.get("SBERACT_DATA_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # app/paths.py → parents[2] = корень проекта
    return Path(__file__).resolve().parents[2]


def generated_dir() -> Path:
    """Каталог сгенерированных .docx. Создаётся при обращении."""
    d = data_root() / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def temp_dir() -> Path:
    """Каталог временных файлов. Создаётся при обращении."""
    d = data_root() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d
