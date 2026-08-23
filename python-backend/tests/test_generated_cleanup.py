# -*- coding: utf-8 -*-
"""Уборка сгенерированных актов (аудит §S.1.4, находка №8).

`cleanup_old_documents` был написан и НЕ вызывался ниоткуда: папка росла
бесконечно (в дереве разработки накопилось 376 файлов на 13 МБ). Теперь он
подключён к жизненному циклу приложения — и раз метод удаляет файлы
пользователя, границы удаления должны быть доказаны, а не заявлены.

Проверяем ровно то, что метод НЕ должен трогать: свежие файлы, чужие
расширения, вложенные каталоги.
"""
import os
import time

import pytest

from document_generator import DocumentGenerator

DAY = 24 * 3600


@pytest.fixture()
def generator(tmp_path, monkeypatch):
    """Генератор с изолированным каталогом вывода — в настоящий не лезем."""
    monkeypatch.setenv("SBERACT_DATA_DIR", str(tmp_path))
    gen = DocumentGenerator()
    gen.generated_dir = tmp_path / "generated"
    gen.generated_dir.mkdir(parents=True, exist_ok=True)
    gen.documents = {}
    return gen


def _make(path, age_hours=0.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"docx")
    if age_hours:
        old = time.time() - age_hours * 3600
        os.utime(path, (old, old))
    return path


def test_старый_осиротевший_файл_удаляется(generator):
    """Реестр живёт в памяти: после перезапуска прошлые акты «ничьи»."""
    old = _make(generator.generated_dir / "aaa.docx", age_hours=48)
    assert generator.cleanup_old_documents(max_age_hours=24) == 1
    assert not old.exists()


def test_свежий_файл_не_трогаем(generator):
    fresh = _make(generator.generated_dir / "bbb.docx", age_hours=1)
    assert generator.cleanup_old_documents(max_age_hours=24) == 0
    assert fresh.exists()


def test_чужое_расширение_не_трогаем(generator):
    """В каталоге могут лежать не наши файлы — сносим только то, что создаём."""
    alien = _make(generator.generated_dir / "важное.txt", age_hours=999)
    generator.cleanup_old_documents(max_age_hours=24)
    assert alien.exists(), "удалён файл, который генератор не создавал"


def test_вложенный_каталог_не_обходим(generator):
    """Обход без рекурсии: чужая подпапка внутри generated не наша забота."""
    nested = _make(generator.generated_dir / "чужое" / "старый.docx", age_hours=999)
    generator.cleanup_old_documents(max_age_hours=24)
    assert nested.exists(), "уборка ушла в подкаталог"


def test_старые_архивы_zips_удаляются(generator):
    """zips/ копился так же, как и сами акты."""
    old_zip = _make(generator.generated_dir / "zips" / "старый.zip", age_hours=48)
    fresh_zip = _make(generator.generated_dir / "zips" / "свежий.zip", age_hours=1)
    generator.cleanup_old_documents(max_age_hours=24)
    assert not old_zip.exists()
    assert fresh_zip.exists()


def test_документ_из_реестра_живёт_пока_не_состарится(generator):
    """Файл, известный текущему процессу, сносится по дате генерации из реестра,
    а не по mtime — иначе свежесозданный акт со сбитым временем файла исчез бы."""
    from datetime import datetime

    doc_id = "ccc"
    path = _make(generator.generated_dir / f"{doc_id}.docx", age_hours=999)
    generator.documents[doc_id] = {
        "file_path": str(path),
        "generation_date": datetime.now().isoformat(),
        "document_name": "Свежий акт",
    }
    assert generator.cleanup_old_documents(max_age_hours=24) == 0
    assert path.exists(), "снесён актуальный документ текущего процесса"


def test_битый_реестр_не_роняет_уборку(generator):
    """Одна плохая запись не должна отменять уборку целиком."""
    generator.documents["битый"] = {"generation_date": "не дата"}
    _make(generator.generated_dir / "ddd.docx", age_hours=48)
    generator.cleanup_old_documents(max_age_hours=24)  # не бросает
