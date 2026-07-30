# -*- coding: utf-8 -*-
"""Пакет ипотечной генерации: всегда 5 актов, пятый зависит от настроек формы.

Четыре акта одинаковы при любом выборе; «Решение резолютивка» ветвится по виду
ипотеки, солидарности и наличию представителей. Проверяем все 9 сочетаний и то,
что каждый выбранный файл реально лежит на диске — опечатка в имени иначе
всплывёт только у юриста при генерации.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from document_generator import DocumentGenerator  # noqa: E402

ALWAYS = ("mortgage_summons", "mortgage_acceptance_short", "mortgage_acceptance_long", "mortgage_notice")


@pytest.fixture(scope="module")
def gen():
    return DocumentGenerator()


def _data(kind=None, solidary=None, representative=None, respondent_representative=None, **extra):
    fields = dict(extra)
    if kind is not None:
        fields["selectedMortgageKind"] = kind
    if solidary is not None:
        fields["solidaryLiability"] = solidary
    if representative is not None:
        fields["representativeName"] = representative
    if respondent_representative is not None:
        fields["respondentRepresentativeName"] = respondent_representative
    return {"fields": fields}


# --- состав пакета ----------------------------------------------------------
@pytest.mark.parametrize("kind", ["civil", "military", "ddu"])
@pytest.mark.parametrize("solidary", [None, "true"])
def test_always_five_acts(gen, kind, solidary):
    templates = gen._get_mortgage_templates(_data(kind=kind, solidary=solidary))
    assert len(templates) == 5
    assert set(ALWAYS).issubset(templates)
    assert "mortgage_decision" in templates


def test_four_acts_are_the_same_regardless_of_settings(gen):
    a = gen._get_mortgage_templates(_data(kind="civil"))
    b = gen._get_mortgage_templates(_data(kind="ddu", solidary="true", representative="Иванов И.И."))
    for key in ALWAYS:
        assert a[key]["path"] == b[key]["path"]


def test_all_template_files_exist(gen):
    """Каждый из 13 файлов пакета лежит на диске под тем именем, что в резолвере."""
    seen = set()
    for kind in ("civil", "military", "ddu"):
        for solidary in (None, "true"):
            for rep in (None, "Иванов И.И."):
                templates = gen._get_mortgage_templates(_data(kind=kind, solidary=solidary, representative=rep))
                for key, tpl in templates.items():
                    seen.add(tpl["path"])
                    assert tpl["path"].exists(), f"нет файла для {key}: {tpl['path']}"
    assert len(seen) == 13


# --- ветвление решения-резолютивки ------------------------------------------
CASES = [
    ("civil", None, None, "реш_рез обычная должник не солидарное ипот.docx"),
    ("civil", "true", None, "реш_рез обычная должник солидарное ипот.docx"),
    ("civil", None, "Иванов И.И.", "реш_рез обычная представители не солидарное ипотека.docx"),
    ("civil", "true", "Иванов И.И.", "реш_рез представители солидарное обычная ипот.docx"),
    ("ddu", None, None, "реш_рез дду должник не_солидарное ипотека.docx"),
    ("ddu", "true", None, "реш_рез дду должник солидарное ипотека.docx"),
    ("ddu", None, "Иванов И.И.", "реш_рез дду представители не_солидарное ипотека.docx"),
    ("ddu", "true", "Иванов И.И.", "реш_рез дду представители солидарное ипотека.docx"),
]


@pytest.mark.parametrize("kind,solidary,representative,expected", CASES)
def test_decision_branching(gen, kind, solidary, representative, expected):
    templates = gen._get_mortgage_templates(_data(kind=kind, solidary=solidary, representative=representative))
    assert templates["mortgage_decision"]["path"].name == expected


@pytest.mark.parametrize("solidary", [None, "true"])
@pytest.mark.parametrize("representative", [None, "Иванов И.И."])
def test_military_ignores_flags(gen, solidary, representative):
    """Военная ипотека — один акт на все сочетания солидарности и представителей."""
    templates = gen._get_mortgage_templates(_data(kind="military", solidary=solidary, representative=representative))
    assert templates["mortgage_decision"]["path"].name == "Решение резолютивка военка.docx"


# --- разбор настроек --------------------------------------------------------
def test_respondent_representative_alone_counts(gen):
    """«Хотя бы один»: представителя ответчика достаточно для варианта «представители»."""
    templates = gen._get_mortgage_templates(_data(kind="civil", respondent_representative="Петров П.П."))
    assert "представители" in templates["mortgage_decision"]["path"].name


def test_user_choice_beats_analyzer(gen):
    """selectedMortgageKind перебивает автоопределённый mortgageKind."""
    data = {"fields": {"selectedMortgageKind": "ddu", "mortgageKind": "military"}}
    assert "дду" in str(gen._get_mortgage_templates(data)["mortgage_decision"]["path"])


def test_analyzer_kind_used_when_user_did_not_choose(gen):
    data = {"fields": {"mortgageKind": "military"}}
    assert gen._get_mortgage_templates(data)["mortgage_decision"]["path"].name == "Решение резолютивка военка.docx"


def test_defaults_to_civil_debtor_non_solidary(gen):
    """Пустая форма — обычная ипотека, должник, не солидарное."""
    assert gen._get_mortgage_templates({})["mortgage_decision"]["path"].name == (
        "реш_рез обычная должник не солидарное ипот.docx"
    )


def test_unknown_kind_falls_back_to_civil(gen):
    assert "обычная" in str(gen._get_mortgage_templates(_data(kind="какая-то"))["mortgage_decision"]["path"])


def test_selection_read_from_top_level_data(gen):
    """Селекции могут прийти не в fields, а в корне data — читаем оба места."""
    data = {"selectedMortgageKind": "ddu", "solidaryLiability": "true"}
    assert gen._get_mortgage_templates(data)["mortgage_decision"]["path"].name == (
        "реш_рез дду должник солидарное ипотека.docx"
    )


def test_solidary_only_on_exact_true(gen):
    """Снятая галочка приходит пустой строкой — это НЕ солидарное."""
    assert "не солидарное" in gen._get_mortgage_templates(_data(kind="civil", solidary=""))["mortgage_decision"]["path"].name
