# -*- coding: utf-8 -*-
"""Тесты детектора САМОБАНКРОТСТВА (`_detect_self_bankruptcy`).

Самобанкротство — заявление о банкротстве подаёт сам должник. Детектор — слои:
вето (кредиторские приметы/ФНС) → обязательное отсутствие «включить в РТК/очередь»
в просительной части → хотя бы один сильный сигнал (первое лицо, заголовок
заявления должника, «Заявитель (Должник)», шапка «должник первым»).

Позитивы — реальные .docx из `Заявления/Самобанкрот/` (по имени, без индексов:
файлы двигаются) + синтетические фрагменты краевых случаев (склеенный без
пробелов текст конвертации из PDF). Негативы — кредиторские ловушки из корпуса:
«должник первым» при «Заявитель (Кредитор)» (САРМАТ/БАЗОВ), включение в РТК, ФНС.
"""
import glob
import os

import pytest

from document_analyzer import DocumentAnalyzer

CORPUS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Заявления")
)
SELF_BK_DIR = os.path.join(CORPUS_DIR, "Самобанкрот")


@pytest.fixture(scope="module")
def da():
    return DocumentAnalyzer()


def _corpus_docx_by_key(key: str):
    """Первый .docx корпуса, содержащий key в пути (индексы плавают — ищем по имени)."""
    for f in sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.docx"), recursive=True)):
        if key.lower() in os.path.relpath(f, CORPUS_DIR).lower() and "~$" not in f:
            return f
    return None


# --- Позитивы: все реальные самобанкроты распознаются ------------------------
def _self_bk_files():
    return sorted(glob.glob(os.path.join(SELF_BK_DIR, "*.docx")))


@pytest.mark.parametrize(
    "path", _self_bk_files(), ids=[os.path.basename(f) for f in _self_bk_files()]
)
def test_real_self_bankruptcy_detected(da, path):
    text = da.extract_text(path)
    assert da._detect_self_bankruptcy(text) is True


def test_self_bankruptcy_folder_present():
    # Страж: если папку переместили — позитивы выше молча опустеют, ловим явно.
    assert _self_bk_files(), "в Заявления/Самобанкрот/ нет .docx"


def test_analyze_sets_application_kind(da):
    # Флаг уходит top-level (НЕ в fields → не в golden и не в editedFields фронта).
    files = _self_bk_files()
    result = da.analyze(files[0])
    assert result["applicationKind"] == "self_bankruptcy"
    assert "applicationKind" not in result["fields"]


# --- Негативы: кредиторские заявления корпуса --------------------------------
@pytest.mark.parametrize("key", [
    "САРМАТ",      # «должник первым» в шапке, но «Заявитель (Кредитор): ПАО Сбербанк»
    "БАЗОВ",       # аналогичная ловушка «только должник» в шапке
    "вкл в ртк",   # включение в РТК — «включить … в реестр требований»
])
def test_creditor_applications_not_self(da, key):
    path = _corpus_docx_by_key(key)
    if path is None:
        pytest.skip(f"файл с ключом «{key}» не найден в корпусе (перемещён)")
    text = da.extract_text(path)
    assert da._detect_self_bankruptcy(text) is False


def test_whole_corpus_no_false_positives(da):
    # Ни один документ корпуса ВНЕ папки Самобанкрот не должен детектиться.
    fp = []
    for f in sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.docx"), recursive=True)):
        rel = os.path.relpath(f, CORPUS_DIR)
        if "~$" in f or rel.startswith("Самобанкрот"):
            continue
        if da._detect_self_bankruptcy(da.extract_text(f)):
            fp.append(rel)
    assert fp == []


# --- Синтетические краевые случаи (слои детектора) ----------------------------
_PRAYER_SELF = "ПРОШУ:\n1. Признать меня несостоятельным (банкротом).\n2. Ввести процедуру реализации имущества."


def test_glued_pdf_text(da):
    # Конвертация из PDF склеивает слова — паттерны обязаны работать без пробелов.
    text = "Должник:ИвановИванИванович\nКредиторы:ПАОСбербанк\nЗАЯВЛЕНИЕФИЗИЧЕСКОГОЛИЦА\nопризнанииегонесостоятельным(банкротом)\nПРОШУ:Признатьменябанкротом."
    assert da._detect_self_bankruptcy(text) is True


def test_veto_applicant_creditor_wins(da):
    # «Заявитель (Кредитор)» перебивает любые сильные сигналы.
    text = "Заявитель (Кредитор): ПАО Сбербанк\nДолжник: Иванов И.И.\n" + _PRAYER_SELF
    assert da._detect_self_bankruptcy(text) is False


def test_veto_vzyskat_v_polzu(da):
    text = "Должник: Иванов И.И.\nПРОШУ:\n1. Признать меня банкротом.\n2. Взыскать с должника в пользу ПАО Сбербанк 100 руб."
    assert da._detect_self_bankruptcy(text) is False


def test_rtk_in_prayer_blocks(da):
    # Ключевой контр-сигнал: «включить в третью очередь» в просительной части.
    text = ("Должник: Иванов И.И.\nКредиторы: ПАО Сбербанк\n"
            "ПРОШУ:\n1. Признать Иванова И.И. банкротом.\n"
            "2. Включить требования в третью очередь реестра требований кредиторов.")
    assert da._detect_self_bankruptcy(text) is False


def test_applicant_is_debtor_signature(da):
    # Подпись «Заявитель (Должник):» — явный сильный сигнал (файл Федоренко).
    text = ("Федоренко Алексей Алексеевич\nКредитор 1. ООО МКК «Русинтерфинанс»\n"
            "ПРОШУ:\nПризнать гражданина РФ Федоренко А.А. несостоятельным (банкротом).\n"
            "Заявитель (Должник):\nГражданин Российской Федерации")
    assert da._detect_self_bankruptcy(text) is True


def test_no_strong_signals_negative(da):
    # Нет ни вето, ни РТК, но и сильных сигналов нет — не самобанкрот.
    text = "Некоторый текст про банкротство без примет.\nПРОШУ:\nНазначить управляющего."
    assert da._detect_self_bankruptcy(text) is False


# --- Layout-парсер шапки: границы должник/кредиторы ---------------------------
_HEADER_MEDVEDEV = (
    "Арбитражный суд Ростовской области\n"
    "Должник:\nМедведев Максим Юрьевич\n"
    "Дата рождения: 30.08.1985\nПаспорт: серия 60 05 № 561 928\n"
    "Адрес регистрации: 347022, Ростовская область, рп. Шолоховский, улица М. Горького, дом 46, квартира 1\n"
    "СНИЛС: 063-128-006 22\nИНН: 614208901558\n"
    "Кредитор 1:\nООО МКК «РУСИНТЕРФИНАНС»\nИНН: 5408292849 ОГРН: 1125476023298\n"
    "630055, город Новосибирск, улица Гнесиных, дом 10/1, офис 202\n"
    "Заявление\nо признании гражданина несостоятельным (банкротом)\n"
    "ПРОШУ:\n1. Признать меня банкротом.\n"
)


def test_layout_debtor_strict_boundaries(da):
    # Реквизиты должника — строго из его блока; ИНН/ОГРН кредитора не подтягиваются.
    fields = {"ogrn": "1125476023298", "creditorName": "ООО МКК «РУСИНТЕРФИНАСН»"}
    da._apply_self_bankruptcy_layout(fields, _HEADER_MEDVEDEV)
    assert fields["applicantName"] == "Медведев Максим Юрьевич"
    assert fields["inn"] == "614208901558"
    assert fields["birthDate"] == "30.08.1985"
    assert fields["snils"] == "063-128-006 22"
    assert fields["applicantAddress"].startswith("347022")
    assert fields["entityType"] == "individual"
    # ОГРН кредитора и creditor*-поля очищены (кредитора-заявителя нет).
    assert "ogrn" not in fields and "creditorName" not in fields


def test_layout_house_number_kept_before_creditors(da):
    # «…д. 23\nКредиторы:» — числовой хвост адреса не должен уходить в границу блока.
    text = (
        "В Арбитражный суд\nот Должника:\nМирский Алексей Степанович\n"
        "14 июня 1990 года рождения\nМесто рождения: г. Ростов-на-Дону\n"
        "Адрес: 344039, г. Ростов-на-Дону, ул. Средняя, д. 23\nКредиторы:\n1. ПАО «Сбербанк»\n"
        "Заявление\nо признании гражданина несостоятельным (банкротом)\nПРОШУ: Признать меня банкротом."
    )
    fields = {}
    da._apply_self_bankruptcy_layout(fields, text)
    assert fields["applicantAddress"].endswith("д. 23")
    # Дата прописью конвертируется в дд.мм.гггг (поле фронта — type=date).
    assert fields["birthDate"] == "14.06.1990"


# --- Обрезка склеенных адресов (требование Андрея, кейс Корсунова) -------------
def test_truncate_glued_address_creditors_tail(da):
    glued = ("347631, обл. Ростовская, р-н Сальский, гор. Сальск, ул. Севастопольская, "
             "д. 93-в, кв. 61 Кредиторы ООО МКК Эквазайм 432071, Ульяновская область, "
             "г Ульяновск ул Карла Маркса, д. 13а к. 1, помещ./этаж")
    assert da._truncate_glued_address(glued).endswith("кв. 61")


def test_truncate_glued_address_second_index(da):
    glued = ("125315, город Москва, Ленинградский пр-кт, д. 80 к. 9 ООО ПКО «РСВ» "
             "127055, город Москва, ул. Бутырский Вал, д. 68/70 стр. 1")
    assert da._truncate_glued_address(glued).endswith("д. 80 к. 9")


@pytest.mark.parametrize("legit", [
    # ФИАС-стили одного адреса — НЕ склейка, не режем.
    "115054, г. Москва, вн.тер.г. Муниципальный Округ Замоскворечье, наб Космодамианская, д. 52, стр. 7",
    "346404, Ростовская область, г. о. город Новочеркасск, г. Новочеркасск Харьковское шоссе, д. 10",
    "347022, Ростовская область, Белокалитвинский р-н, рп. Шолоховский, улица М. Горького, дом 46, квартира 1",
])
def test_truncate_glued_address_keeps_legit(da, legit):
    assert da._truncate_glued_address(legit) == legit


# --- Третьи лица из шапки самобанкрота ----------------------------------------
def test_third_parties_multiline_and_person(da):
    text = (
        "Должник: Иванов Иван Иванович\nКредиторы:\nПАО Сбербанк\n117312, город Москва, ул. Вавилова, д.19\n"
        "Третьи лица, не заявляющие\nсамостоятельных требований:\n"
        "Межрайонная инспекция Федеральной\nналоговой службы №4 по Ростовской\nобласти\n"
        "347375, Ростовская обл, Волгодонск г,\nЛенинградская ул, 10\n"
        "Петров Пётр Петрович\n344000, г. Ростов-на-Дону, ул. Ленина, д. 1\n"
        "28.06.1969 года рождения\nСНИЛС: 049-288-075 97 ИНН: 615300015070\n"
        "Заявление\nо признании гражданина несостоятельным (банкротом)\n"
    )
    tps = da._extract_sb_third_parties(text, len(text))
    assert [tp["name"] for tp in tps] == [
        "Межрайонная инспекция Федеральной налоговой службы №4 по Ростовской области",
        "Петров Пётр Петрович",
    ]
    assert tps[0]["address"].startswith("347375")
    assert tps[1]["birthDate"] == "28.06.1969"
    assert tps[1]["inn"] == "615300015070"


# --- Мусорные обязательства и ложный залог (правки по разбору Андрея) ----------
def test_passport_numbers_not_obligations(da):
    # Номера паспортов/свидетельств («Паспорт: серия 6018 № 402670», «Свидетельством
    # о установлении отцовства серии I-АН №671711») — не обязательства.
    text = ("Должник: Галета Ольга Николаевна\n"
            "Паспорт: серия 6018 № 402670\n"
            "что подтверждается Свидетельством о установлении отцовства серии I-АН №671711, выданным\n"
            "ПРОШУ: Признать меня банкротом.")
    assert da.extract_obligations(text, {"debtorName": "Галета Ольга Николаевна"}) == []


def test_bare_dogovor_type_filtered(da):
    # Правило Андрея: голый тип «Договор» (номер без кредитного контекста) в
    # fallback-пути — отсев (напр. «налоговое уведомление № 224597118»).
    text = ("Должник: Иванов Иван Иванович\n"
            "в адрес должника направлено налоговое уведомление № 224597118 от 26.08.2025.\n")
    assert da.extract_obligations(text, {"debtorName": "Иванов Иван Иванович"}) == []


def test_inventory_property_not_collateral(da):
    # Перечисление имущества должника — НЕ залог (Мирский: NISSAN из описи).
    text = ("В настоящее время у Должника имеется следующее имущество:\n"
            "недвижимое имущество — не имеет;\n"
            "движимое имущество — автомобиль NISSAN PRIMERA, 2003 года выпуска; имущественные права — не имеет.")
    assert da._extract_all_collateral_items(text) == []


def test_pledged_property_still_collateral(da):
    # А явный залог тем же форматом — извлекается по-прежнему.
    text = ("В качестве обеспечения в залог передано следующее имущество:\n"
            "- Автомобиль LADA VESTA, 2020 г.в., VIN XTA000000000000, стоимостью 500 000 руб.")
    items = da._extract_all_collateral_items(text)
    assert any("LADA" in s for s in items)


def test_third_parties_filters_credit_orgs(da):
    # Слипшиеся колонки таблицы: банки после метки «Третьи лица:» — кредиторы, отсев.
    text = (
        "Кредиторы:\nТретьи лица:\n"
        "ПАО СБЕРБАНК 117312, г Москва, ул Вавилова, д 19 \n"
        "УФНС России по Ростовской области 344002, г. Ростов-на-Дону, ул. Социалистическая, 96-98\n"
        "№ п/п Содержание обязательства\n"
    )
    tps = da._extract_sb_third_parties(text, len(text))
    assert [tp["name"] for tp in tps] == ["УФНС России по Ростовской области"]
