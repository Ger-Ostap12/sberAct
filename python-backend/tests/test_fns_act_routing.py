"""ФНС: актуальное дерево, очереди и запрет подмены включения инициированием."""
from pathlib import Path

import pytest
from document_generator import DocumentGenerator


@pytest.fixture(scope="module")
def ген():
    return DocumentGenerator()


def _включение(ген, entity="individual", variant="realization", **amounts):
    data = {
        "selectedApplicationKind": "rtk",
        "creditorName": "ФНС России",
        "final_rtk_inclusion_variant": variant,
        **amounts,
    }
    templates, missing = ген._map_selected_acts_to_templates(
        "final_rtk_inclusion", entity, "no_collateral", data,
    )
    assert not missing, (missing, data.get("_unresolvedReasons"))
    assert set(templates) == {"rtk_inclusion"}
    path = templates["rtk_inclusion"]["path"]
    assert path.is_file()
    assert path.relative_to(ген._templates_root()).parts[:2] == ("Банкротство", "Включение в РТК")
    assert "ФНС" in path.parts
    assert {"individual": "ФЛ", "ip": "ИП", "legal": "ЮЛ", "kfh": "КФХ"}[entity] in path.parts
    return path


@pytest.mark.parametrize("entity,variant", [
    ("individual", "realization"), ("individual", "restructuring"), ("legal", "observation"),
])
@pytest.mark.parametrize("amount,prefix", [("0", "3-я_"), ("1000", "2-я_")])
def test_акт_фнс_находится(ген, entity, variant, amount, prefix):
    path = _включение(ген, entity, variant, fnsQ2Total=amount)
    assert path.name.startswith(prefix), path
    assert ("наблюдение+конкурсное" if entity in ("legal", "kfh")
            else "реализация+реструктуризация") in path.name


@pytest.mark.parametrize("field", ["fnsQ2Total", "fnsQ2Arrears", "fnsQ2Penalties"])
def test_любая_сумма_второй_очереди_переключает_файл(ген, field):
    without = _включение(ген)
    with_second = _включение(ген, **{field: "10,01"})
    assert without != with_second
    assert without.name.startswith("3-я_")
    assert with_second.name.startswith("2-я_")


def test_нулевые_суммы_второй_очереди_файл_не_переключают(ген):
    path = _включение(ген, fnsQ2Total="0,00", fnsQ2Arrears="0", fnsQ2Penalties="")
    assert path.name.startswith("3-я_")


def test_инициирование_фнс_не_подменяется_включенкой(ген):
    data = {"selectedApplicationKind": "other", "creditorName": "ФНС России"}
    templates, missing = ген._map_selected_acts_to_templates(
        "final_restructuring", "individual", "no_collateral", data,
    )
    assert templates == {}
    assert missing == ["final_restructuring"]
    assert data.get("_unresolvedReasons", {}).get("final_restructuring")


@pytest.mark.parametrize("entity,procedure", [
    ("individual", "realization"), ("individual", "restructuring"),
    ("ip", "realization"), ("ip", "restructuring"),
    ("legal", "observation"), ("legal", "competition"),
    ("kfh", "observation"), ("kfh", "competition"),
])
@pytest.mark.parametrize("queue", ["2", "3", "2-3"])
def test_all_fns_entities_procedures_and_queues(ген, entity, procedure, queue):
    path = _включение(ген, entity, procedure,
                     fnsQ2Arrears="100" if queue in ("2", "2-3") else "0",
                     fnsQ3Arrears="200" if queue in ("3", "2-3") else "0")
    expected_queue = {"2": "2-я_", "3": "3-я_", "2-3": "2-я_3-я_"}[queue]
    assert path.name.startswith(expected_queue)
    suffix = "наблюдение+конкурсное" if entity in ("legal", "kfh") else "реализация+реструктуризация"
    assert suffix in path.name


def test_fns_picker_filters_wrong_procedures_and_keeps_ambiguity_guard(tmp_path):
    from bankruptcy_tree import pick_fns_inclusion
    old = tmp_path / "3-я_вкл_резолютивка_реализация+реструктуризация.docx"
    correct = tmp_path / "3-я_вкл_резолютивка_наблюдение+конкурсное.docx"
    old.touch()
    assert pick_fns_inclusion(tmp_path, "3", "observation").path is None
    correct.touch()
    assert pick_fns_inclusion(tmp_path, "3", "observation").path == correct
    assert pick_fns_inclusion(tmp_path, "3", "realization").path == old
    duplicate = tmp_path / "3-я_вкл_резолютивка_наблюдение+конкурсное (Копия).docx"
    duplicate.touch()
    result = pick_fns_inclusion(tmp_path, "3", "observation")
    assert result.path is None
    assert "неоднозначно" in result.reason


@pytest.mark.parametrize("entity,procedure", [
    ("legal", "realization"), ("kfh", "restructuring"),
    ("individual", "competition"), ("ip", "observation"),
])
def test_fns_final_rejects_procedure_of_another_entity(ген, entity, procedure):
    from bankruptcy_tree import resolve_final
    result = resolve_final(ген._templates_root(), entity=entity, role="rtk_short",
                           procedure=procedure, applicant="fns")
    assert result.path is None
    assert "несовместима" in result.reason


@pytest.mark.parametrize("entity,procedure", [
    ("legal", "observation"), ("legal", "competition"),
    ("kfh", "observation"), ("kfh", "competition"),
])
@pytest.mark.parametrize("queue", ["2", "3", "2-3"])
def test_new_fns_legal_kfh_full_generation(ген, monkeypatch, tmp_path, entity, procedure, queue):
    import re
    from docx import Document
    monkeypatch.setattr(ген, "generated_dir", tmp_path)
    data = {
        "selectedApplicationKind": "rtk", "selectedEntityType": entity,
        "selectedCollateralOption": "no_collateral", "sourceDocumentType": "rtk_application",
        "selectedActsIds": "final_rtk_inclusion", "final_rtk_inclusion_variant": procedure,
        "entityType": "legal" if entity == "legal" else "individual", "isKfh": entity == "kfh",
        "creditorName": "ФНС России в лице ИФНС России № 1",
        "applicantName": "ООО «Проверка»" if entity == "legal" else "Иванов Иван Иванович",
        "debtorName": "ООО «Проверка»" if entity == "legal" else "Иванов Иван Иванович",
        "kfhHeadName": "Иванов Иван Иванович", "birthDate": "01.01.1980",
        "ogrn": "1026100000002", "ogrnip": "304610000000001",
        "inn": "6100000001" if entity == "legal" else "610000000001",
        "applicantAddress": "г. Ростов-на-Дону, ул. Проверочная, д. 1",
        "judge": "Петров Пётр Петрович", "date": "10.11.2026", "caseNumber": "А53-1234/2026",
        "fnsQ2Arrears": "234,56" if queue in ("2", "2-3") else "0",
        "fnsQ3Arrears": "345,67" if queue in ("3", "2-3") else "0",
        "fnsQ3Forfeit": "0", "fnsQ3Penalties": "0", "obligations": [],
    }
    result = ген.generate("", data)
    assert result["success"], result
    assert result["count"] == 1
    doc = Document(result["documents"]["rtk_inclusion"]["file_path"])
    text = "\n".join(ген._paragraph_text(p) for p in list(ген._iter_all_paragraphs(doc)))
    assert not re.search(r"\[\d+(?:\.\d+)*\]", text)
    assert (data["ogrn"] if entity == "legal" else data["ogrnip"]) in text
    assert data["inn"] in text
    assert ("234,56" in text) == (queue in ("2", "2-3"))
    assert ("345,67" in text) == (queue in ("3", "2-3"))
