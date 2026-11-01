"""Выбор удовлетворённых требований обычной ипотеки/ДДУ и присуждённые суммы."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

AWARD_FLAGS = {
    "termination": "mortgageAwardTermination",
    "debt": "mortgageAwardDebt",
    "foreclosure": "mortgageAwardForeclosure",
}
AWARD_AMOUNTS = {
    "principal": ("mortgageAwardPrincipal", ("principalDebt", "loanDebt", "principalDebt13")),
    "interest": ("mortgageAwardInterest", ("interest", "interest14")),
    "penalty": ("mortgageAwardPenalty", ("forfeit", "forfeit15", "penalties")),
    "duty": ("mortgageAwardDuty", ("stateDuty16", "stateDuty")),
}
DDU_AWARD_AMOUNTS = {
    **AWARD_AMOUNTS,
    "penalty_interest": ("mortgageAwardInterestPenalty", ("forfeitInterest1362",)),
}
AWARD_BOOKMARKS = (
    "MortgageTermination", "MortgageDebt", "MortgageForeclosure", "MortgageSale",
)
DEBT_CLAUSE = re.compile(r"задолженность\b.*?,\s*а также\s*(?=расходы)", re.DOTALL)
DUTY_CLAUSE = re.compile(r",\s*а также расходы по оплате государственной пошлины в размере\s*\[16\]")
TOTAL_CLAUSE = re.compile(r",\s*всего\s*\[1360\]\.?")

DDU_DEBT_CLAUSE = re.compile(r"задолженность\b.*?,\s*(?=судебные расходы)", re.DOTALL)
DDU_DUTY_CLAUSE = re.compile(r",\s*судебные расходы по оплате государственной пошлины в размере\s*\[16\]")
DDU_TOTAL_CLAUSE = re.compile(r",\s*а всего взыскать:\s*\[1360\]\.?")
DDU_PENALTY_CLAUSES = {
    "15": re.compile(r",?\s*неустойка за просроченный основной долг\s*[-–—]\s*\[15\](?:\s*руб\.?)?", re.IGNORECASE),
    "1362": re.compile(r",?\s*неустойка за просроченные проценты\s*[-–—]\s*\[1362\](?:\s*руб\.?)?", re.IGNORECASE),
}


def _money(value: Any) -> Decimal:
    text = re.sub(r"\s+", "", str(value if value is not None else "")).lower()
    text = re.sub(r"(?:руб(?:\.|ля|лей)?|₽)$", "", text)
    if not text:
        return Decimal("0")
    if not re.fullmatch(r"\d+(?:[.,]\d{1,2})?", text):
        raise ValueError("Присуждённые суммы должны быть неотрицательными числами с точностью до копеек")
    try:
        amount = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Некорректная присуждённая сумма") from exc
    if not amount.is_finite():
        raise ValueError("Некорректная присуждённая сумма")
    return amount


def partial_awards(data: Dict[str, Any], kind: str = "civil") -> Optional[Dict[str, Any]]:
    """Отсутствие новых полей сохраняет поведение прежних клиентов."""
    if str(data.get("claimResolution") or "").strip().lower() != "partial":
        return None
    fields = data.get("fields") or {}
    amount_fields = DDU_AWARD_AMOUNTS if kind == "ddu" else AWARD_AMOUNTS
    keys = (*AWARD_FLAGS.values(), *(value[0] for value in amount_fields.values()))
    if not any(key in data or key in fields for key in keys):
        return None

    def pick(key, default=None):
        return data[key] if key in data else fields.get(key, default)

    result: Dict[str, Any] = {}
    for name, key in AWARD_FLAGS.items():
        value = str(pick(key, "true")).strip().lower()
        if value not in ("true", "false"):
            raise ValueError(f"Некорректный выбор требования: {key}")
        result[name] = value == "true"
    if not any(result.values()):
        raise ValueError("Все требования отклонены. Выберите «Отказать в удовлетворении»")
    for name, (key, aliases) in amount_fields.items():
        if name != "duty" and not result["debt"]:
            result[name] = Decimal("0")
            continue
        fallback = next((pick(alias) for alias in aliases
                         if pick(alias) is not None and str(pick(alias)).strip()), "")
        result[name] = _money(pick(key, fallback))
    result["debt_total"] = sum(
        (result[name] for name in amount_fields if name != "duty"), Decimal("0")
    )
    if result["debt"] and result["debt_total"] <= 0:
        raise ValueError("Укажите положительную сумму задолженности или снимите отметку «Взыскать задолженность»")
    return result


def prepare_partial_awards(data: Dict[str, Any], kind: str = "civil") -> Dict[str, Any]:
    """Присуждённые суммы применяются к решению, суммы заявления не меняются."""
    selected = partial_awards(data, kind)
    if selected is None:
        return data
    result = dict(data)
    amount_fields = DDU_AWARD_AMOUNTS if kind == "ddu" else AWARD_AMOUNTS
    for name, (_, aliases) in amount_fields.items():
        for alias in aliases:
            result[alias] = format(selected[name], ".2f")
    result["totalDebt"] = format(selected["debt_total"], ".2f")
    result["totalWithDuty1360"] = format(selected["debt_total"] + selected["duty"], ".2f")
    return result
