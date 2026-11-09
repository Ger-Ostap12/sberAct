"""Стандартный РТК использует то же дерево, что и явный выбор актов."""
from copy import deepcopy

import pytest

from document_generator import DocumentGenerator


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


@pytest.mark.parametrize("entity", ["individual", "ip", "legal", "kfh"])
@pytest.mark.parametrize("collateral", ["no_collateral", "collateral"])
@pytest.mark.parametrize("creditor", ["creditor", "fns"])
def test_default_rtk_packet_matches_explicit_selection(generator, entity, collateral, creditor):
    data = {
        "selectedApplicationKind": "rtk",
        "selectedEntityType": entity,
        "selectedCollateralOption": collateral,
        "creditorName": "\u0424\u041d\u0421 \u0420\u043e\u0441\u0441\u0438\u0438" if creditor == "fns" else "creditor",
        "fnsQ3Total": "1000",
    }
    variant = "observation" if entity in ("legal", "kfh") else "realization"
    expected_data = {**data, "final_rtk_inclusion_variant": variant}
    expected, missing = generator._map_selected_acts_to_templates(
        "final_rtk_inclusion,acceptance_definition", entity, collateral, expected_data,
    )
    actual, procedure = generator._resolve_standard_templates(
        deepcopy(data), "rtk_single_obligation", "", "", entity == "kfh",
    )
    assert actual == expected
    assert actual, missing
    assert all(item["path"].is_file() for item in actual.values())
    assert all("\u0411\u0430\u043d\u043a\u0440\u043e\u0442\u0441\u0442\u0432\u043e" in item["path"].parts for item in actual.values())
    assert procedure == variant


@pytest.mark.parametrize("template", ["restructuring", "physical_restructuring_collateral", "ip_enforcement_restructuring"])
def test_explicit_restructuring_keeps_its_procedure(generator, template):
    data = {"selectedApplicationKind": "rtk", "creditorName": "creditor"}
    templates, procedure = generator._rtk_default_templates(data, template, "")
    assert templates
    assert procedure == "restructuring"


def test_legacy_default_without_application_kind_also_uses_tree(generator):
    templates, procedure = generator._resolve_standard_templates({}, "", "", "", False)
    assert templates
    assert procedure == "realization"
    assert all(item["path"].is_file() for item in templates.values())


@pytest.mark.parametrize("status", ["liquidation", "absent"])
def test_default_procedure_respects_selected_legal_status(generator, status):
    data = {"selectedApplicationKind": "rtk", "selectedEntityType": "legal",
            "selectedDebtorStatus": status}
    templates, procedure = generator._rtk_default_templates(data, "rtk_single_obligation", "")
    assert procedure == "competition"
    assert templates
    assert all(item["path"].is_file() for item in templates.values())


def test_explicit_rtk_variant_is_kept_without_selected_act_ids(generator):
    data = {"selectedApplicationKind": "rtk", "selectedEntityType": "individual",
            "final_rtk_inclusion_variant": "restructuring"}
    templates, procedure = generator._rtk_default_templates(data, "rtk_single_obligation", "")
    assert procedure == "restructuring"
    assert templates
