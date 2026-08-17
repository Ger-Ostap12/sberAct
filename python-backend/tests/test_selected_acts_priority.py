# -*- coding: utf-8 -*-
"""Тесты приоритета выбранных пользователем актов над авто-подобранным template_type.

Требование Андрея: генерируются РОВНО те акты, которые выбрал пользователь — другие
генериться не должны. Покрывают три механизма, которые это нарушали:

  • can_use_selected_acts требовал пустой template_type, а фронт всегда шлёт
    непустой (pickTemplate() с фолбэком 'rtk_single_obligation') → выбор
    игнорировался всегда, генерировался стандартный комплект;
  • при неудачном маппинге выбранных актов был тихий фолбэк на стандартный комплект;
  • _resolve_template_path при отсутствии файла подставлял «любой .docx из папки» —
    под видом выбранного акта выдавался чужой (наблюдение → конкурсное).
"""
import json

import pytest

from document_generator import DocumentGenerator


@pytest.fixture
def gen():
    return DocumentGenerator()


BASE = {
    "caseNumber": "А53-1234/2026",
    "debtorName": "Иванов Иван Иванович",
    "applicantName": "Иванов Иван Иванович",
    "creditorName": "ПАО Сбербанк",
    "entityType": "individual",
    "date": "17.07.2026",
    "judge": "Петров П.П.",
    "obligations": [],
}

# Так шлёт фронт: template_type подобран автоматически и НИКОГДА не пустой.
AUTO_TEMPLATE = "rtk_single_obligation"


def _data(**extra):
    data = dict(BASE)
    data.update(extra)
    return data


def test_single_selected_act_generates_only_that_act(gen):
    """Выбран один акт — ровно один документ, а не стандартный комплект."""
    result = gen.generate(AUTO_TEMPLATE, _data(
        selectedActsIds="acceptance_definition",
        selectedActsData=json.dumps([{"id": "acceptance_definition", "selected": True}]),
        selectedEntityType="individual",
        selectedCollateralOption="no_collateral",
    ))

    assert result["success"] and result["count"] == 1
    assert list(result["documents"]) == ["acceptance"]


def test_two_selected_acts_generate_exactly_two(gen):
    result = gen.generate(AUTO_TEMPLATE, _data(
        selectedActsIds="acceptance_definition,intermediate_postponement",
        selectedEntityType="individual",
        selectedCollateralOption="no_collateral",
    ))

    assert result["success"] and result["count"] == 2
    assert set(result["documents"]) == {"acceptance", "postponement"}


def test_unknown_act_errors_without_substituting_standard_set(gen):
    """Нераспознанный акт — ошибка. Стандартный комплект подставлять нельзя."""
    result = gen.generate(AUTO_TEMPLATE, _data(selectedActsIds="bogus_act_id"))

    assert result["success"] is False
    assert "bogus_act_id" in result["error"]
    assert not result.get("documents")


def test_missing_template_warns_and_does_not_substitute_another_act(gen, tmp_path, monkeypatch):
    """Шаблона выбранного акта нет физически: остальные выбранные акты
    генерируются, по отсутствующему приходит warning — но чужой акт под его именем
    не подставляется. Результат маппинга подменён напрямую (а не через реально
    отсутствующий файл в Templates), чтобы тест не зависел от того, какой конкретно
    шаблон отсутствует на диске в данный момент."""
    real_return_path = gen._templates_root() / "промежуточные_особые" / "внести Возврат" / "возврат ртк ГП.docx"
    assert real_return_path.exists(), "тест рассчитан на существующий шаблон 'Возврат'"
    corrupted_templates = {
        "return": {"name": "Возврат (РТК ГП)", "path": real_return_path, "order": 1},
        "rtk_inclusion": {"name": "Определение ВКЛ в РТК (реализация)", "path": tmp_path / "нет-такого-файла.docx", "order": 2},
    }
    monkeypatch.setattr(gen, "_map_selected_acts_to_templates", lambda *a, **kw: (corrupted_templates, []))

    result = gen.generate(AUTO_TEMPLATE, _data(
        selectedActsIds="intermediate_return,final_rtk_inclusion",
        selectedActsData=json.dumps([
            {"id": "final_rtk_inclusion", "selected": True, "rtkVariant": "realization"},
        ]),
        selectedEntityType="individual",
        selectedCollateralOption="no_collateral",
    ))

    assert result["success"] and result["count"] == 1
    assert list(result["documents"]) == ["return"]
    assert any("файл шаблона не найден" in w for w in result["warnings"])


def test_duplicate_act_ids_are_not_reported_as_unresolved(gen):
    templates, unresolved = gen._map_selected_acts_to_templates(
        "acceptance_definition,acceptance_definition", "individual", "no_collateral", {}
    )
    assert unresolved == [] and len(templates) == 1


def test_strict_resolve_refuses_arbitrary_docx_substitution(gen):
    """Слепой фолбэк «любой .docx из папки» подменял наблюдение конкурсным.
    Для выбранных актов он выключен: путь возвращается как есть (файла нет)."""
    missing = gen._templates_root() / "шаблоны актов без залогов" / "ртк.docx"
    assert not missing.exists(), "тест рассчитан на отсутствующий шаблон"

    assert gen._resolve_template_path(missing, allow_any_docx_fallback=False) == missing
    # Стандартная логика поведение сохраняет — там подмена по-прежнему разрешена.
    assert gen._resolve_template_path(missing).exists()


def test_standard_logic_still_used_when_nothing_selected(gen):
    """Регрессия: пользователь не выбрал актов — стандартный роутинг по template_type."""
    result = gen.generate(AUTO_TEMPLATE, _data())

    assert result["success"] and result["count"] >= 1
