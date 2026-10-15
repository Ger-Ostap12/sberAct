"""Поиск корня шаблонов: признак — папки нового дерева, а не старая раскладка."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from document_generator import DocumentGenerator  # noqa: E402

ВЫБОР = DocumentGenerator._pick_templates_root


@pytest.fixture
def gen():
    return DocumentGenerator()


class TestПризнакКорня:
    def test_новое_дерево_опознаётся(self, tmp_path):
        (tmp_path / "Банкротство").mkdir()
        assert DocumentGenerator._looks_like_templates_root(tmp_path)

    def test_ипотека_и_взыскание_тоже_признак(self, tmp_path):
        (tmp_path / "Ипотека").mkdir()
        assert DocumentGenerator._looks_like_templates_root(tmp_path)
        (tmp_path / "Взыскание").mkdir()
        assert DocumentGenerator._looks_like_templates_root(tmp_path)

    def test_старая_раскладка_больше_не_признак(self, tmp_path):
        # Дерево заменено: по этой папке корень искать нельзя.
        (tmp_path / "шаблоны актов без залогов").mkdir()
        assert not DocumentGenerator._looks_like_templates_root(tmp_path)

    def test_пустая_папка_не_корень(self, tmp_path):
        assert not DocumentGenerator._looks_like_templates_root(tmp_path)

    def test_файл_вместо_папки_не_считается(self, tmp_path):
        (tmp_path / "Банкротство").write_text("не папка", encoding="utf-8")
        assert not DocumentGenerator._looks_like_templates_root(tmp_path)


class TestВыборКандидата:
    def test_первый_подходящий_кандидат(self, tmp_path):
        пусто = tmp_path / "пусто"
        пусто.mkdir()
        годный = tmp_path / "годный"
        (годный / "Банкротство").mkdir(parents=True)
        assert ВЫБОР([пусто, годный]) == годный

    def test_порядок_кандидатов_важен(self, tmp_path):
        # Шаблоны рядом с exe должны выигрывать у встроенных в бинарник.
        рядом = tmp_path / "рядом-с-exe"
        внутри = tmp_path / "внутри-бинарника"
        (рядом / "Банкротство").mkdir(parents=True)
        (внутри / "Банкротство").mkdir(parents=True)
        assert ВЫБОР([рядом, внутри]) == рядом
        assert ВЫБОР([внутри, рядом]) == внутри

    def test_дерево_внутри_обёртки(self, tmp_path):
        # У собранного exe кандидат — каталог запуска, дерево лежит в Templates.
        (tmp_path / "Templates" / "Банкротство").mkdir(parents=True)
        assert ВЫБОР([tmp_path]) == tmp_path / "Templates"

    def test_обёртка_shablony(self, tmp_path):
        (tmp_path / "Shablony" / "Ипотека").mkdir(parents=True)
        assert ВЫБОР([tmp_path]) == tmp_path / "Shablony"

    def test_сам_кандидат_важнее_обёртки(self, tmp_path):
        (tmp_path / "Банкротство").mkdir()
        (tmp_path / "Templates" / "Банкротство").mkdir(parents=True)
        assert ВЫБОР([tmp_path]) == tmp_path

    def test_ничего_не_найдено(self, tmp_path):
        assert ВЫБОР([tmp_path]) is None

    def test_несуществующий_кандидат_пропускается(self, tmp_path):
        нет = tmp_path / "нет-такой"
        годный = tmp_path / "годный"
        (годный / "Ипотека").mkdir(parents=True)
        assert ВЫБОР([нет, годный]) == годный


class TestРеальныйКорень:
    def test_корень_найден(self, gen):
        root = gen._templates_root()
        assert root.is_dir(), root
        assert (root / "Банкротство").is_dir(), root

    def test_ипотека_на_месте(self, gen):
        mortgage = gen._templates_root() / "Ипотека"
        assert mortgage.is_dir(), mortgage
        assert list(mortgage.glob("*.docx")), "в папке ипотеки нет шаблонов"

    def test_ветка_ртк_на_месте(self, gen):
        rtk = gen._templates_root() / "Банкротство" / "Включение в РТК"
        assert rtk.is_dir(), rtk


class TestРегистрИмёнПапок:
    """Windows не различает регистр, Astra различает — сверяем имя с диском."""

    def _фактические(self, папка):
        return {p.name for p in папка.iterdir() if p.is_dir()}

    def _точный_путь(self, корень, путь):
        """Каждая часть пути встречается в листинге родителя побайтово."""
        текущая = корень
        for часть in путь.relative_to(корень).parts:
            имена = {p.name for p in текущая.iterdir()}
            assert часть in имена, (
                "код ищет «%s» в %s, на диске %s" % (часть, текущая, sorted(имена)))
            текущая = текущая / часть

    def test_пути_шаблонов_ипотеки_совпадают_по_регистру(self, gen):
        root = gen._templates_root()
        пакет = gen._get_mortgage_templates()
        assert len(пакет) == 5, пакет
        for сведения in пакет.values():
            self._точный_путь(root, сведения["path"])

    def test_имя_ветки_банкротства(self, gen):
        root = gen._templates_root()
        assert "Банкротство" in self._фактические(root)
        assert "Включение в РТК" in self._фактические(root / "Банкротство")
