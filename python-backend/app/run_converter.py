# -*- coding: utf-8 -*-
"""
Лаунчер OCR-конвертера на заданном порту БЕЗ правок его кода.

В upstream-репо конвертера порт захардкожен (uvicorn.run(..., port=8000)) и
конфликтует с бэкендом sberAct. Политика интеграции — «ноль правок в папке
конвертера» (docs/converter_integration_plan.md §6), поэтому обёртка живёт
здесь: импортирует FastAPI-приложение конвертера (модульный код выполняется,
uvicorn.run у него под __main__-guard) и поднимает его на CONVERTER_PORT.

Запуск (менеджером процессов бэкенда/Electron, интерпретатором venv КОНВЕРТЕРА):
    <converter>/venv/Scripts/python.exe run_converter.py
Окружение: CONVERTER_DIR — папка конвертера, CONVERTER_PORT — порт (дефолт 8008).
Когда upstream научится CONVERTER_PORT сам — обёртка станет не нужна.
"""
import os
import sys
from pathlib import Path


def main() -> None:
    converter_dir = os.environ.get("CONVERTER_DIR")
    if not converter_dir:
        print("CONVERTER_DIR не задан", file=sys.stderr)
        sys.exit(2)
    converter_path = Path(converter_dir).resolve()
    if not (converter_path / "main.py").exists():
        print(f"main.py конвертера не найден в {converter_path}", file=sys.stderr)
        sys.exit(2)

    port = int(os.environ.get("CONVERTER_PORT", "8008"))

    # Конвертер полагается на запуск из своей папки (модели/фронт по
    # относительным путям) — работаем из неё.
    os.chdir(converter_path)
    sys.path.insert(0, str(converter_path))

    import uvicorn  # uvicorn из venv конвертера
    import main as converter_main  # noqa: F401 — его module-level код собирает app

    uvicorn.run(converter_main.app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
