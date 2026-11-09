# -*- coding: utf-8 -*-
"""Регрессия по сценариям из уаууа.txt (сессия 22.07.2026): для каждой исправленной
ветки _map_selected_acts_to_templates — один представитель, с проверкой ТОЧНОГО пути
и что файл реально существует на диске. Не покрывает резолютивки/«короткий текст» —
эта работа отложена пользователем на следующую итерацию.
"""
import pytest

from document_generator import DocumentGenerator


@pytest.fixture
def gen():
    return DocumentGenerator()


def _map(gen, act_id, entity_type, collateral_option, **data):
    templates, unresolved = gen._map_selected_acts_to_templates(act_id, entity_type, collateral_option, data)
    assert unresolved == [], f"акт не резолвится: {unresolved}"
    return templates


def _assert_path_ends_with(path, *parts):
    assert path.exists(), f"файл шаблона не найден на диске: {path}"
    tail = "/".join(parts)
    assert str(path).replace("\\", "/").endswith(tail), f"{path} не оканчивается на {tail}"


# --- Финальные СА (введение процедуры, не путать с final_rtk_inclusion) ---

def test_final_realization_no_collateral_defaults_to_initiation_decision(gen):
    templates = _map(gen, "final_realization", "individual", "no_collateral",
                      selectedApplicationKind="other")
    _assert_path_ends_with(templates["final_realization"]["path"], *"Банкротство/Инициирование/ФЛ/Кредиторы/Незалог/Реализация/решение реализ заемщик.docx".split("/"))


def test_final_restructuring_collateral(gen):
    templates = _map(gen, "final_restructuring", "individual", "collateral")
    _assert_path_ends_with(templates["final_restructuring"]["path"], *"Банкротство/Инициирование/ФЛ/Кредиторы/Залог/Реструктуризация/Определение о введении реструктуризации долгов (заемщик) (залог).docx".split("/"))


def test_final_restructuring_no_collateral(gen):
    templates = _map(gen, "final_restructuring", "individual", "no_collateral")
    _assert_path_ends_with(templates["final_restructuring"]["path"], *"Банкротство/Инициирование/ФЛ/Кредиторы/Незалог/Реструктуризация/Определение о введении реструктуризации ЗАЕМЩИК.docx".split("/"))


def test_final_observation_kfh_collateral(gen):
    templates = _map(gen, "final_observation", "kfh", "collateral")
    _assert_path_ends_with(templates["final_observation"]["path"], *"Банкротство/Инициирование/КФХ/Кредиторы/Обычный/Залог/Наблюдение/Наблюдение_ЮрЛицо.docx".split("/"))


def test_final_observation_legal_collateral(gen):
    templates = _map(gen, "final_observation", "legal", "collateral")
    _assert_path_ends_with(templates["final_observation"]["path"], *"Банкротство/Инициирование/ЮЛ/Кредиторы/Обычный/Залог/Наблюдение/Наблюдение_ЮрЛицо.docx".split("/"))


def test_final_observation_legal_no_collateral(gen):
    templates = _map(gen, "final_observation", "legal", "no_collateral")
    _assert_path_ends_with(templates["final_observation"]["path"], *"Банкротство/Инициирование/ЮЛ/Кредиторы/Обычный/Незалог/Наблюдение/Наблюдение_ЮрЛицо.docx".split("/"))


def test_final_competition_collateral_liquidation(gen):
    templates = _map(gen, "final_competition", "legal", "collateral",
                      selectedDebtorStatus="liquidation")
    _assert_path_ends_with(templates["final_competition"]["path"], *"Банкротство/Инициирование/ЮЛ/Кредиторы/Ликвидируемый/Залог/Конкурсное/О введении конкурсное ликвидируемый (залог).docx".split("/"))


def test_final_competition_no_collateral_absent(gen):
    templates = _map(gen, "final_competition", "legal", "no_collateral",
                      selectedDebtorStatus="absent")
    _assert_path_ends_with(templates["final_competition"]["path"], *"Банкротство/Инициирование/ЮЛ/Кредиторы/Отсутствующий/Незалог/Конкурсное/!О введении конкурсное отсутствующий.docx".split("/"))


# --- Определение ВКЛ в РТК (акт включения — отдельный от актов введения выше) ---

def test_rtk_inclusion_realization_no_collateral(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "individual", "no_collateral",
        {"final_rtk_inclusion_variant": "realization"}
    )
    _assert_path_ends_with(templates["rtk_inclusion"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Реализация/Вкл в РТК реализация полный текст.docx".split("/"))


def test_rtk_inclusion_competition_no_collateral(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "legal", "no_collateral",
        {"final_rtk_inclusion_variant": "competition"}
    )
    _assert_path_ends_with(templates["rtk_inclusion"]["path"], *"Банкротство/Включение в РТК/ЮЛ/Кредиторы/Обычный/Незалог/Конкурсное/Конкурсное_ВКЛ_в_РТК (без залога).docx".split("/"))


def test_rtk_inclusion_observation_kfh_collateral(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "kfh", "collateral",
        {"final_rtk_inclusion_variant": "observation"}
    )
    _assert_path_ends_with(templates["rtk_inclusion"]["path"], *"Банкротство/Включение в РТК/КФХ/Кредиторы/Обычный/Залог/Наблюдение/Наблюдение ВКЛ в РТК  Залог.docx".split("/"))


# --- Определение о принятии (acceptance_definition) ---

def test_acceptance_deceased(gen):
    templates = _map(gen, "acceptance_definition", "individual", "no_collateral",
                      selectedDebtorStatus="deceased")
    _assert_path_ends_with(templates["acceptance"]["path"], *"Банкротство/Инициирование/ФЛ/Кредиторы/Умерший/Первоначальные/Определение о принятии.docx".split("/"))


def test_acceptance_legal_initiation_liquidation(gen):
    templates = _map(gen, "acceptance_definition", "legal", "no_collateral",
                      selectedDebtorStatus="liquidation")
    _assert_path_ends_with(templates["acceptance"]["path"], *"Банкротство/Инициирование/ЮЛ/Кредиторы/Ликвидируемый/Незалог/Первоначальные/Определение о принятии.docx".split("/"))


def test_acceptance_individual_collateral_initiation(gen):
    templates = _map(gen, "acceptance_definition", "individual", "collateral",
                      selectedApplicationKind="other")
    _assert_path_ends_with(templates["acceptance"]["path"], *"Банкротство/Инициирование/ФЛ/Кредиторы/Залог/Первоначальные/Определение о принятии залог.docx".split("/"))


def test_acceptance_individual_collateral_rtk_realization(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "acceptance_definition,final_rtk_inclusion", "individual", "collateral",
        {"selectedApplicationKind": "rtk", "final_rtk_inclusion_variant": "realization"}
    )
    _assert_path_ends_with(templates["acceptance"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Залог/Первоначальные/Определение о принятии реализация.docx".split("/"))


def test_acceptance_individual_no_collateral_initiation(gen):
    templates = _map(gen, "acceptance_definition", "individual", "no_collateral",
                      selectedApplicationKind="other")
    _assert_path_ends_with(templates["acceptance"]["path"], *"Банкротство/Инициирование/ФЛ/Кредиторы/Незалог/Первоначальные/Определение о принятии банкротство.docx".split("/"))


def test_acceptance_individual_no_collateral_rtk_default(gen):
    templates = _map(gen, "acceptance_definition", "individual", "no_collateral",
                      selectedApplicationKind="rtk")
    _assert_path_ends_with(templates["acceptance"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Первоначальные/Определение о принятии реализация.docx".split("/"))


# --- Принятие после Б/Д и Б/Д-блок ---

def test_acceptance_after_no_motion(gen):
    templates = _map(gen, "acceptance_after_no_motion", "individual", "no_collateral")
    _assert_path_ends_with(templates["acceptance_after_no_motion"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Первоначальные/Определение о принятии после БД реализация.docx".split("/"))


def test_acceptance_no_motion_no_duty(gen):
    templates = _map(gen, "acceptance_no_motion_no_duty", "individual", "no_collateral")
    _assert_path_ends_with(templates["acceptance_no_motion"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Первоначальные/Определение БД нет ГП реализация.docx".split("/"))


def test_acceptance_no_motion_no_duty_collateral(gen):
    templates = _map(gen, "acceptance_no_motion_no_duty_collateral", "individual", "collateral")
    _assert_path_ends_with(templates["acceptance_no_motion_collateral"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Залог/Первоначальные/Определение БД нет ГП залог реализация.docx".split("/"))


def test_acceptance_no_motion_other(gen):
    templates = _map(gen, "acceptance_no_motion_other", "individual", "no_collateral")
    _assert_path_ends_with(templates["acceptance_no_motion_other"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Первоначальные/Определение БД иное реализация.docx".split("/"))


# --- Промежуточные ---

def test_intermediate_postponement_both_collateral_options(gen):
    for collateral_option in ("no_collateral", "collateral"):
        templates = _map(gen, "intermediate_postponement", "individual", collateral_option)
        _assert_path_ends_with(templates["postponement"]["path"], *("Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Промежуточные/Отложение рестр+реал.docx" if collateral_option == "no_collateral" else "Банкротство/Включение в РТК/ФЛ/Кредиторы/Залог/Промежуточные/Отложение залог рестр+реал.docx").split("/"))


def test_intermediate_extend_no_motion(gen):
    templates = _map(gen, "intermediate_extend_no_motion", "individual", "no_collateral")
    _assert_path_ends_with(templates["extend_no_motion"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Промежуточные/Продление БД рестр+реал.docx".split("/"))


def test_intermediate_extend_simplified(gen):
    templates = _map(gen, "intermediate_extend_simplified", "individual", "no_collateral")
    _assert_path_ends_with(templates["extend_simplified"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Промежуточные/продление упрощенка ФЛ.docx".split("/"))


def test_intermediate_simplified_to_main(gen):
    templates = _map(gen, "intermediate_simplified_to_main", "individual", "no_collateral")
    _assert_path_ends_with(templates["simplified_to_main"]["path"], *"Банкротство/Включение в РТК/ФЛ/Кредиторы/Незалог/Промежуточные/Переход из упрощенки в основное производство реализация.docx".split("/"))


# --- Короткий текст (резолютивка) — один общий на генерацию по флагу selectedShortText ---

def test_short_text_realization_no_collateral_exists(gen):
    templates, missing = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "individual", "no_collateral",
        {"selectedApplicationKind": "rtk", "selectedShortText": "true",
         "final_rtk_inclusion_variant": "realization"},
    )
    assert not missing
    _assert_path_ends_with(
        templates["short_text"]["path"], "Банкротство", "Включение в РТК", "ФЛ",
        "Кредиторы", "Незалог", "Реализация", "Вкл в РТК реализация резолютивная часть.docx",
    )

def test_short_text_restructuring_collateral_exists(gen):
    templates, missing = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "individual", "collateral",
        {"selectedApplicationKind": "rtk", "selectedShortText": "true",
         "final_rtk_inclusion_variant": "restructuring"},
    )
    assert not missing
    _assert_path_ends_with(
        templates["short_text"]["path"], "Банкротство", "Включение в РТК", "ФЛ",
        "Кредиторы", "Залог", "Реструктуризация", "Вкл в РТК реструктуризация залог резолютивная часть.docx",
    )

def test_initiation_competition_ignores_short_text(gen):
    """Инициирование не запрашивает дополнительную резолютивку."""
    data = {"selectedApplicationKind": "other", "selectedShortText": "true",
            "selectedDebtorStatus": "liquidation"}
    templates, missing = gen._map_selected_acts_to_templates(
        "final_competition", "legal", "no_collateral", data,
    )
    assert templates["final_competition"]["path"].is_file()
    assert "short_text" not in templates
    assert missing == []
    assert "short_text" not in data.get("_unresolvedReasons", {})

def test_short_text_absent_when_flag_off(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_realization", "individual", "no_collateral", {}
    )
    assert "short_text" not in templates
