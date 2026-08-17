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
    _assert_path_ends_with(templates["final_realization"]["path"],
                            "физ иниц рестр + реал", "решение реализ заемщик.docx")


def test_final_restructuring_collateral(gen):
    templates = _map(gen, "final_restructuring", "individual", "collateral")
    _assert_path_ends_with(templates["final_restructuring"]["path"],
                            "Залог", "Реструктуризация",
                            "Определение о введении реструктуризации долгов (заемщик) (залог).docx")


def test_final_restructuring_no_collateral(gen):
    templates = _map(gen, "final_restructuring", "individual", "no_collateral")
    _assert_path_ends_with(templates["final_restructuring"]["path"],
                            "физ иниц рестр + реал", "Определение о введении реструктуризации ЗАЕМЩИК.docx")


def test_final_observation_kfh_collateral(gen):
    templates = _map(gen, "final_observation", "kfh", "collateral")
    _assert_path_ends_with(templates["final_observation"]["path"], "КФХ", "Наблюдение КФХ Залог.docx")


def test_final_observation_legal_collateral(gen):
    templates = _map(gen, "final_observation", "legal", "collateral")
    _assert_path_ends_with(templates["final_observation"]["path"],
                            "Залог", "Наблюдение", "Принятие РТК наблюдение (залог).docx")


def test_final_observation_legal_no_collateral(gen):
    templates = _map(gen, "final_observation", "legal", "no_collateral")
    _assert_path_ends_with(templates["final_observation"]["path"],
                            "юр ВКЛ в РТК наблюдение", "Наблюдение_ЮрЛицо.docx")


def test_final_competition_collateral_liquidation(gen):
    templates = _map(gen, "final_competition", "legal", "collateral",
                      selectedDebtorStatus="liquidation")
    _assert_path_ends_with(templates["final_competition"]["path"],
                            "Залог", "Конкурсное", "О введении конкурсное ликвидируемый (залог).docx")


def test_final_competition_no_collateral_absent(gen):
    templates = _map(gen, "final_competition", "legal", "no_collateral",
                      selectedDebtorStatus="absent")
    _assert_path_ends_with(templates["final_competition"]["path"],
                            "юр инициир набл + конкурс", "!О введении конкурсное отсутствующий.docx")


# --- Определение ВКЛ в РТК (акт включения — отдельный от актов введения выше) ---

def test_rtk_inclusion_realization_no_collateral(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "individual", "no_collateral",
        {"final_rtk_inclusion_variant": "realization"}
    )
    _assert_path_ends_with(templates["rtk_inclusion"]["path"],
                            "физ реализация ВКЛ в РТК", "Реализация ВКЛ несколько договоров.docx")


def test_rtk_inclusion_competition_no_collateral(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "legal", "no_collateral",
        {"final_rtk_inclusion_variant": "competition"}
    )
    _assert_path_ends_with(templates["rtk_inclusion"]["path"],
                            "юр инициир набл + конкурс", "Конкурсное_ВКЛ_в_РТК (без залога).docx")


def test_rtk_inclusion_observation_kfh_collateral(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_rtk_inclusion", "kfh", "collateral",
        {"final_rtk_inclusion_variant": "observation"}
    )
    _assert_path_ends_with(templates["rtk_inclusion"]["path"], "КФХ", "Наблюдение КФХ Залог.docx")


# --- Определение о принятии (acceptance_definition) ---

def test_acceptance_deceased(gen):
    templates = _map(gen, "acceptance_definition", "individual", "no_collateral",
                      selectedDebtorStatus="deceased")
    _assert_path_ends_with(templates["acceptance"]["path"],
                            "умерший", "Принятие заявления о призании должника банкротом умерший.docx")


def test_acceptance_legal_initiation_liquidation(gen):
    templates = _map(gen, "acceptance_definition", "legal", "no_collateral",
                      selectedDebtorStatus="liquidation")
    _assert_path_ends_with(templates["acceptance"]["path"],
                            "юр инициир набл + конкурс", "О принятии заявления.docx")


def test_acceptance_individual_collateral_initiation(gen):
    templates = _map(gen, "acceptance_definition", "individual", "collateral",
                      selectedApplicationKind="other")
    _assert_path_ends_with(templates["acceptance"]["path"], "Залог", "принятие иниц залог недвига.docx")


def test_acceptance_individual_collateral_rtk_realization(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "acceptance_definition,final_rtk_inclusion", "individual", "collateral",
        {"selectedApplicationKind": "rtk", "final_rtk_inclusion_variant": "realization"}
    )
    _assert_path_ends_with(templates["acceptance"]["path"],
                            "Залог", "Реализация", "Реализация принятие РТК Залог.docx")


def test_acceptance_individual_no_collateral_initiation(gen):
    templates = _map(gen, "acceptance_definition", "individual", "no_collateral",
                      selectedApplicationKind="other")
    _assert_path_ends_with(templates["acceptance"]["path"],
                            "физ иниц рестр + реал", "Принятие заявления о призании должника банкротом.docx")


def test_acceptance_individual_no_collateral_rtk_default(gen):
    templates = _map(gen, "acceptance_definition", "individual", "no_collateral",
                      selectedApplicationKind="rtk")
    _assert_path_ends_with(templates["acceptance"]["path"],
                            "физ реализация ВКЛ в РТК", "Реализация принятие РТК.docx")


# --- Принятие после Б/Д и Б/Д-блок ---

def test_acceptance_after_no_motion(gen):
    templates = _map(gen, "acceptance_after_no_motion", "individual", "no_collateral")
    _assert_path_ends_with(templates["acceptance_after_no_motion"]["path"], "принятие после БД.docx")


def test_acceptance_no_motion_no_duty(gen):
    templates = _map(gen, "acceptance_no_motion_no_duty", "individual", "no_collateral")
    _assert_path_ends_with(templates["acceptance_no_motion"]["path"],
                            "внести Обездвижка", "Определение БД нет ГП.docx")


def test_acceptance_no_motion_no_duty_collateral(gen):
    templates = _map(gen, "acceptance_no_motion_no_duty_collateral", "individual", "collateral")
    _assert_path_ends_with(templates["acceptance_no_motion_collateral"]["path"],
                            "внести Обездвижка", "Определение БД не гп залог.docx")


def test_acceptance_no_motion_other(gen):
    templates = _map(gen, "acceptance_no_motion_other", "individual", "no_collateral")
    _assert_path_ends_with(templates["acceptance_no_motion_other"]["path"], "Определение БД иное.docx")


# --- Промежуточные ---

def test_intermediate_postponement_both_collateral_options(gen):
    for collateral_option in ("no_collateral", "collateral"):
        templates = _map(gen, "intermediate_postponement", "individual", collateral_option)
        _assert_path_ends_with(templates["postponement"]["path"], "внести отложка", "отложение.docx")


def test_intermediate_extend_no_motion(gen):
    templates = _map(gen, "intermediate_extend_no_motion", "individual", "no_collateral")
    _assert_path_ends_with(templates["extend_no_motion"]["path"], "продление БД.docx")


def test_intermediate_extend_simplified(gen):
    templates = _map(gen, "intermediate_extend_simplified", "individual", "no_collateral")
    _assert_path_ends_with(templates["extend_simplified"]["path"], "внести отложка", "продление упрощенка.docx")


def test_intermediate_simplified_to_main(gen):
    templates = _map(gen, "intermediate_simplified_to_main", "individual", "no_collateral")
    _assert_path_ends_with(templates["simplified_to_main"]["path"],
                            "внести Назначение после упрощенки", "Переход из упрощенки в основное производство.docx")


# --- Короткий текст (резолютивка) — один общий на генерацию по флагу selectedShortText ---

def test_short_text_realization_no_collateral_exists(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_realization", "individual", "no_collateral",
        {"selectedShortText": "true"}
    )
    assert "short_text" in templates
    _assert_path_ends_with(templates["short_text"]["path"],
                            "физ реализация ВКЛ в РТК", "Резолютивка ВКЛ реализация.docx")


def test_short_text_restructuring_collateral_exists(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_restructuring", "individual", "collateral",
        {"selectedShortText": "true"}
    )
    assert "short_text" in templates
    _assert_path_ends_with(templates["short_text"]["path"],
                            "Залог", "Реструктуризация", "Резолютивка ВКЛ реструктуризация Залог.docx")


def test_short_text_competition_missing_reports_no_template(gen):
    """Для конкурсного резолютивки нет — путь указывает на несуществующий файл, чтобы
    генератор выдал «нет шаблона» (файл шаблона не найден)."""
    templates, _ = gen._map_selected_acts_to_templates(
        "final_competition", "legal", "no_collateral",
        {"selectedShortText": "true", "selectedDebtorStatus": "liquidation"}
    )
    assert "short_text" in templates
    assert not templates["short_text"]["path"].exists()


def test_short_text_absent_when_flag_off(gen):
    templates, _ = gen._map_selected_acts_to_templates(
        "final_realization", "individual", "no_collateral", {}
    )
    assert "short_text" not in templates
