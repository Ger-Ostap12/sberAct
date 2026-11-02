"""Границы и реквизиты объектов недвижимости в ипотечном заявлении."""

import re

OBJECT = r"(?:жил\w+\s+дом|квартир\w+|земельн\w+\s+участ\w+|нежил\w+\s+(?:помещени\w+|здани\w+)|помещени\w+|гараж\w*|машино-?мест\w*|здани\w+|строени\w+|комнат\w+)"
OBJECT_START = re.compile(r"^" + OBJECT + r"\b", re.I)
CADASTRAL = re.compile(r"кадастров\w+\s+номер[^\d\n]{0,40}?(\d{2}:\d{2}:\d{5,7}:\d+)", re.I)
ADDRESS = re.compile(r"(?:\bпо\s+адресу|\bадрес)\s*[:：]?\s*(.+?)(?:,?\s*кадастров\w+\s+номер|\.\s*Запис\w+\s+в\s+ЕГРН|$)", re.I | re.S)
AREA = re.compile(r"площад(?:ью|и|ь)\s*[:：–—-]?\s*(\d+(?:[.,]\d+)?(?:\s*(?:\+\s*/\s*-|±)\s*\d+(?:[.,]\d+)?)?)\s*(?:кв\.?\s*м|м[²2])", re.I)
BOUNDARY = re.compile(
    r"^(?:Для\s+обеспечения|В\s+силу|Согласно|Банк\s+исполнил|Право\s+собственности\s+на\s+вышеуказанн|"
    r"В\s+соответствии|Установить|Определить|Расторгнуть|Поскольку|Таким\s+образом|Следовательно|"
    r"Ответчик\w*|Истец\s|Кредитор\s|При\s+заключении|Нормой\s|ПРИЛОЖЕНИЯ|ПРОШУ)\b", re.I)
CONTINUATION = re.compile(
    r"^(?:общ\w+\s+площад|площад|располож|находящ|по\s+адресу|адрес|кадастров|Запис\w*\s+в\s+ЕГРН|"
    r"собственност|общ\w+\s+(?:совместн|долев)|ипотек|назначени|категори|разрешенн|разрешённ|"
    r"\d+\s*/\s*\d+\s*,?\s*№|№)", re.I)


def property_address(chunk):
    match = ADDRESS.search(chunk or "")
    return match.group(1).strip(" ,;.") if match else ""


def property_area(chunk):
    match = AREA.search(chunk or "")
    return re.sub(r"\s+", "", match.group(1)) if match else ""


def property_description(chunk):
    text = (chunk or "").strip(" -–—•\t")
    text = re.split(
        r",?\s*(?:расположен\w*|находящ\w*|по\s+адресу|\bадрес\s*[:：]|"
        r"кадастров\w+|Запис\w+\s+в\s+ЕГРН|[-–—]?\s*площадь\s*[:：])",
        text, maxsplit=1, flags=re.I)[0].strip(" ,;.-–—")
    return text[:1].upper() + text[1:] if text else ""


def physical_type(text):
    """Правовая форма залога не заменяет вид самого объекта."""
    for pattern, name in (
        (r"квартир\w*", "Квартира"), (r"жил\w+\s+дом", "Жилой дом"),
        (r"нежил\w+\s+помещени\w+", "Нежилое помещение"),
        (r"машино-?мест\w*", "Машино-место"), (r"гараж\w*", "Гараж"),
        (r"комнат\w*", "Комната"), (r"земельн\w+\s+участ\w*", "Земельный участок"),
        (r"помещени\w+", "Помещение"), (r"здани\w+", "Здание"),
    ):
        if re.search(r"\b" + pattern, text or "", re.I):
            return name
    return ""


ADDRESS_LINE = re.compile(
    r"^(?:\d{5,6}\b|Российск\w+\s+Федерац|[А-ЯЁа-яё -]+\s+(?:область|край|республика)\b|"
    r"г\.?\s|ул\.?\s|улиц|д\.?\s|дом\s+\d|кв\.?\s|стр\.?\s|корп\.?\s|р-н\b|с\.?\s|п\.?\s)", re.I)


def _records(region):
    records, current = [], ""
    region = re.sub(r"(?<=[.;])\s*(?=[-–—]?\s*" + OBJECT + r"\b)", "\n", region, flags=re.I)
    for raw in region.splitlines():
        line = raw.strip(" -–—•\t")
        if not line:
            continue
        if OBJECT_START.match(line):
            if current:
                records.append(current)
            current = line
        elif current:
            if BOUNDARY.match(line):
                break
            if CONTINUATION.match(line):
                current += " " + line
            elif property_address(current) and not CADASTRAL.search(current) and ADDRESS_LINE.match(line):
                current += " " + line
            else:
                break
        else:
            break
    if current:
        records.append(current)
    return [record for record in records if CADASTRAL.search(record) or property_address(record) or property_area(record)]


def collateral_chunks(text):
    """Одинаковый объект в описательной и просительной частях даёт одну карточку."""
    regions = [text[m.end():] for m in re.finditer(r"а\s+именно\s*:?\s*", text or "", re.I)]
    chunks = [chunk for region in regions for chunk in _records(region)]
    if not chunks:
        lines = (text or "").splitlines()
        for index, line in enumerate(lines):
            if OBJECT_START.match(line.strip(" -–—•\t")):
                chunks.extend(_records("\n".join(lines[index:])))
    result, positions = [], {}
    for chunk in chunks:
        cadastral = CADASTRAL.search(chunk)
        key = ("cad", cadastral.group(1)) if cadastral else (
            "object", property_description(chunk).casefold(), property_address(chunk).casefold(), property_area(chunk))
        if key not in positions:
            positions[key] = len(result)
            result.append(chunk)
        else:
            index = positions[key]
            def quality(value):
                return (bool(re.search(r"Запис\w*\s+в\s+ЕГРН", value, re.I)),
                        bool(property_area(value)), bool(property_address(value)))
            if quality(chunk) > quality(result[index]):
                result[index] = chunk
    return result
