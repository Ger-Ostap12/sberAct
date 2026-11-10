"""Контекстное извлечение публикаций и дат подачи без заимствования соседних дат."""
import re
from datetime import date

DATE = r"(?<!\d)(\d{1,2}[.,]\d{1,2}[.,]\d{4})(?!\d)"
DATE_RE = re.compile(DATE)
EFRSB = r"(?:ЕФРСБ|Един\w*\s+федеральн\w*\s+реестр\w*\s+сведени\w*\s+о\s+банкротств\w*|(?:bankrot\.)?fedresurs\.ru)"
KOMMERSANT = r"[«\"]?Коммерсант[ъь]?[»\"]?"
SOURCE = re.compile(f"{EFRSB}|{KOMMERSANT}", re.I)
STOP = re.compile(
    r"\.(?=\s+[^\d\s])|;|\n\s*\n|"
    r"\b(?:закон\w*|договор\w*|согласно|стать\w*|поступ\w*|направлен\w*|Мой\s+Арбитр)\b|в\s+соответствии|№\s*127-ФЗ", re.I,
)
NUMBER = r"([0-9]+(?:[-/][0-9A-Za-zА-Яа-яЁё]+)*)"


def normalized_date(value):
    try:
        day, month, year = map(int, value.replace(",", ".").split("."))
        date(year, month, day)
        return f"{day:02d}.{month:02d}.{year:04d}"
    except (ValueError, TypeError):
        return None


def _number(context, explicit_only=False):
    dates = [m.span(1) for m in DATE_RE.finditer(context)]
    patterns = [rf"№\s*{NUMBER}"]
    if not explicit_only:
        patterns += [rf"(?:номер\s+сообщени\w*|сообщени\w*)[:\s]+{NUMBER}"]
    for pattern in patterns:
        for match in re.finditer(pattern, context, re.I):
            if any(start < match.end(1) and end > match.start(1) for start, end in dates):
                continue
            return match.group(1)
    return None


def _publication(text, source):
    anchor = re.compile(source, re.I)
    for match in anchor.finditer(text):
        right = text[match.end():match.end() + 240]
        stops = [m.start() for pattern in (SOURCE, STOP) if (m := pattern.search(right))]
        if stops:
            right = right[:min(stops)]
        number = _number(right)
        dates = [normalized_date(m.group(1)) for m in DATE_RE.finditer(right)]
        value = next((d for d in dates if d), None)
        left = text[max(0, match.start() - 160):match.start()]
        # Только явно привязанные к публикации данные перед названием источника.
        before = re.search(rf"{DATE}\s+(?:в\s+газет[аые]\s*|на\s+сайте\s*)?$", left, re.I)
        if not value and before:
            value = normalized_date(before.group(1))
        if not number:
            prefix = re.search(r"сообщени\w*\s*№(?:(?!закон|договор|Коммерсант)[^;\n]){1,150}$", left, re.I)
            if prefix:
                number = _number(prefix.group(), explicit_only=True)
                if not value:
                    prefix_dates = [normalized_date(m.group(1)) for m in DATE_RE.finditer(prefix.group())]
                    value = next((d for d in reversed(prefix_dates) if d), None)
        if number or value:
            return number, value
    return None, None


def publication_fields(text):
    result = {}
    for source, number_field, date_field in (
        (EFRSB, "messageNumber", "efirsbPublicationDate"),
        (KOMMERSANT, "kommersantNumber", "kommersantDate"),
    ):
        number, value = _publication(text, source)
        if number:
            result[number_field] = number
        if value:
            result[date_field] = value
    # Размеченные поля имеют однозначную принадлежность источнику.
    for marker, field in (("9", "messageNumber"), ("11", "efirsbPublicationDate"),
                          ("67", "kommersantNumber"), ("68", "kommersantDate")):
        pattern = rf"\[{marker}\]\s*" + (NUMBER if field.endswith("Number") else DATE)
        match = re.search(pattern, text)
        if match:
            value = match.group(1) if field.endswith("Number") else normalized_date(match.group(1))
            if value:
                result[field] = value
    return result


def apply_publication_fields(fields, text):
    found = publication_fields(text)
    if SOURCE.search(text):
        # Общие старые паттерны «сообщение №» не должны превращать
        # публикацию Коммерсанта в сообщение ЕФРСБ (и наоборот).
        for key in ("messageNumber", "efirsbPublicationDate", "kommersantNumber", "kommersantDate"):
            fields.pop(key, None)
    fields.update(found)
    # Старый общий алиас не должен восстанавливать чужую дату в [11].
    if SOURCE.search(text) and "efirsbPublicationDate" not in found:
        fields.pop("publicationDate", None)


def _filing_actor_matches(fields, text, match):
    creditor = str(fields.get("creditorName") or "").strip()
    if not creditor:
        return True
    # После даты подачи может стоять иной кредитор из истории дела:
    # «...Мой Арбитр» АО «Банк Б» обратилось...». Его дату не заимствуем.
    tail = text[match.end():match.end() + 180]
    actor = re.match(
        r'[»"]?\s*((?:ПАО|АО|ООО|ОАО|ЗАО)\s*(?:«[^»]+»|"[^"]+"|[А-ЯЁ][А-Яа-яЁё-]*(?:\s+[Бб]анк)?))\s+обратил\w*',
        tail, re.I,
    )
    if not actor:
        return True
    def key(value):
        value = re.sub(r"^(?:ПАО|АО|ООО|ОАО|ЗАО)\s*", "", value, flags=re.I)
        return re.sub(r"[^а-яёa-z0-9]", "", value.lower())
    return key(actor.group(1)) == key(creditor)


def apply_filing_dates(fields, text):
    patterns = {
        "applicationReceiptDate23": [
            rf"\[23\]\s*{DATE}",
            rf"дата\s+поступления\s+заявления\s+в\s+суд[:\s]*{DATE}",
            rf"заявлени\w*\s+поступил\w*\s+в\s+(?:арбитражный\s+)?суд\s+{DATE}",
            rf"(?:в\s+(?:арбитражный\s+)?суд\s+)?{DATE}\s*(?:г\.?\s*)?поступил\w*\s+(?:\([^;\n]{{0,150}}\)\s*)?заявлени\w*",
            rf"поступил\w*\s+в\s+суд\s+{DATE}",
            rf"{DATE}\s*(?:г\.?\s*)?\(\s*согласно\s+штампу",
            rf"согласно\s+штампу[^.;\n]{{0,60}}?{DATE}",
        ],
        "courtSubmissionDate24": [
            rf"\[24\]\s*{DATE}",
            rf"(?:посредством|через)\s+(?:систем\w*|сервис\w*)?\s*[«\"]?Мой\s+Арбитр[»\"]?\s*{DATE}",
            rf"дата\s+направления\s+в\s+суд[:\s]*{DATE}",
            rf"заявлени\w*\s+(?:направлен\w*|подан\w*)\s+в\s+(?:арбитражный\s+)?суд\s+{DATE}",
            rf"{DATE}\s*(?:г\.?\s*)?(?:заявлени\w*\s+)?(?:направлен\w*|подан\w*)[^.;\n]{{0,80}}?Мой\s+Арбитр",
            rf"{DATE}\s*(?:г\.?\s*)?(?:в?\s*\d{{1,2}}[:.]\d{{2}}(?::\d{{2}})?\s*)?(?:посредством|через)\s+(?:сервис\w*\s+(?:электронной\s+подачи\s+документов\s+)?)?[«\"]?Мой\s+Арбитр",
            rf"(?:через|посредством)\s+(?:сервис\w*\s+(?:электронной\s+подачи\s+документов\s+)?)?[«\"]?Мой\s+Арбитр[»\"]?\s+(?:заявлени\w*\s+)?(?:подан\w*|направлен\w*)?[:\s]*{DATE}",
        ],
    }
    labels = {
        "applicationReceiptDate23": r"\[23\]|поступлени\w*\s+заявлени\w*|заявлени\w*\s+поступил\w*|штамп\w*",
        "courtSubmissionDate24": r"\[24\]|направлени\w*\s+в\s+суд|заявлени\w*\s+(?:направлен\w*|подан\w*)|Мой\s+Арбитр",
    }
    for field, expressions in patterns.items():
        if re.search(labels[field], text, re.I):
            fields.pop(field, None)
        for expression in expressions:
            for match in re.finditer(expression, text, re.I):
                value = normalized_date(match.group(1))
                if value and _filing_actor_matches(fields, text, match):
                    fields[field] = value
                    break
            if field in fields:
                break
