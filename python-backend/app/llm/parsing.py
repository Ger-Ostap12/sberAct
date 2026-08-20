# -*- coding: utf-8 -*-
"""Разбор и обеззараживание ответов LLM. Вынесено из tests/llm_bench_run_fields.py
в app/, чтобы бенчмарк и прод-путь считали ОДНИМ кодом: иначе бенчмарк
перестаёт измерять то, что реально работает, и его цифра качества становится
декоративной.

Направление зависимости строго одно: бенчмарк импортирует отсюда, не наоборот.
"""
import json
import re

from requisites_validation import is_valid_inn

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def extract_json(text: str) -> dict | None:
    """Объект верхнего уровня. Markdown-обёртка (```json ... ```) не мешает —
    регулярка ищет {...} где угодно в тексте."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    blob = m.group(0)
    try:
        return json.loads(blob)
    except Exception:
        pass
    return repair_json(blob)


def extract_json_array(text: str) -> list | None:
    """Как extract_json, но верхний уровень — МАССИВ. Нужно для схемы предмета
    залога: на двух и более объектах модель игнорирует объектную обёртку
    {"properties": [...]} и возвращает голый массив (проверено эмпирически,
    df_mortgage_v5), поэтому схема сама просит массив — мы не боремся с этим
    текстом, а подстраиваемся под то, что модель делает естественно."""
    text = (text or "").strip()
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# Реальная причина 3/58 «невалидных JSON» на df_v3 (handoff §R.6) оказалась НЕ
# обрезкой по max_tokens (ответы приходили полные, с закрывающей скобкой), а:
# (а) вложенными неэкранированными кавычками внутри значения — модель
# игнорировала текстовый запрет, когда в самом документе название дано в
# несколько уровней кавычек («Союз «СРО «Гильдия…»»»); (б) невалидным
# escape-символом (`\я`, похоже на OCR-артефакт «а/я» → «а\я»). Обе чинятся
# построчным проходом: для строк вида `"key": "…значение…"` берём ВЕСЬ текст
# между первой и последней кавычками строки как значение и экранируем его.
_REPAIR_LINE_RE = re.compile(r'^(\s*"[a-zA-Z]+"\s*:\s*)"(.*)"(\s*,?\s*)$')


def repair_json(blob: str) -> dict | None:
    fixed_lines = []
    for line in blob.splitlines():
        m = _REPAIR_LINE_RE.match(line)
        if m:
            prefix, value, suffix = m.groups()
            value = value.replace("\\", "\\\\").replace('"', '\\"')
            line = f'{prefix}"{value}"{suffix}'
        fixed_lines.append(line)
    try:
        return json.loads("\n".join(fixed_lines))
    except Exception:
        return None


def check_leak(parsed: dict, markers_by_path: dict) -> int:
    """Обнуляет поля, дословно совпавшие с маркерами из few-shot — это сигнал,
    что модель скопировала пример вместо реального текста. Возвращает число
    обнулённых полей.

    Раздел может быть и словарём (court/representatives), и МАССИВОМ словарей
    (debtors/thirdParties) — проверяем каждый элемент: реальная утечка ИНН
    третьего лица нашлась именно в массиве, на прогоне df_mortgage_v2, как
    только ИНН впервые появился в few-shot."""
    if not isinstance(parsed, dict):
        return 0
    leaked = 0
    for path, markers in markers_by_path.items():
        role, field = path.split(".")
        section = parsed.get(role)
        if isinstance(section, dict):
            if section.get(field) in markers:
                section[field] = ""
                leaked += 1
        elif isinstance(section, list):
            for item in section:
                if isinstance(item, dict) and item.get(field) in markers:
                    item[field] = ""
                    leaked += 1
    return leaked


def sanitize_mortgage(parsed: dict) -> dict:
    """Детерминированный предохранитель ипотечной схемы: ИНН с неверной
    контрольной суммой и дата не в формате ДД.ММ.ГГГГ обнуляются. Принцип
    везде один — честное «не найдено» лучше уверенно неверного значения."""
    if not isinstance(parsed, dict):
        return parsed
    for item in parsed.get("debtors") or []:
        if not isinstance(item, dict):
            continue
        if item.get("inn") and not is_valid_inn(item["inn"]):
            item["inn"] = ""
        if item.get("birthDate") and not _DATE_RE.match(str(item["birthDate"]).strip()):
            item["birthDate"] = ""
    return parsed
