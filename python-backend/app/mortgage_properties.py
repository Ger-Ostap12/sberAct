"""Повторяемые блоки реквизитов каждого предмета ипотеки в Word."""

from copy import deepcopy
import re

from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


PROPERTY_MARKERS = {
    "1221": "description", "1222": "startingPrice", "1223": "appraisalReport",
    "1224": "value", "1225": "startingPrice", "1226": "cadastralNumber",
    "1227": "address", "1228": "npcStrategy", "1229": "egrnRecord",
    "1230": "egrnRecordDate", "1231": "dduContract", "1232": "dduDate",
    "1233": "area", "1234": "saleMethod",
}
BLOCK_NAME = re.compile(r"MortgageProperties(?:_\d+)?\Z")
MARKER = re.compile(r"\[(" + "|".join(PROPERTY_MARKERS) + r")\]")


def expand_property_blocks(doc, data, replace_span, format_amount, format_date):
    """Разворачивает явно размеченные блоки, не затрагивая старые шаблоны."""
    if str(data.get("sourceDocumentType") or "").lower() != "mortgage_claim":
        return 0
    body = doc.element.body
    starts = [node for node in body.iter(qn("w:bookmarkStart"))
              if BLOCK_NAME.fullmatch(node.get(qn("w:name"), ""))]
    if not starts:
        return 0
    fields = data.get("fields") or {}
    properties = data.get("mortgageProperties")
    if properties is None:
        properties = fields.get("mortgageProperties")
    if not isinstance(properties, list):
        raise ValueError("Для блока MortgageProperties нужен список предметов ипотеки")
    valid = []
    for index, item in enumerate(properties, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Предмет ипотеки {index}: ожидается объект с реквизитами")
        if any(str(item.get(key) or "").strip() for key in PROPERTY_MARKERS.values()):
            valid.append(item)
    if not valid:
        raise ValueError("Заполните хотя бы один предмет ипотеки для блока MortgageProperties")

    children = list(body)
    plans = []
    names = set()
    for start in starts:
        name = start.get(qn("w:name"))
        if name in names:
            raise ValueError(f"Повторяется имя закладки {name}")
        names.add(name)
        ends = [node for node in body.iter(qn("w:bookmarkEnd"))
                if node.get(qn("w:id")) == start.get(qn("w:id"))]
        if len(ends) != 1:
            raise ValueError(f"Не найдена единственная граница {name}")
        end = ends[0]
        first, last = start.getparent(), end.getparent()
        if first.getparent() is not body or last.getparent() is not body:
            raise ValueError(f"Закладка {name} должна охватывать целые абзацы основного текста")
        left, right = children.index(first), children.index(last)
        if left > right:
            raise ValueError(f"Перепутаны границы {name}")
        nodes = children[left:right + 1]
        if any(node.tag != qn("w:p") for node in nodes):
            raise ValueError(f"В блоке {name} допускаются только абзацы")
        for paragraph, boundary, before in ((first, start, True), (last, end, False)):
            content = list(paragraph.iter())
            at = content.index(boundary)
            outside = content[:at] if before else content[at + 1:]
            if any(node.tag == qn("w:t") and (node.text or "").strip() for node in outside):
                raise ValueError(f"Закладка {name} должна охватывать абзацы целиком")
        combined = [node for paragraph in nodes for node in paragraph.iter()]
        if combined.index(start) >= combined.index(end):
            raise ValueError(f"Перепутаны границы {name}")
        if any(node.tag in (qn("w:bookmarkStart"), qn("w:bookmarkEnd"))
               and node is not start and node is not end for node in combined):
            raise ValueError(f"В блоке {name} не должно быть вложенных закладок")
        if any(node.tag == qn("w:sectPr") for node in combined):
            raise ValueError(f"В блоке {name} не должно быть разрыва раздела")
        if not any("[1221]" in "".join(node.itertext()) for node in nodes):
            raise ValueError(f"В блоке {name} отсутствует описание объекта [1221]")
        plans.append((left, right, nodes))
    ordered = sorted(plans)
    if any(current[0] <= previous[1] for previous, current in zip(ordered, ordered[1:])):
        raise ValueError("Блоки MortgageProperties не должны пересекаться")

    replacements = []
    for left, right, nodes in ordered:
        rendered = []
        for item in valid:
            values = {}
            for marker, key in PROPERTY_MARKERS.items():
                value = str(item.get(key) if item.get(key) is not None else "").strip()
                if not value and marker == "1233":
                    area = re.search(
                        r"площад[ьи][^\d]{0,12}([\d]+[.,]?\d*\s*(?:кв\.?\s*м|м2|м²|\+/-\s*\d+\s*кв))",
                        str(item.get("description") or ""), re.IGNORECASE,
                    )
                    if area:
                        value = area.group(1).strip()
                if not value and marker == "1234":
                    value = "путем продажи с публичных торгов"
                if value and marker in ("1222", "1224", "1225"):
                    value = format_amount(value)
                elif value and marker in ("1230", "1232"):
                    value = format_date(value)
                values[marker] = value or "******"
            for source in nodes:
                clone = deepcopy(source)
                for key in (qn("w14:paraId"), qn("w14:textId")):
                    clone.attrib.pop(key, None)
                for node in list(clone.iter()):
                    if node.tag in (qn("w:bookmarkStart"), qn("w:bookmarkEnd")):
                        node.getparent().remove(node)
                paragraph = Paragraph(clone, doc._body)
                text = "".join(clone.itertext(qn("w:t")))
                for match in reversed(list(MARKER.finditer(text))):
                    replace_span(paragraph, match.start(), match.end(), values[match.group(1)])
                rendered.append(clone)
        replacements.append((left, right, rendered))
    for left, right, rendered in reversed(replacements):
        for node in children[left:right + 1]:
            body.remove(node)
        for offset, node in enumerate(rendered):
            body.insert(left + offset, node)
    return len(replacements)
