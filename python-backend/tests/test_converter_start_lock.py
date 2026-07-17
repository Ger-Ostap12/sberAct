# -*- coding: utf-8 -*-
"""Старт конвертера сериализован: параллельные вызовы дают ОДИН процесс.

Фронт зовёт /converter/start несколько раз подряд (React StrictMode дублирует
эффект в dev). До лока каждый вызов успевал пройти проверку _converter_healthy()
раньше, чем предыдущий поднимал сервис, — Popen'ы плодились и дрались за порт 8008.

pytest-asyncio в проекте нет, поэтому корутины гоняем через asyncio.run().
"""
import asyncio
import logging
import os
import sys

import pytest

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

import main  # noqa: E402


class _FakePopen:
    """Живой процесс, который никогда не падает сам."""

    returncode = None

    def poll(self):
        return None


@pytest.fixture(autouse=True)
def _reset_converter_state():
    main._converter_process = None
    main._converter_start_lock = None  # лок привязан к loop — пересоздаём на каждый тест
    yield
    main._converter_process = None
    main._converter_start_lock = None


def _fake_converter(popen_calls, boot_polls=2):
    """
    Фейк sidecar'а с ЗАДЕРЖКОЙ старта: health становится True только через
    `boot_polls` опросов после Popen.

    Мгновенный подъём (health=True прямо в Popen) делал тест пустым: повторная
    проверка сама гасила гонку, и тест проходил даже без лока. Реальный конвертер
    грузит LLM секунды — именно это окно и порождает лишние Popen'ы.
    """
    state = {"spawned": False, "polls": 0}

    async def fake_healthy():
        await asyncio.sleep(0)  # отдаём управление — конкурент получает шанс влезть
        if not state["spawned"]:
            return False
        state["polls"] += 1
        return state["polls"] >= boot_polls

    def fake_popen(*args, **kwargs):
        popen_calls.append(args)
        state["spawned"] = True
        return _FakePopen()

    return fake_healthy, fake_popen


def test_parallel_start_spawns_single_process(monkeypatch):
    """Три параллельных вызова — ровно один Popen."""
    popen_calls = []
    fake_healthy, fake_popen = _fake_converter(popen_calls)

    monkeypatch.setattr(main, "_converter_healthy", fake_healthy)
    monkeypatch.setattr(main, "_converter_command", lambda: ["python", "run_converter.py"])
    monkeypatch.setattr(main.subprocess, "Popen", fake_popen)

    async def scenario():
        return await asyncio.gather(*(main.converter_start() for _ in range(3)))

    results = asyncio.run(scenario())

    assert len(popen_calls) == 1, f"ожидался один Popen, получено {len(popen_calls)}"
    assert all(r["ok"] for r in results), results


def test_already_healthy_does_not_spawn(monkeypatch):
    """Живой конвертер переиспользуется, Popen не зовётся вовсе."""
    popen_calls = []

    async def fake_healthy():
        return True

    monkeypatch.setattr(main, "_converter_healthy", fake_healthy)
    monkeypatch.setattr(main.subprocess, "Popen", lambda *a, **k: popen_calls.append(a))

    res = asyncio.run(main.converter_start())

    assert res["ok"] is True
    assert popen_calls == []
