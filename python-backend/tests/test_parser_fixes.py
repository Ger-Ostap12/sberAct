# -*- coding: utf-8 -*-
"""Регрессия по багам парсинга/рендера из сессии 22.07.2026:
  • П.2 — «Описание предмета залога» [1221] тянуло весь последующий текст (обязательства),
    когда якорь «выпиской из ЕГРН» не совпадал (в заявлении «выписками»/«По состоянию…»);
  • П.1 — остаточные пустые слоты «от № ,» при < 6 обязательств.
"""
import re

import pytest

from patterns import build_patterns
from document_analyzer import DocumentAnalyzer


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


# --- П.2 (реальный кейс ООО «СПН ТРАК»): fallback-извлечение предмета залога не должно
#     утекать в нарратив обязательств/просительную часть на ОДНОАБЗАЦНОМ OCR-тексте ---

SPN_TRAK_ONE_PARAGRAPH = (
    "В качестве обеспечения своевременного и полного возврата кредита, ЗАЕМЩИК обес-печивает "
    "предоставление: Имущественное обеспечение в соответствии с договором залога. "
    "Договор залога №6142027489 24 2З01 Залогодатель ООО «СПН ТРАК». – движимое имущество: "
    "VIN: X89984710L2GS7002, полуприцеп, Модель: 98472 0000010; Год: 2020. "
    "Банк свои обязательства по Договору выполнил в полном объеме, перечислив на банковский счет "
    "Заемщика сумму кредита. По состоянию на 20.05.2026 образовалась задолженность в размере "
    "34740651,37 рублей. Обязательство №2 Между ПАО Сбербанк и ООО «СПН ТРАК» заключен договор. "
    "ПРОСИТ СУД: 1. Признать ООО \"СПН ТРАК\" несостоятельным (банкротом)."
)


def test_collateral_block_stops_before_obligation_narrative(analyzer):
    blk = analyzer._extract_mortgage_collateral_block(SPN_TRAK_ONE_PARAGRAPH)
    assert blk, "предмет залога должен извлечься"
    # Захвачен предмет залога…
    assert "движимое имущество" in blk and "VIN" in blk
    # …но НЕ утекли обязательства/долг/просительная часть (баг «огромного текста»).
    assert "Банк свои обязательства" not in blk
    assert "задолженность" not in blk
    assert "Обязательство №" not in blk
    assert "ПРОСИТ" not in blk


def test_collateral_block_real_estate_stops_at_egrn(analyzer):
    text = (
        "что подтверждается договором залога №5555 от 28.10.2022 : квартира, общей площадью "
        "31.4 кв.м., кадастровый номер: 61:48:0030519:436, расположенный по адресу: г. Волгодонск, "
        "ул. Ленина, д. 22, кв. 5. Наличие заложенного имущества подтверждается выписками из ЕГРН. "
        "По состоянию на 19.05.2025 задолженность по кредитному договору №1271058 составляет 1 249 122,53 руб."
    )
    blk = analyzer._extract_mortgage_collateral_block(text)
    assert blk and "квартира" in blk
    assert "задолженность" not in blk and "выписк" not in blk.lower()


# --- П.2: захват предмета залога не должен утекать в обязательства ---

def _collateral_patterns():
    all_patterns = build_patterns()
    for group in all_patterns.values():
        for item in group:
            if item.get("name") == "mortgageCollateralDescription1221":
                return item["patterns"]
    raise AssertionError("паттерн mortgageCollateralDescription1221 не найден")


COLLATERAL_TEXT = (
    "что подтверждается договором залога №5555 от 28.10.2022 : "
    "квартира, общей площадью 31.4 кв.м., кадастровый номер: 61:48:0030519:436, "
    "расположенный по адресу: Ростовская область, г. Волгодонск, ул. Ленина, д. 22, кв. 5. "
    "Наличие заложенного имущества подтверждается выписками из ЕГРН (документы прилагаются). "
    "По состоянию на 19.05.2025 задолженность по кредитному договору №1271058 от 28.10.2022 "
    "составляет 1 249 122,53 руб. Обязательство №2 11.06.2025 ПАО Сбербанк заключили кредитный договор."
)


def test_collateral_description_stops_before_obligations():
    for pat in _collateral_patterns():
        m = re.search(pat, COLLATERAL_TEXT, re.IGNORECASE)
        if not m:
            continue
        captured = m.group(1)
        # Захвачено описание предмета…
        assert "квартира" in captured
        assert "61:48:0030519:436" in captured
        # …но НЕ утекли обязательства/задолженности после «выписками из ЕГРН».
        assert "задолженность" not in captured
        assert "кредитному договору" not in captured
        assert "Обязательство" not in captured
        return
    raise AssertionError("ни один паттерн предмета залога не сматчился на пример")


# --- П.1: зачистка остаточных «от № ,» повторяет логику из obligations_render_mixin ---

def _cleanup_empty_slots(text: str) -> str:
    """Тот же набор regex-замен, что применяется к параграфам документа в
    obligations_render_mixin.replace_obligations_data (ungated-блок для < N обязательств).
    Чистит ОБА порядка: "от № " (обычные акты) и "№ от" (ипотека: [100]=№, [110]=дата)."""
    for _ in range(8):
        text = re.sub(r"(?:,\s*)?от\s+№\s*(?=,|\.|\)|;|$)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(?:,\s*)?№\s*от\s*(?=,|\.|\)|;|$)", "", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r",\s*\.", ".", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def test_empty_obligation_slots_removed_date_first():
    # Обычные акты: "от № " (дата-первым)
    got = _cleanup_empty_slots("по договорам от № , от № , от № , от №.")
    assert "от №" not in got


def test_empty_obligation_slots_removed_number_first_mortgage():
    # Ипотека: "№ от" (номер-первым) — хвост из скриншота пользователя
    got = _cleanup_empty_slots("по кредитному договору №  от , №  от , №  от .")
    assert "№  от" not in got and "№ от" not in got


def test_real_obligation_numbers_preserved():
    src = "по договору от № 1271058, от № 3064405."
    got = _cleanup_empty_slots(src)
    assert "1271058" in got and "3064405" in got
    # Реальные номера не должны исчезнуть.
    assert got.count("№") == 2


def test_real_mortgage_numbers_preserved():
    # Ипотечный порядок "№ 123 от 12.03.2024" — не трогаем реальные значения.
    src = "по договору № 1271058 от 28.10.2022, № 3064405 от 20.12.2023."
    got = _cleanup_empty_slots(src)
    assert "1271058" in got and "28.10.2022" in got
    assert got.count("№") == 2
