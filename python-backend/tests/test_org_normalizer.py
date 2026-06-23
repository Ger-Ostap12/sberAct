# -*- coding: utf-8 -*-
"""Фича A: канонизация организаций и матч реестра кредиторов."""
import pytest

from org_normalizer import norm_org_key, base_org_name


# Группы: разные написания одной организации должны схлопываться в один ключ.
GROUPS = {
    "Сбербанк": [
        "ПАО Сбербанк", "ПАО «Сбербанк»", 'ПАО "Сбербанк"',
        "Публичное акционерное общество «Сбербанк России»",
    ],
    "Альфа-Банк": [
        "АО «АЛЬФА-БАНК»", "Акционерное общество «АЛЬФА-БАНК»",
        "АО АЛЬФА-БАНК", "АО «Альфа-Банк»",
    ],
    "Форте Пром Стил": [
        "ООО «Форте Пром Стил»", "ООО Форте Пром Стил",
        "Общество с ограниченной ответственностью «Форте Пром Стил»",
    ],
    "Колор": [
        "ООО «КОЛОР»", 'ООО "Колор"',
        "Общество с ограниченной ответственностью «КОЛОР»",
    ],
}


@pytest.mark.parametrize("group", GROUPS)
def test_variants_collapse_to_single_key(group):
    """Все варианты написания организации дают один канонический ключ."""
    keys = {norm_org_key(v) for v in GROUPS[group]}
    assert len(keys) == 1, f"{group}: ожидался 1 ключ, получено {keys}"


def test_full_form_matches_creditor_registry():
    """Полная правовая форма и кавычки сводятся к базовому имени и матчат реестр."""
    from document_analyzer import _match_creditor_registry

    for name in [
        "Публичное акционерное общество «Сбербанк России»",
        "ПАО «Сбербанк»",
        "ПАО Сбербанк",
    ]:
        matched = _match_creditor_registry(name)
        assert matched is not None, f"{name} не найден в реестре"
        assert matched["inn"] == "7707083893"


def test_base_org_name_strips_legal_form():
    assert base_org_name("Общество с ограниченной ответственностью «КОЛОР»") == "колор"
    assert base_org_name("ПАО «Сбербанк России»") == "сбербанк"


def test_unrelated_orgs_have_distinct_keys():
    """Разные организации не должны коллапсировать в один ключ."""
    keys = {
        norm_org_key("ООО «КОЛОР»"),
        norm_org_key("ООО «Форте Пром Стил»"),
        norm_org_key("АО «АЛЬФА-БАНК»"),
    }
    assert len(keys) == 3
