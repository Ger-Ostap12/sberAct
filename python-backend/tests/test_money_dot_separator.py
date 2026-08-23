# -*- coding: utf-8 -*-
"""Копейки через ТОЧКУ и разведение ссудной/банкротной госпошлины.

Треть корпуса (24 документа из 66) печатает суммы точкой — «53476.48».
Захват шёл классом [0-9\\s,]+, который обрывался на точке: в поле попадало
«53476», и в акт уезжала сумма, заниженная на копейки. Класс заменён на
MONEY_NUM — структурный шаблон, который копейки принимает через оба
разделителя, но не даёт зацепиться за хвост соседней даты и за номер статьи.

Второй сюжет — та же госпошлина. Названная СЛАГАЕМЫМ требования («в том числе
расходы по оплате госпошлины», «из которых: … - госпошлина»), она ссудная [17]:
входит в сумму требований. Банкротная [16] платится отдельно за подачу
заявления; по заявлению о включении в РТК её нет вовсе.
"""
import re

import pytest

from patterns import MONEY_NUM
from document_analyzer import DocumentAnalyzer


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


MONEY_RX = re.compile(r"(" + MONEY_NUM + r")\s*(?:руб|рублей|RUR|₽|р\.?)", re.IGNORECASE)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("53476.48 руб", "53476.48"),
        ("5 000,00 руб", "5 000,00"),
        ("2000.00 руб", "2000.00"),
        ("1 234 567.89 руб", "1 234 567.89"),
        ("68689.56 RUR", "68689.56"),
        ("сумма 0,00 руб", "0,00"),
        # Хвост даты не должен попадать в сумму: без левой границы отсюда
        # получалось «026 126 000,00».
        ("по состоянию на 01.01.2026 126 000,00 руб", "126 000,00"),
        ("на 29.05.2026 составляет 2789060,93 руб", "2789060,93"),
        # Дата и статья закона суммами не являются.
        ("21.03.2008 руб", None),
        ("ст. 213.24 Закона", None),
    ],
)
def test_money_capture(text, expected):
    match = MONEY_RX.search(text)
    assert (match.group(1) if match else None) == expected


# «в том числе»: сумма требования названа целиком, пошлина — её часть.
CLAIM_INCLUDING = (
    "Признать обоснованным и включить в третью очередь реестра требований "
    "кредиторов должника задолженность в сумме 47999.98 руб., в том числе "
    "расходы по оплате госпошлины в размере 2000.00 руб."
)

# «из которых»: требование разложено по строкам, пошлина — последняя.
CLAIM_BREAKDOWN = (
    "Включить денежное требование в размере 53476.48, из которых:\n"
    "48869.75 руб. - основной долг,\n"
    "2606.73 руб. - неустойки (штрафы, пени),\n"
    "2000.00 руб. - госпошлина.\n"
)


@pytest.mark.parametrize("text, total, duty", [
    (CLAIM_INCLUDING, "47 999,98", "2 000,00"),
    (CLAIM_BREAKDOWN, "53 476,48", "2 000,00"),
])
def test_claim_duty_is_loan_duty(analyzer, text, total, duty):
    fields = {"stateDuty": duty, "stateDuty16": duty}
    analyzer._apply_claim_state_duty(fields, text)
    assert fields["loanStateDuty17"] == duty
    assert fields["totalDebt"] == total
    # Тот же рубль не может стоять сразу в [16] и [17].
    assert "stateDuty" not in fields
    assert "stateDuty16" not in fields


def test_separate_bankruptcy_duty_survives(analyzer):
    """Настоящую банкротную пошлину правило не трогает.

    Если в [16] стоит СВОЯ сумма — это отдельная пошлина за подачу заявления,
    а не переписанная ссудная, и стирать её нельзя.
    """
    fields = {"stateDuty": "10 000,00", "stateDuty16": "10 000,00"}
    analyzer._apply_claim_state_duty(fields, CLAIM_INCLUDING)
    assert fields["loanStateDuty17"] == "2 000,00"
    assert fields["stateDuty16"] == "10 000,00"


def test_duty_not_bigger_than_claim(analyzer):
    """Пошлина больше самого требования — разбор промахнулся, поля не трогаем."""
    fields = {}
    analyzer._apply_claim_state_duty(
        fields,
        "задолженность в сумме 1000.00 руб., в том числе расходы по оплате "
        "госпошлины в размере 9000.00 руб.",
    )
    assert "loanStateDuty17" not in fields
    assert "totalDebt" not in fields
