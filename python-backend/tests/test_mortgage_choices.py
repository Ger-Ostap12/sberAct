"""Обязательные решения пользователя проверяются до создания ипотечного пакета."""

from copy import deepcopy
from itertools import product

import pytest

from document_generator import DocumentGenerator
from mortgage_choices import mortgage_choices_error
from test_mortgage_full_package import packet_data


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


@pytest.mark.parametrize("solidary,outcome", list(product(("true", "false"), ("full", "partial", "deny"))))
def test_explicit_choices_accept_false_and_all_outcomes(solidary, outcome):
    assert mortgage_choices_error({"solidaryLiability": solidary, "claimResolution": outcome}) is None
    assert mortgage_choices_error({"fields": {"solidaryLiability": solidary, "claimResolution": outcome}}) is None


@pytest.mark.parametrize("kind", ["civil", "ddu", "military"])
@pytest.mark.parametrize("key", ["solidaryLiability", "claimResolution"])
@pytest.mark.parametrize("value", ["", None, "unknown"])
def test_incomplete_packet_is_rejected_before_documents(generator, monkeypatch, kind, key, value):
    data = packet_data(kind)
    data[key] = value
    data["fields"][key] = value
    original = deepcopy(data)
    monkeypatch.setattr(generator, "_save_document_meta", lambda *args: pytest.fail("Не должно быть документов"))
    result = generator.generate("mortgage", data)
    assert not result["success"] and "Выберите" in result["error"]
    assert not result.get("documents")
    assert data == original


def test_empty_flat_choice_cannot_inherit_analyzer_value():
    assert mortgage_choices_error({"solidaryLiability": "", "fields": {"solidaryLiability": "true", "claimResolution": "full"}})


def test_unrelated_generations_do_not_require_mortgage_choices(generator, monkeypatch):
    monkeypatch.setattr(generator, "_resolve_standard_templates", lambda *args: ({}, "test"))
    result = generator.generate("bankruptcy", {})
    assert not result["success"]
    assert "Выберите" not in result.get("error", "")
