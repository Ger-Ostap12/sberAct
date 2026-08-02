# -*- coding: utf-8 -*-
"""Как бэкенд ищет и запускает конвертер: _converter_command и _converter_env.

Эти две функции решают, заработает ли конвертация на машине пользователя.
Реальный случай, из-за которого написаны тесты: с флешки доехала неполная папка
converter (интерпретатора нет), и приложение показывало «Конвертер не найден»
без объяснения, что именно отсутствует.

Все пути подкладываем через tmp_path — ни один тест не трогает настоящую
установку и не запускает процессов.
"""
import logging
import os
import sys

import pytest

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

import main  # noqa: E402

_IS_WINDOWS = sys.platform == "win32"


def _make_converter(root, *, entry=True, launcher=True, pyruntime=False,
                    venv=False, site_packages=False):
    """Собирает бутафорскую папку конвертера с нужным набором частей."""
    root.mkdir(parents=True, exist_ok=True)
    if entry:
        (root / "main.py").write_text("# converter entry", encoding="utf-8")
    if launcher:
        (root / "run_converter.py").write_text("# launcher", encoding="utf-8")

    py_name = "python.exe" if _IS_WINDOWS else "python"
    bin_dir = "Scripts" if _IS_WINDOWS else "bin"

    if pyruntime:
        d = root / "pyruntime" if _IS_WINDOWS else root / "pyruntime" / "bin"
        d.mkdir(parents=True, exist_ok=True)
        (d / py_name).write_text("", encoding="utf-8")
    if venv:
        d = root / ".venv" / bin_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / py_name).write_text("", encoding="utf-8")
    if site_packages:
        rel = "Lib/site-packages" if _IS_WINDOWS else "lib/python3.12/site-packages"
        (root / ".venv" / rel).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def converter_dir(tmp_path, monkeypatch):
    """Подменяет CONVERTER_DIR модуля на временную папку."""
    d = tmp_path / "converter"

    def _use(**kwargs):
        _make_converter(d, **kwargs)
        monkeypatch.setattr(main, "CONVERTER_DIR", d)
        return d

    return _use


def test_no_interpreter_means_not_installed(converter_dir):
    """Код и лаунчер есть, интерпретатора нет — ровно случай битой установки."""
    converter_dir(pyruntime=False, venv=False)
    assert main._converter_command() is None


def test_pyruntime_is_used_when_present(converter_dir):
    """Прод: рядом лежит портируемый Python — запускаем им."""
    root = converter_dir(pyruntime=True)
    cmd = main._converter_command()
    assert cmd is not None
    assert str(root / "pyruntime") in cmd[0]
    assert cmd[1].endswith("run_converter.py")


def test_venv_is_fallback_without_pyruntime(converter_dir):
    """Dev: pyruntime не собран — берём интерпретатор .venv конвертера."""
    root = converter_dir(pyruntime=False, venv=True)
    cmd = main._converter_command()
    assert cmd is not None
    assert str(root / ".venv") in cmd[0]


def test_pyruntime_wins_over_venv(converter_dir):
    """Есть оба — приоритет у pyruntime: .venv не самодостаточен."""
    root = converter_dir(pyruntime=True, venv=True)
    cmd = main._converter_command()
    assert str(root / "pyruntime") in cmd[0]


def test_missing_entry_means_not_installed(converter_dir):
    """Без main.py конвертера папка бесполезна, даже если интерпретатор есть."""
    converter_dir(entry=False, pyruntime=True)
    assert main._converter_command() is None


def test_env_isolates_from_user_site_packages(converter_dir):
    """
    В проде зависимости берутся из .venv через PYTHONPATH, а user-site пользователя
    обязан быть отключён: его пакеты попадают в sys.path раньше PYTHONPATH и могут
    подменить torch чужой версией.
    """
    root = converter_dir(pyruntime=True, site_packages=True)
    env = main._converter_env()
    assert env.get("PYTHONNOUSERSITE") == "1"
    assert env["PYTHONPATH"].startswith(str(root / ".venv"))


def test_env_empty_without_pyruntime(converter_dir):
    """Dev-запуск через .venv самодостаточен — env не подменяем."""
    converter_dir(pyruntime=False, venv=True, site_packages=True)
    assert main._converter_env() == {}


def test_env_empty_when_site_packages_absent(converter_dir):
    """pyruntime без .venv/site-packages: подсовывать несуществующий путь незачем."""
    converter_dir(pyruntime=True, site_packages=False)
    assert main._converter_env() == {}
