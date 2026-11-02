"""Общий разбор денежных чисел без смешения сумм с датами."""

import re
from decimal import Decimal, InvalidOperation

from patterns import MONEY_NUM

MONEY_TOKEN_RE = re.compile(MONEY_NUM)
_CURRENCY_RE = re.compile(r"(?:₽|руб(?:лей|ля|\.)?|р\.)", re.IGNORECASE)
_CURRENCY_AMOUNT_RE = re.compile(
    rf"(?P<amount>{MONEY_NUM})[ \t  ]*(?P<currency>₽(?:[ \t  ]*руб(?:лей|ля|\.)?)?)",
    re.IGNORECASE,
)
_MIXED_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(?P<amount>\d{1,3}(?:,\d{3})+\.\d{1,2}"
    r"|\d{1,3}(?:\.\d{3})+,\d{1,2})(?!\d|[.,]\d)"
    r"(?=[ \t  ]*(?:₽|руб\b|руб\.|рублей\b|рубля\b))"
)


def decimal_amount(value):
    """Проверяет всё число, сохраняя копейки и не склеивая соседние значения."""
    text = _CURRENCY_RE.sub("", str(value or "")).strip()
    if not MONEY_TOKEN_RE.fullmatch(text):
        return None
    text = re.sub(r"[ \t  ]", "", text)
    if "," in text and "." in text:
        grouping, fraction = (",", ".") if text.rfind(".") > text.rfind(",") else (".", ",")
        text = text.replace(grouping, "").replace(fraction, ".")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def canonical_money_text(text):
    """Канонизирует однозначный денежный формат только в рабочей копии текста."""

    def replace_mixed(match):
        value = decimal_amount(match.group("amount"))
        return format(value, ",.2f").replace(",", " ").replace(".", ",")

    text = _MIXED_AMOUNT_RE.sub(replace_mixed, text)
    # Двойная подпись валюты мешает привязке суммы к её метке.
    return _CURRENCY_AMOUNT_RE.sub(lambda m: m.group("amount") + " руб.", text)
