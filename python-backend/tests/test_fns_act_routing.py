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
    assert ("ЮЛ" if entity == "legal" else "ФЛ") in path.parts
    return path


@pytest.mark.parametrize("entity,variant", [
    ("individual", "realization"), ("individual", "restructuring"), ("legal", "observation"),
])
@pytest.mark.parametrize("amount,prefix", [("0", "3-я_"), ("1000", "2-я_")])
def test_акт_фнс_находится(ген, entity, variant, amount, prefix):
    path = _включение(ген, entity, variant, fnsQ2Total=amount)
    assert path.name.startswith(prefix), path
    assert "реализация+реструктуризация" in path.name


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
