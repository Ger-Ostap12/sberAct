# -*- coding: utf-8 -*-
"""Ипотека: разбор сторон — представитель истца, адрес одиночного ответчика,
несовершеннолетние со-ответчики «в лице законного представителя».

Синтетические тексты (без внешних .docx) — детерминированно и быстро.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import fio_detector as fd  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402


# --- #5: несовершеннолетние со-ответчики -----------------------------------

def test_represented_minor_name_full_string():
    line = "Федотьев Даниил Александрович в лице законного представителя ФЕДОТЬЕВА АЛЕКСАНДРА АРТАВАЗДОВИЧА"
    assert fd._represented_minor_name(line) == (
        "Федотьев Даниил Александрович в лице законного представителя "
        "Федотьева Александра Артаваздовича"
    )


def test_represented_minor_name_rejects_plain_fio():
    assert fd._represented_minor_name("Иванов Иван Иванович") is None
    assert fd._represented_minor_name("Цена иска: 100 руб.") is None


def test_extract_debtors_includes_minors():
    text = (
        "Ответчики:\n"
        "ФЕДОТЬЕВ АЛЕКСАНДР АРТАВАЗДОВИЧ\n"
        "ИНН: 261543614802,\n"
        "Дата рождения: 22.08.1989,\n"
        "Адрес регистрации: 353132, Краснодарский край, ст-ца Березанская, ул. Жлобы, д. 8\n"
        "Федотьев Даниил Александрович в лице законного представителя ФЕДОТЬЕВА АЛЕКСАНДРА АРТАВАЗДОВИЧА\n"
        "Дата рождения: 11.10.2021,\n"
        "СНИЛС 574-699-736 77\n"
        "Адрес регистрации: 353132, Краснодарский край, ст-ца Березанская, ул. Жлобы, д. 8\n"
        "Цена иска: 1177237,23 руб.\n"
    )
    debtors = fd.extract_debtors(text)
    names = [d["name"] for d in debtors]
    assert "Федотьев Александр Артаваздович" in names
    assert any("в лице законного представителя" in n for n in names)
    assert all(d.get("address") for d in debtors)


# --- #2: представитель истца -----------------------------------------------

def test_extract_representative_skips_branch_line():
    da = DocumentAnalyzer()
    text = (
        "Представитель истца:\n"
        "Северодвинское отделение №2221\n"
        "Чепелов Иван Александрович\n"
        "СНИЛС 131-761-878 92\n"
    )
    assert da._extract_representative_name(text) == "Чепелов Иван Александрович"


def test_extract_representative_none_when_absent():
    da = DocumentAnalyzer()
    assert da._extract_representative_name("Истец:\nПАО Сбербанк\n") is None


# --- #4: адрес одиночного ответчика восполняется из записи блока -------------

def test_single_debtor_address_backfilled():
    """Плоский applicantAddress пуст, но запись блока «Ответчик:» несёт адрес —
    он должен попасть в единственного ответчика (реальный путь resolve)."""
    da = DocumentAnalyzer()
    text = (
        "Ответчик:\n"
        "НУРИЕВА ЕЛЕНА ВАЛИДИНОВНА\n"
        "Дата рождения: 27.08.1978\n"
        "ИНН 231552257675\n"
        "Адрес регистрации: 353911, Краснодарский край, г. Новороссийск, пер. Геленджикский, д. 8Б\n"
        "Цена иска: 3 670 388,48 руб.\n"
    )
    fields = {"applicantName": "Нуриева Елена Валидиновна", "applicantAddress": ""}
    debtors_result, _ = da._resolve_debtors_and_third_parties(fields, text, {})
    assert len(debtors_result) == 1
    assert debtors_result[0]["address"].startswith("353911")


# --- Военная ипотека: детект вида + третье лицо ФГКУ «Росвоенипотека» ---------

_ROSVOEN_HEAD = (
    "Третье лицо: Федеральное государственное казенное учреждение \"Федеральное управление "
    "накопительно-ипотечной системы жилищного обеспечения военнослужащих\"\n"
    "Адрес: 123007, г. Москва, Хорошевское шоссе, д. 85Д, стр.4\n"
    "ОГРН 1067781337095 от 8 июня 2006 г.\n"
    "ИНН/КПП 7704159488/771401001\n"
    "Цена иска: 1 844 383,84 руб.\n"
    "ИСКОВОЕ ЗАЯВЛЕНИЕ\n"
    "Публичное акционерное общество \"Сбербанк России\" (далее – Банк, Истец) выдало ипотечный "
    "кредит «Военная ипотека – приобретение готового жилья» ...\n"
)


def test_detect_mortgage_kind():
    da = DocumentAnalyzer()
    assert da._detect_mortgage_kind(_ROSVOEN_HEAD) == "military"
    assert da._detect_mortgage_kind("выдало ипотечный кредит под залог квартиры") == "civil"
    assert da._detect_mortgage_kind(
        "Кредит выдавался на инвестирование строительства недвижимости; права требования "
        "участника долевого строительства по договору участия в долевом строительстве"
    ) == "ddu"


_DDU_THIRD_PARTIES = (
    "Третье лицо:\n"
    "ООО \"СПЕЦИАЛИЗИРОВАННЫЙ ЗАСТРОЙЩИК «Не гарантирую качество»\n"
    "ИНН 2311111111, ОГРН 1202311111111, КПП 2311011111.\n"
    "Адрес: 350028, Краснодарский край, г. Краснодар, Восточно-Кругликовская ул., дом 42/3\n"
    "Третье лицо:\n"
    "Управление Росреестра по Краснодарскому краю\n"
    "ИНН 2309090540 ОГРН 1042304982510\n"
    "Адрес: 350063 г. Краснодар ул. Ленина, д. 28\n"
    "Цена иска: 1 000 000 руб.\n"
)


def test_two_third_parties_repeated_label():
    """Две метки «Третье лицо:» подряд (застройщик + Росреестр) — оба лица, свои ИНН."""
    parties = fd.extract_third_parties(_DDU_THIRD_PARTIES)
    assert len(parties) == 2
    assert parties[0]["inn"] == "2311111111"
    assert parties[1]["name"].startswith("Управление Росреестра")
    assert parties[1]["inn"] == "2309090540"
    # Адрес первого лица не должен захватывать второе.
    assert "Росреестра" not in parties[0]["address"]


def test_debtor_passport_and_secondary_address():
    """Паспорт серия/номер разбирается; вторичный «Иной известный адрес» в основной не тянется."""
    text = (
        "Ответчик:\n"
        "ФОНАРЕВА ИННА ВИКТОРОВНА\n"
        "Дата рождения 31.12.1982\n"
        "Паспорт: серия 1111 № 111111\n"
        "ИНН 280111111111\n"
        "Адрес регистрации 675014, Амурская область, г. Благовещенск, ул. Текстильная, д. 86/2, кв. 68 "
        "Иной известный адрес проживания: 350011, г. Краснодар, ул. Обрывная, д. 293/6\n"
        "Цена иска: 5 000 000 руб.\n"
    )
    debtors = fd.extract_debtors(text)
    assert len(debtors) == 1
    d = debtors[0]
    assert d["passportSeries"] == "1111"
    assert d["passportNumber"] == "111111"
    assert "Иной известный адрес" not in d["address"]
    assert "Обрывная" not in d["address"]


def test_third_party_rosvoenipoteka_not_garbage():
    """Блок третьих лиц не должен улетать в тело: единственное лицо — ФГКУ, без
    ложных «ИСКОВОЕ ЗАЯВЛЕНИЕ»/«Сбербанк»."""
    parties = fd.extract_third_parties(_ROSVOEN_HEAD)
    assert len(parties) == 1
    p = parties[0]
    assert p["name"].startswith("Федеральное государственное казенное учреждение")
    assert p.get("inn") == "7704159488"
    assert p.get("ogrn") == "1067781337095"
    assert p["address"].startswith("123007")
