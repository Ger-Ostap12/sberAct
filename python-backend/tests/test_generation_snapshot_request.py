"""Golden-фикстура воспроизводит контракт запроса из предпросмотра."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "golden_gen"))
from _gen_snapshot import generation_request


def test_request_forwards_every_preview_array():
    arrays = ("obligations", "heirs", "thirdParties", "debtors", "mortgageProperties", "coborrowers", "guarantors")
    source = {"fields": {"sourceDocumentType": "rtk_application", "caseNumber": "test"}}
    source.update({key: [{"value": key}] for key in arrays})
    result = generation_request(source)
    assert result["caseNumber"] == "test"
    assert result["sourceDocumentType"] == "rtk_application"
    for key in arrays:
        assert result[key] == source[key]


def test_mortgage_fixture_makes_explicit_choices_and_preserves_detected_kind():
    result = generation_request({
        "fields": {"sourceDocumentType": "mortgage_claim", "selectedActsIds": "acceptance_definition", "selectedActsData": "[]"},
        "mortgageKind": "ddu", "debtors": [{"name": "first"}, {"name": "second"}],
    })
    assert result["selectedMortgageKind"] == "ddu"
    assert result["claimResolution"] == "full"
    assert result["solidaryLiability"] == "true"
    assert "selectedActsIds" not in result and "selectedActsData" not in result


def test_single_debtor_mortgage_fixture_uses_non_solidary_scenario():
    result = generation_request({"documentType": "mortgage_claim", "debtors": [{"name": "one"}]})
    assert result["solidaryLiability"] == "false"
    assert result["selectedMortgageKind"] == "civil"


def test_bankruptcy_fixture_does_not_invent_mortgage_choices():
    result = generation_request({"documentType": "rtk_application"})
    assert "solidaryLiability" not in result
    assert "claimResolution" not in result
