# -*- coding: utf-8 -*-
"""Короткое ЧИСЛО — валидное значение поля, а не мусор.

Общий цикл извлечения отсеивал захваты короче трёх символов: фильтр писался
против текстового сора («г.», «в»), но заодно убивал числа из одной-двух цифр.
Ставка неустойки «неустойку в размере 15%» давала захват «15» и выбрасывалась,
а в поле оставалось протухшее значение предыдущего — в итоге в ставку неустойки
[114]/[1003] уезжала ставка ПО КРЕДИТУ. На корпусе это видно точным совпадением:
creditPenaltyRate = creditInterestRate = 5,7 при реальной неустойке 15 %.

Тест держит обе стороны правила: число проходит, текстовый огрызок — нет.
"""
import pytest

from document_analyzer import DocumentAnalyzer


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


# Формулировка ипотечных заявлений Сбербанка: ставка неустойки — две цифры,
# ставка по кредиту рядом и отличается. Именно на такой паре баг и проявлялся.
PENALTY_TEXT = (
    "Между Банком и Заёмщиком заключён кредитный договор с процентной ставкой "
    "5,7 % годовых. За несвоевременное погашение кредита и/или уплату процентов "
    "за пользование кредитом Заёмщик уплачивают Кредитору неустойку в размере "
    "15% от суммы просроченного платежа за период просрочки."
)


def test_two_digit_penalty_rate_survives_length_filter(analyzer):
    fields = analyzer.extract_fields(PENALTY_TEXT, "mortgage_claim")
    assert fields.get("creditPenaltyRate") == "15"
    # Совпадение с ставкой по кредиту и было отпечатком бага: отброшенный
    # короткий захват оставлял в поле значение соседнего.
    assert fields.get("creditPenaltyRate") != fields.get("creditInterestRate")


def test_single_digit_term_survives(analyzer):
    """Одна цифра — тоже значение: «на срок 4 месяца»."""
    text = (
        "Открыть в отношении должника конкурсное производство по упрощённой "
        "процедуре ликвидируемого должника на срок 4 месяца."
    )
    fields = analyzer.extract_fields(text, "initiation_legal")
    assert fields.get("creditTermMonths") == "4"


def test_short_text_garbage_still_filtered(analyzer):
    """Послабление касается только чисел — текстовый огрызок по-прежнему отсеян."""
    text = "Наименование суда: г. Задолженность отсутствует."
    fields = analyzer.extract_fields(text, "initiation_legal")
    assert (fields.get("courtName") or "").strip() != "г."
