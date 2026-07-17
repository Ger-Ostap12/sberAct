# -*- coding: utf-8 -*-
"""Сторож простоя: конвертер гаснет сам, если им перестали пользоваться.

UI больше не убивает sidecar после каждого файла (иначе КАЖДЫЙ следующий PDF
платил холодным стартом с загрузкой LLM). Память возвращает этот сторож: процесс
держит ~3.5 ГБ, а Python не умеет выгружать torch/LLM из живого процесса —
только kill (docs/converter_integration_plan.md).
"""
import asyncio
import contextlib
import logging
import os
import sys
import time

import pytest

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

import main  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    main._converter_process = None
    main._converter_last_used = None
    yield
    main._converter_process = None
    main._converter_last_used = None


def _run_watchdog_once(monkeypatch, killed, *, idle_for, timeout=300):
    """Один тик сторожа с отметкой активности, сдвинутой в прошлое на idle_for.

    Часы НЕ подменяем: на time.monotonic работает планировщик asyncio, и его
    подмена ломает event loop (первая версия теста именно так и падала).
    """
    monkeypatch.setattr(main, "CONVERTER_IDLE_TIMEOUT_S", timeout)
    monkeypatch.setattr(main, "CONVERTER_IDLE_CHECK_S", 0)  # без реального ожидания

    def fake_kill():
        # Настоящий _kill_converter обнуляет _converter_process (main.py) — без
        # этого сторож в тесте убивал бы на КАЖДОЙ итерации, чего в бою не бывает.
        main._converter_process = None
        killed.append(True)

    monkeypatch.setattr(main, "_kill_converter", fake_kill)
    main._converter_last_used = time.monotonic() - idle_for

    async def one_tick():
        task = asyncio.create_task(main._converter_idle_watchdog())
        # CONVERTER_IDLE_CHECK_S=0, поэтому сторож доходит до проверки за пару
        # переключений цикла; больше одного тика нам и не нужно.
        for _ in range(4):
            await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(one_tick())


def test_idle_converter_is_killed(monkeypatch):
    """Простой дольше таймаута — процесс гасится."""
    killed = []
    main._converter_process = object()  # наш процесс жив
    _run_watchdog_once(monkeypatch, killed, idle_for=301, timeout=300)
    assert killed == [True], "простаивающий конвертер обязан быть остановлен"


def test_recently_used_converter_survives(monkeypatch):
    """Пользовались недавно — не трогаем."""
    killed = []
    main._converter_process = object()
    _run_watchdog_once(monkeypatch, killed, idle_for=10, timeout=300)
    assert killed == [], "активный конвертер останавливать нельзя"


def test_external_converter_not_touched(monkeypatch):
    """Внешний конвертер (не наш Popen) не наш — не убиваем."""
    killed = []
    main._converter_process = None  # запущен снаружи
    _run_watchdog_once(monkeypatch, killed, idle_for=9999, timeout=300)
    assert killed == [], "чужой процесс трогать нельзя"


def test_touch_updates_last_used():
    """_converter_touch двигает отметку активности."""
    main._converter_last_used = None
    before = time.monotonic()
    main._converter_touch()
    assert main._converter_last_used is not None
    assert main._converter_last_used >= before
