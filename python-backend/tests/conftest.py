# -*- coding: utf-8 -*-
"""Общая настройка pytest: добавляет app/ в sys.path для импорта модулей backend."""
import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import json
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--require-golden-corpus", action="store_true",
        help="Завершить проверку с ошибкой, если отсутствуют документы golden-корпуса.",
    )


def pytest_sessionstart(session):
    if not session.config.getoption("--require-golden-corpus"):
        return
    tests = Path(__file__).resolve().parent
    with (tests / "golden" / "golden_master.json").open(encoding="utf-8") as source:
        expected = json.load(source)
    corpus = tests.parents[1] / "заявления"
    missing = [name for name in expected if not (corpus / name).is_file()]
    if not expected or missing:
        raise pytest.UsageError(
            f"Golden-корпус неполон: отсутствует {len(missing)} из {len(expected)} документов. "
            "Подготовьте тестовый корпус перед обязательной проверкой CI."
        )
