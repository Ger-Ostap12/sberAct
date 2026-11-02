"""Реквизиты каждого объекта в резолютивной части обычной ипотеки."""

from copy import deepcopy
import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from mortgage_awards import _money
from mortgage_object_parser import property_area
from mortgage_properties import PROPERTY_MARKERS


def render_civil_property_awards(doc, foreclosure, sale, data, format_date):
    """Массив объектов имеет приоритет над устаревшими плоскими полями."""
    fields = data.get("fields") or {}
    items = data.get("mortgageProperties")
    if items is None:
        items = fields.get("mortgageProperties")
    if items is None:
        return False
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Предметы ипотеки должны быть списком объектов с реквизитами")
    items = [item for item in items if any(str(item.get(key) or "").strip()
             for key in PROPERTY_MARKERS.values())]
    # Старые клиенты могли передавать лишь плоские поля.
    if not items:
        return False

    def value(item, key):
        raw = item.get(key)
        return str(raw).strip() if raw is not None and str(raw).strip() else "******"

    def money(item, key):
        raw = item.get(key)
        if raw is None or not str(raw).strip():
            return "******"
        return f"{_money(raw):,.2f}".replace(",", " ").replace(".", ",") + " руб."

    lines = ["Обратить взыскание на следующее заложенное имущество:"]
    for item in items:
        area = value(item, "area")
        if area == "******":
            area = property_area(value(item, "description")) or "******"
        else:
            area = re.sub(r"\s*(?:кв\.?\s*м\.?|м[²2])\s*$", "", area, flags=re.I).strip()
        date = value(item, "egrnRecordDate")
        date = format_date(date) if date != "******" else date
        method = value(item, "saleMethod")
        if method == "******":
            method = "продажа с публичных торгов"
        lines.extend([
            f"Объект недвижимости: {value(item, 'description')}.",
            f"Адрес: {value(item, 'address')}. Общая площадь (кв. м.): {area}.",
            f"Кадастровый номер: {value(item, 'cadastralNumber')}.",
            f"Запись в ЕГРН: № {value(item, 'egrnRecord')} от {date}.",
            f"Рыночная стоимость: {money(item, 'value')}.",
            f"Отчёт об оценке: {value(item, 'appraisalReport')}.",
            f"Начальная продажная стоимость: {money(item, 'startingPrice')}.",
            f"Стратегия определения начальной цены: {value(item, 'npcStrategy')}.",
            f"Определить способ реализации имущества: {method}.",
        ])

    parent = foreclosure.getparent()
    if parent is not doc.element.body or sale.getparent() is not parent:
        raise ValueError("Блоки обращения взыскания должны быть абзацами основного текста")
    for source in (foreclosure, sale):
        if source.pPr is not None and source.pPr.find(qn("w:sectPr")) is not None:
            raise ValueError("В блоке имущества не должно быть разрыва раздела")
    properties = next((run.rPr for run in foreclosure.iter(qn("w:r"))
                       if run.rPr is not None), None)
    for text in lines:
        node = OxmlElement("w:p")
        if foreclosure.pPr is not None:
            node.append(deepcopy(foreclosure.pPr))
        paragraph = Paragraph(node, doc._body)
        run = paragraph.add_run(text.replace("руб..", "руб."))
        if properties is not None:
            run._r.insert(0, deepcopy(properties))
        foreclosure.addprevious(node)
    parent.remove(foreclosure)
    parent.remove(sale)
    return True
