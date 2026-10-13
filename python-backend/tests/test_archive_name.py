"""Имя архива с актами: ФИО должника и дата генерации в формате ДД-ММ-ГГГГ."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from archive_name import (  # noqa: E402
    archive_base_name,
    content_disposition,
    archive_name_for_documents,
    debtor_display_name,
    sanitize_file_name,
)

ДЕНЬ = date(2026, 10, 13)


class TestИмяДолжника:
    def test_из_карточки_должника(self):
        данные = {"debtors": [{"name": "Иванов Иван Иванович"}]}
        assert debtor_display_name(данные) == "Иванов Иван Иванович"

    def test_при_нескольких_берётся_первый(self):
        данные = {"debtors": [{"name": "Первый Ответчик"}, {"name": "Второй Ответчик"}]}
        assert debtor_display_name(данные) == "Первый Ответчик"

    def test_из_плоского_поля_когда_карточек_нет(self):
        assert debtor_display_name({"debtorName": "ООО «СПОРТ»"}) == "ООО СПОРТ"

    def test_пустая_карточка_не_мешает_плоскому_полю(self):
        данные = {"debtors": [{"name": "  "}], "debtorName": "Петров Пётр"}
        assert debtor_display_name(данные) == "Петров Пётр"

    def test_из_вложенных_полей(self):
        # Хвостовая точка снимается тут же: имя идёт прямо в файл.
        assert debtor_display_name({"fields": {"debtorName": "Сидоров С.С."}}) == "Сидоров С.С"

    def test_заявитель_как_запасной_источник(self):
        assert debtor_display_name({"applicantName": "Кузнецов К.К."}) == "Кузнецов К.К"

    def test_имени_нет(self):
        assert debtor_display_name({}) == ""
        assert debtor_display_name(None) == ""


class TestОчисткаИмени:
    def test_служебные_символы_уходят(self):
        assert sanitize_file_name('ООО "СПОРТ"/ЮГ') == "ООО СПОРТ ЮГ"

    def test_кавычки_ёлочки_уходят(self):
        assert sanitize_file_name("ООО «Форте»") == "ООО Форте"

    def test_двоеточие_и_звёздочка_уходят(self):
        assert sanitize_file_name("Дело: А53*11") == "Дело А53 11"

    def test_перевод_строки_не_попадает_в_заголовок(self):
        assert sanitize_file_name("Иванов\nИван") == "Иванов Иван"

    def test_хвостовая_точка_убирается(self):
        # Windows не умеет файлы, оканчивающиеся точкой.
        assert sanitize_file_name("Иванов И.И.") == "Иванов И.И"

    def test_пробелы_схлопываются(self):
        assert sanitize_file_name("  Иванов   Иван  ") == "Иванов Иван"


class TestИмяАрхива:
    def test_фио_и_дата(self):
        данные = {"debtors": [{"name": "Иванов Иван Иванович"}]}
        assert archive_base_name(данные, ДЕНЬ) == "Иванов Иван Иванович 13-10-2026"

    def test_формат_даты_день_месяц_год(self):
        # Решение Андрея: ДД-ММ-ГГГГ, а не ГГГГ-ММ-ДД.
        assert archive_base_name({}, date(2026, 1, 5)).endswith("05-01-2026")

    def test_без_имени_запасное(self):
        assert archive_base_name({}, ДЕНЬ) == "Судебные акты 13-10-2026"


class TestПоХранилищуДокументов:
    def test_берёт_данные_первого_документа(self):
        store = {
            "d1": {"data": {"debtors": [{"name": "Иванов Иван"}]}},
            "d2": {"data": {"debtors": [{"name": "Другой Должник"}]}},
        }
        assert archive_name_for_documents(store, ["d1", "d2"], ДЕНЬ) == "Иванов Иван 13-10-2026"

    def test_пропускает_документ_без_имени(self):
        store = {"d1": {"data": {}}, "d2": {"data": {"debtorName": "Петров Пётр"}}}
        assert archive_name_for_documents(store, ["d1", "d2"], ДЕНЬ) == "Петров Пётр 13-10-2026"

    def test_неизвестный_документ_не_роняет(self):
        assert archive_name_for_documents({}, ["нет-такого"], ДЕНЬ) == "Судебные акты 13-10-2026"

    def test_пустой_список(self):
        assert archive_name_for_documents({}, [], ДЕНЬ) == "Судебные акты 13-10-2026"

class TestЗаголовокСкачивания:
    def test_кириллица_уходит_в_filename_звёздочка(self):
        заголовок = content_disposition("Иванов Иван 13-10-2026.zip")
        assert "filename*=UTF-8''" in заголовок
        assert "%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2" in заголовок

    def test_есть_ascii_запасное_имя_для_старых_клиентов(self):
        заголовок = content_disposition("Иванов Иван 13-10-2026.zip")
        assert 'filename="13-10-2026.zip"' in заголовок

    def test_латиница_остаётся_читаемой(self):
        заголовок = content_disposition("Sidorov 13-10-2026.zip")
        assert 'filename="Sidorov_13-10-2026.zip"' in заголовок

    def test_кавычка_в_имени_не_рвёт_заголовок(self):
        заголовок = content_disposition('ООО "СПОРТ" 13-10-2026.zip')
        assert заголовок.count('"') == 2

    def test_имя_целиком_из_кириллицы_не_даёт_пустого_ascii(self):
        заголовок = content_disposition("Иванов.zip")
        assert 'filename=""' not in заголовок
