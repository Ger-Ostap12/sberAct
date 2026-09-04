# -*- coding: utf-8 -*-
"""Контракт поля: тип значения, владение текстом, инвариант каскада.

Реальные случаи из корпуса (файл указан в тесте) + негативные: контракт обязан
молчать там, где значение законное. Ложняк здесь дороже пропуска: вычищенное
поле юрист заметит, а лишний флаг обесценит подсветку.
"""
import logging
import os
import sys

import pytest

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

import field_contract as FC  # noqa: E402


# --- тип значения -----------------------------------------------------------
def test_money_field_rejects_text():
    """«Арбитражный суд Ростовской области» в loanDebt — Заявление РФЛ1.docx."""
    assert FC.check_value("loanDebt", "Арбитражный суд Ростовской области")


def test_money_field_rejects_text_with_newline():
    """Медведев М.Ю.docx: к суду прилип перенос и слово «Адрес»."""
    assert FC.check_value("loanDebt", "Арбитражный суд Ростовской области\nАдрес")


@pytest.mark.parametrize("value", ["25 000,00", "1 490 913,00", "163210,00", "0,00", "100000"])
def test_money_field_accepts_real_amounts(value):
    assert FC.check_value("totalDebt", value) is None


def test_money_field_accepts_nbsp_separators():
    """Разряды неразрывным пробелом — типовой docx банка, это валидная сумма."""
    assert FC.check_value("totalDebt", "1\xa0490\xa0913,00") is None


def test_zero_is_valid_money():
    """Законный ноль: неустойка может быть не начислена. Чистить нельзя."""
    assert FC.check_value("forfeit", "0,00") is None


# --- реквизиты (только помечаем, не чистим) ---------------------------------
def test_inn_checksum_failure_is_reported():
    """A53-9758…docx: ИНН должника побит OCR (стоит трижды, сумма не сходится)."""
    assert FC.check_value("inn", "612102429513")


def test_valid_inn_is_silent():
    assert FC.check_value("inn", "612102152288") is None


def test_ogrn_checksum_now_enforced():
    """is_valid_ogrn был написан, но не вызывался нигде — контракт его подключает."""
    assert FC.check_value("ogrn", "123454321234")


def test_multivalue_inn_kept_when_one_part_valid():
    """Многодолжниковые заявления: «ИНН1, ИНН2» — не мусор, а список."""
    assert FC.check_value("inn", "612102152288, 001023012301") is None


def test_requisites_are_flagged_but_not_cleared():
    """Решение Андрея: битый СВОЙ реквизит полезнее пустого поля."""
    fields = {"inn": "612102429513"}
    issues = FC.apply_contract(fields)
    assert fields["inn"] == "612102429513", "реквизит не должен вычищаться"
    assert [i for i in issues if i.field == "inn" and not i.cleared]


# --- адрес: позитивная грамматика -------------------------------------------
def test_address_without_any_address_marker_is_garbage():
    """«ПАО Сбер» в адресе должника — взыскание банкрот заявление.docx.

    Отсекается не потому, что «ПАО» в чёрном списке, а потому, что адресом не
    является: ни индекса, ни города, ни улицы, ни дома.
    """
    assert FC.check_value("applicantAddress", "ПАО Сбер")


@pytest.mark.parametrize("value", [
    "347561, Ростовская область, Песчанокопский р-н, с. Развильное, ул. Соляника, д. 20",
    "344068, г. Ростов-на-Дону, пр-кт Ленина, д. 5, кв. 61",
    "115114, Москва, Дербеневская наб., д. 11",
    "248030, Калужская обл., г. Калуга, ул. Труда, д. 29А",
    "a/я 15, 344000, г. Ростов-на-Дону",
])
def test_real_addresses_pass(value):
    assert FC.check_value("applicantAddress", value) is None


def test_address_with_postbox_tail_passes():
    """Хвост «а/я N» не режется (правило §K) — адрес остаётся валидным."""
    assert FC.check_value("managerAddress", "344000, г. Ростов-на-Дону, а/я 123") is None


# --- адрес: склейка с соседней строкой --------------------------------------
_GLUED_ADDRESS = (
    "347211, Ростовская обл, Морозовский р-н, Морозовск, ул Калинина, двлд 38 "
    "дата и место рождения; 21.11.1971 ,гор.Морозовск Ростовской обл.РСФСР "
    "паспорт 60 17 067255 выдан 09.12"
)


def test_address_with_foreign_label_is_flagged():
    """Адрес + прилипший хвост «дата и место рождения … паспорт …».

    Адресных признаков тут навалом, поэтому позитивная грамматика молчит, и до
    этого правила поле уезжало в акт целиком с уровнем MEDIUM (без подсветки).
    """
    reason = FC.check_value("debtorAddress", _GLUED_ADDRESS)
    assert reason and reason.startswith(FC.FOREIGN_LABEL_REASON)


def test_glued_address_is_flagged_but_kept():
    """Решение Андрея: только помечаем. Где кончается адрес — машина не знает."""
    fields = {"debtorAddress": _GLUED_ADDRESS}
    issues = FC.apply_contract(fields)
    assert fields["debtorAddress"] == _GLUED_ADDRESS, "значение не чистим"
    assert [i for i in issues if i.field == "debtorAddress" and not i.cleared]


def test_glued_address_lights_up_the_field():
    """Консьюмер: фронт рисует рамку только на LOW (грабли §N.7 — мёртвая цепочка)."""
    fields = {"debtorAddress": _GLUED_ADDRESS}
    issues = FC.apply_contract(fields)
    assert FC.assess_quality(fields, issues)["debtorAddress"]["level"] == FC.LOW


def test_glued_address_in_entry_is_flagged_but_kept():
    """Записи идут мимо fields (ловушка §J.3) — правило обязано работать и там."""
    debtors = [{"name": "Иванов Иван Иванович", "address": _GLUED_ADDRESS}]
    issues = FC.check_entries(debtors, "debtors")
    assert debtors[0]["address"] == _GLUED_ADDRESS, "адрес записи не чистим"
    assert [i for i in issues if i.field == "debtors[0].address" and not i.cleared]


@pytest.mark.parametrize("value", [
    "344068, г. Ростов-на-Дону, ул. Красноармейская, д. 15, кв. 3",
    "115114, Москва, Дербеневская наб., д. 11",
    "Ростовская область, Морозовский район, г. Морозовск, ул. Калинина, д. 38",
    "347930, Ростовская обл., г. Таганрог, ул. Дзержинского, д. 156, кв. 12",
])
def test_clean_addresses_have_no_foreign_label(value):
    """Ложняк дороже пропуска: на 198 адресах golden-корпуса правило молчит."""
    assert FC.check_value("debtorAddress", value) is None


def test_own_address_labels_are_not_foreign():
    """«Место нахождения» — метка САМОГО адреса, флага быть не должно."""
    assert "Место нахождения" not in FC._FOREIGN_LABELS_IN_ADDRESS


# --- имя организации --------------------------------------------------------
def test_org_trailing_postal_index_is_cut():
    """Умерший ким клим.docx: к имени кредитора прилип индекс из адреса."""
    assert FC.clean_org_tail("ПАО Сбербанк России в лице Юго-Западного банка 344068") == \
        "ПАО Сбербанк России в лице Юго-Западного банка"


def test_fns_creditor_name_is_not_touched():
    """Анти-регрессия: «в лице Межрайонной ИФНС» — корректное имя, а не проза.

    34 документа ФНС в корпусе. Раньше мой же сканер аудита считал это мусором —
    контракт не должен повторять ту ошибку.
    """
    name = "ФНС России в лице Межрайонной ИФНС России № 26 по Ростовской области"
    assert FC.clean_org_tail(name) == name
    assert FC.check_value("creditorName", name) is None


def test_sberbank_branch_name_is_not_touched():
    """«ПАО Сбербанк в лице филиала - Юго-Западный Банк» — так и пишут в заявлении."""
    name = "ПАО Сбербанк в лице филиала - Юго-Западный Банк ПАО Сбербанк"
    assert FC.clean_org_tail(name) == name


# --- владение текстом -------------------------------------------------------
def test_cross_field_court_name_in_money_field():
    """Корень бага: один и тот же текст в courtName и в loanDebt."""
    fields = {"courtName": "Арбитражный суд Ростовской области",
              "loanDebt": "Арбитражный суд Ростовской области"}
    issues = FC.check_cross_field(fields)
    assert [i for i in issues if i.field == "loanDebt"]
    assert not [i for i in issues if i.field == "courtName"], "владелец не жертва"


def test_cross_field_creditor_name_in_debtor_address():
    """applicantAddress = «ПАО Сбер» — префикс creditorName."""
    fields = {"creditorName": "ПАО Сбербанк", "applicantAddress": "ПАО Сбер"}
    assert [i for i in FC.check_cross_field(fields) if i.field == "applicantAddress"]


def test_cross_field_ignores_identical_legit_addresses():
    """Адрес кредитора и должника могут совпасть (оба — тот же город/дом).

    Оба поля одного типа — конфликта нет: несовместимы только РАЗНЫЕ типы.
    """
    addr = "344068, г. Ростов-на-Дону, ул. Ленина, д. 5"
    assert not FC.check_cross_field({"creditorAddress": addr, "applicantAddress": addr})


def test_apply_contract_clears_victim_and_keeps_owner():
    fields = {"courtName": "Арбитражный суд Ростовской области",
              "loanDebt": "Арбитражный суд Ростовской области",
              "totalDebt": "25 000,00"}
    FC.apply_contract(fields)
    assert "loanDebt" not in fields
    assert fields["courtName"] == "Арбитражный суд Ростовской области"
    assert fields["totalDebt"] == "25 000,00"


# --- записи, строящиеся мимо fields ----------------------------------------
def test_entries_addresses_are_checked():
    """Ловушка §J.3: debtors[] строится отдельным путём, мимо fields."""
    debtors = [{"name": "Иванов Иван Иванович", "address": "ПАО Сбер"}]
    issues = FC.check_entries(debtors, "debtors")
    assert issues and debtors[0]["address"] == ""


def test_entries_broken_inn_is_flagged_not_cleared():
    """A53-9758…docx: битый ИНН доезжает до карточки должника мимо fields.

    `fio_detector` берёт первый кандидат, когда ни один не прошёл контрольную
    сумму, — ровно тот же приём, что чинили в parties_mixin. Правило реквизитов
    то же: помечаем, но оставляем — юрист правит цифру, а не набирает двенадцать.
    """
    debtors = [{"name": "Иванов Иван Иванович", "inn": "612102429513"}]
    issues = FC.check_entries(debtors, "debtors")
    assert debtors[0]["inn"] == "612102429513"
    assert [i for i in issues if i.field == "debtors[0].inn" and not i.cleared]


def test_entries_valid_requisites_are_silent():
    """Анти-ложняк: в корпусе 13 ОГРН и 4 ОГРНИП записей — все обязаны молчать."""
    debtors = [{"name": "ООО Ромашка", "inn": "612102152288", "ogrn": "1026101344664"},
               {"name": "Иванов Иван Иванович", "ogrnip": "317619600232839"}]
    assert not FC.check_entries(debtors, "debtors")


def test_entries_keep_valid_address():
    debtors = [{"name": "Иванов Иван Иванович",
                "address": "347561, Ростовская область, с. Развильное, ул. Соляника, д. 20"}]
    assert not FC.check_entries(debtors, "debtors")
    assert debtors[0]["address"]


# --- инвариант каскада ------------------------------------------------------
def test_find_issues_does_not_mutate():
    """Чекпоинт обязан быть наблюдателем: правит только apply_contract."""
    fields = {"courtName": "Арбитражный суд Ростовской области",
              "loanDebt": "Арбитражный суд Ростовской области"}
    before = dict(fields)
    assert FC.find_issues(fields)
    assert fields == before


def test_find_issues_silent_on_clean_fields():
    fields = {"courtName": "Арбитражный суд Ростовской области", "loanDebt": "25 000,00",
              "creditorName": "ПАО Сбербанк", "inn": "612102152288"}
    assert not FC.find_issues(fields)


def test_unknown_field_is_never_touched():
    """Поля вне реестра не проверяем: молчать безопаснее, чем чистить непонятое."""
    assert FC.check_value("someFutureField", "что угодно") is None


def test_checkpoint_raises_only_in_strict_mode():
    """В проде чекпоинт лишь пишет в лог: ронять разбор из-за одного поля нельзя.

    В строгом режиме (SBERACT_STRICT_CONTRACT=1) — падает, показывая ШАГ каскада,
    на котором словарь испортился. Зовём метод несвязанным, чтобы не поднимать
    spaCy-модель ради проверки трёх строк.
    """
    import types

    from document_analyzer import DocumentAnalyzer

    dirty = {"courtName": "Арбитражный суд Ростовской области",
             "loanDebt": "Арбитражный суд Ростовской области"}

    DocumentAnalyzer._contract_checkpoint(
        types.SimpleNamespace(_STRICT_CONTRACT=False), dirty, "шаг")  # молчит

    with pytest.raises(AssertionError, match="финансовый каскад"):
        DocumentAnalyzer._contract_checkpoint(
            types.SimpleNamespace(_STRICT_CONTRACT=True), dirty, "финансовый каскад")


# --- уровень доверия к полю -------------------------------------------------
def test_quality_marks_contract_victims_low():
    fields = {"courtName": "Арбитражный суд Ростовской области"}
    issues = [FC.Issue("loanDebt", "в денежном поле текст, а не сумма",
                       "Арбитражный суд Ростовской области")]
    q = FC.assess_quality(fields, issues)
    assert q["loanDebt"]["level"] == FC.LOW
    assert q["loanDebt"]["reasons"]


def test_quality_marks_registry_value_high():
    """Значение из справочника независимо от разбора текста — его не перепроверяют."""
    q = FC.assess_quality({"creditorAddress": "115114, Москва, Дербеневская наб., 11"},
                          [], {"creditorAddress": FC.SOURCE_REGISTRY})
    assert q["creditorAddress"]["level"] == FC.HIGH
    assert q["creditorAddress"]["source"] == FC.SOURCE_REGISTRY


def test_quality_marks_checksum_requisite_high():
    """Контрольная сумма — независимое подтверждение: 10 цифр случайно не совпадут."""
    q = FC.assess_quality({"inn": "612102152288"}, [])
    assert q["inn"]["level"] == FC.HIGH


def test_quality_broken_requisite_is_low_not_high():
    """Битый ИНН помечен, но НЕ вычищен (решение Андрея) — уровень всё равно LOW."""
    fields = {"inn": "612102429513"}
    issues = FC.apply_contract(fields)
    q = FC.assess_quality(fields, issues)
    assert fields["inn"] == "612102429513"
    assert q["inn"]["level"] == FC.LOW
    assert q["inn"]["cleared"] is False


def test_quality_default_is_medium_not_invented_number():
    """Обычное поле — MEDIUM: подтвердить нечем, и врать цифрой мы не будем."""
    q = FC.assess_quality({"debtorName": "Иванов Иван Иванович"}, [])
    assert q["debtorName"]["level"] == FC.MEDIUM


def test_quality_skips_empty_fields():
    q = FC.assess_quality({"debtorName": "", "inn": None, "courtName": []}, [])
    assert q == {}


def test_quality_covers_entry_issues():
    """Претензии к записям (debtors[0].address) обязаны попадать и в качество.

    Иначе список сверху говорит о проблеме, а карточка должника молчит — юрист
    видит противоречие и перестаёт доверять подсветке.
    """
    debtors = [{"name": "Иванов Иван Иванович", "address": "ПАО Сбер"}]
    issues = FC.check_entries(debtors, "debtors")
    q = FC.assess_quality({}, issues)
    assert q["debtors[0].address"]["level"] == FC.LOW


def test_checkpoint_silent_on_clean_fields_even_in_strict_mode():
    import types

    from document_analyzer import DocumentAnalyzer

    clean = {"courtName": "Арбитражный суд Ростовской области", "loanDebt": "25 000,00"}
    DocumentAnalyzer._contract_checkpoint(
        types.SimpleNamespace(_STRICT_CONTRACT=True), clean, "шаг")


# --- Заполнители из шаблона заявителя (02.09.2026) ---------------------------
#
# Заявитель печатает заполнитель из СВОЕГО шаблона, когда данных у него нет.
# Реальный случай корпуса: «Место рождения: None» — чужой генератор вывел
# питоновский None. Разбор отработал ВЕРНО, грязный тут вход, поэтому фильтр
# стоит на границе контракта, а не в конкретном извлекателе.

@pytest.mark.parametrize("значение", [
    "None", "none", "NULL", "nan", "N/A", "-", "—", "н/д", "нд",
    "нет данных", "не указано", "не указана", "отсутствует", "____", "XXX",
])
def test_заполнитель_опознан(значение):
    assert FC.is_placeholder(значение)


@pytest.mark.parametrize("значение", [
    "г. Ростов-на-Дону", "Иванов Иван Иванович", "7707083893",
    "нет данных о регистрации права",   # заполнитель — только ЦЕЛОЕ значение
    "Нонна Петровна", "Ноне Ивановне",  # начинается на «нон», но не заполнитель
])
def test_настоящее_значение_не_заполнитель(значение):
    assert not FC.is_placeholder(значение)


def test_заполнитель_вычищается_из_полей():
    поля = {"birthPlace": "None", "debtorName": "Иванов Иван Иванович"}
    претензии = FC.apply_contract(поля)
    assert "birthPlace" not in поля
    assert поля["debtorName"] == "Иванов Иван Иванович"
    assert [i.field for i in претензии] == ["birthPlace"]
    assert претензии[0].cleared is True


def test_заполнитель_вычищается_из_карточки_должника():
    """Тот же «None» приезжает и в fields, и в debtors[0] — разными путями."""
    записи = [{"name": "Иванов Иван Иванович", "birthPlace": "None"}]
    претензии = FC.check_entries(записи, "debtors")
    assert записи[0]["birthPlace"] == ""
    assert [i.field for i in претензии] == ["debtors[0].birthPlace"]
