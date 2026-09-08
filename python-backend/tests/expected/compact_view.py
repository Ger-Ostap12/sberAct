# -*- coding: utf-8 -*-
"""Сжатая сверка: значения программы рядом со строками текста по якорям.

Зачем не полный текст: документ — 15-20 тысяч знаков, десять таких в один
проход не помещаются. Здесь по каждой группе полей печатаются только те строки
документа, где факт мог бы быть написан. Объём падает вчетверо, а решение
«совпало / не совпало» принимается по тем же словам, что читал бы юрист.

⚠️ Якорь — не доказательство. Если строки по якорю нет, это НЕ значит, что
факта в документе нет: смотри полный текст через dump_doc.py. Инструмент
сужает поиск, а не заменяет чтение.

Запуск:  compact_view.py корпус 0 10
"""
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_doc import ТИП_ЛИЦА, путь_документа  # noqa: E402

КОРЕНЬ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(КОРЕНЬ, "python-backend", "app"))
logging.disable(logging.CRITICAL)

ПОЛЯ = [
    ("суд", ("courtName",)), ("дело", ("caseNumber",)),
    ("должник", ("debtorName", "applicantName")), ("адрес долж.", ("applicantAddress",)),
    ("ИНН долж.", ("inn", "companyInn")), ("ОГРН долж.", ("ogrn", "ogrnip")),
    ("род./место", ("birthDate",)), ("кредитор", ("creditorName",)),
    ("юр.адрес кред.", ("creditorAddress",)), ("ОГРН/ИНН кред.", ("creditorOgrn",)),
    ("ИНН кред.", ("creditorInn",)),
    ("управляющий", ("managerName",)), ("адрес упр.", ("managerAddress",)),
    ("СРО", ("sroName",)), ("представитель", ("representativeName", "mortgageRepresentative22")),
    ("ИТОГО", ("totalDebt",)), ("осн.долг", ("principalDebt", "loanDebt")),
    ("проценты", ("interest",)), ("неустойка", ("forfeit",)),
    ("штрафы", ("penalties",)), ("ГП банкр.", ("stateDuty",)), ("ГП ссудн.", ("loanStateDuty17",)),
]

# группа -> регулярка по строке текста; берём не больше N строк на группу
# группа -> (регулярка, предел строк, максимальная длина строки).
# Ограничение длины важнее, чем кажется: юридическая «вода» — это длинные
# абзацы, а факты живут в коротких строках-метках. Без отсечки по длине
# сжатый вид тонет в цитатах ГК и становится не короче полного текста.
ЯКОРЯ = [
    ("СУД/ДЕЛО", r"(Арбитражн\w+ суд|Дело\s*[:№]|№\s*А\d{2}-|судебн\w+ участ)", 3, 150),
    ("СТОРОНЫ", r"^(Должник|Ответчик|Заявитель|Истец|Кредитор|Взыскател|Третьи|Финансовый)", 8, 180),
    ("РЕКВИЗИТЫ", r"(ИНН|ОГРН|ОГРНИП|СНИЛС)\s*[:\s]\s*\d", 6, 170),
    ("АДРЕСА", r"(^Адрес|Место нахождения|Место жительства|адрес регистрац|проживающ)", 7, 170),
    ("УПРАВЛЯЮЩИЙ/СРО", r"(финансов\w+ управляющ|арбитражн\w+ управляющ|СРО|саморегулируем)", 4, 200),
    ("ДОГОВОРЫ", r"договор\w*\s*(№|N)\s*\S", 5, 160),
    ("СУММЫ", r"(в размере|составляет|итого|в том числе|основно\w+ долг|процент\w+ –|пошлин)", 9, 260),
    ("ПРЕДСТАВИТЕЛЬ", r"^(Представитель|.{0,30}по доверенности)", 3, 120),
    ("ЗАЛОГ", r"(предмет залога|заложенн\w+ имуществ|кадастров\w+ номер|обеспеченн\w+ залогом)", 4, 200),
    ("ПУБЛИКАЦИИ", r"(ЕФРСБ|Коммерсант|сообщени\w+ №)", 3, 190),
]


def главное(часть: str, от: int, до: int) -> None:
    from document_analyzer import DocumentAnalyzer
    анализатор = DocumentAnalyzer()
    for n in range(от, до):
        try:
            путь = путь_документа(часть, n)
        except IndexError:
            return
        r = анализатор.analyze(путь)
        f = r.get("fields") or {}
        рек = r.get("recommendedActs") or {}
        print("=" * 100)
        print(f"### {часть}[{n}] {os.path.basename(путь)}")
        кнопки = (f"тип={ТИП_ЛИЦА.get(r.get('entityType'), r.get('entityType'))} "
                  f"статус={r.get('debtorStatusHint') or 'обычный'} "
                  f"залог={рек.get('collateralOption')} док={r.get('documentType')}")
        print(f"[КНОПКИ] {кнопки}")
        значения = []
        for подпись, ключи in ПОЛЯ:
            v = next((f.get(k) for k in ключи if f.get(k)), None)
            значения.append(f"{подпись}={v!r}")
        print("[ПРОГРАММА] " + "; ".join(значения))
        for имя, ключ in (("должники", "debtors"), ("третьи", "thirdParties"),
                          ("обязательства", "obligations"), ("залоги", "collaterals"),
                          ("ипотека", "mortgageProperties"), ("поручители", "guarantors")):
            зап = r.get(ключ) or []
            if зап:
                кратко = [{k: v for k, v in (e or {}).items()
                           if v not in (None, "", [], {}) and not k.endswith("Value")
                           and k != "id"} for e in зап]
                print(f"[{имя} {len(зап)}] {кратко}")
        пр = r.get("fieldIssues") or []
        if пр:
            print("[ПОМЕТКИ] " + "; ".join(f"{i.get('field')}:{str(i.get('reason'))[:44]}"
                                           for i in пр))
        текст = re.sub(r"[ \t]{2,}", " ", r.get("rawText") or "")
        строки = [s.strip() for s in текст.split("\n") if s.strip()]
        for имя, я, предел, макс in ЯКОРЯ:
            нашли, видели = [], set()
            for s in строки:
                if len(нашли) >= предел:
                    break
                if len(s) <= макс and re.search(я, s, re.I) and s[:60] not in видели:
                    видели.add(s[:60])
                    нашли.append(s)
            if нашли:
                print(f"  <{имя}> " + " | ".join(нашли))
        print()


if __name__ == "__main__":
    главное(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
