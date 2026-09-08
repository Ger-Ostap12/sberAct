# -*- coding: utf-8 -*-
"""Выгрузка одного документа для вычитки эталона: что показывает ФОРМА + текст.

Нужен, чтобы ожидание в эталоне писалось по ТЕКСТУ ДОКУМЕНТА, а не по памяти
и не по тому, что уже выдаёт программа. Печатает обе стороны рядом.

Запуск:  dump_doc.py корпус 32
         dump_doc.py свежие 6
Нумерация: корпус — по `_snapshot.corpus_files()`, свежие — по отсортированному
списку .docx в папке «Заявления от 31.08» (так же нумеровался журнал).
"""
import glob
import logging
import os
import re
import sys

КОРЕНЬ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(КОРЕНЬ, "python-backend", "app"))
sys.path.insert(0, os.path.join(КОРЕНЬ, "python-backend", "tests", "golden"))
logging.disable(logging.CRITICAL)

СВЕЖИЕ_ПАПКА = r"C:\Диск D\Сбер\мусорные заявления\Заявления от 31.08"

ТИП_ЛИЦА = {"individual": "Физ.лицо", "legal": "Юр.лицо", "ip": "ИП", "kfh": "Глава КФХ"}
СТАТУС = {"liquidation": "Ликвидируемый", "absent": "Отсутствующий", "deceased": "Умерший"}

ВИДИМЫЕ = [
    ("Название суда", ("courtName", "mortgageCourtName002")),
    ("Номер дела", ("caseNumber",)),
    ("ФИО/наименование должника", ("debtorName", "applicantName")),
    ("Адрес должника", ("applicantAddress",)),
    ("ИНН должника", ("inn", "companyInn")),
    ("ОГРН должника", ("ogrn", "ogrnip")),
    ("Дата рождения", ("birthDate",)), ("Место рождения", ("birthPlace",)),
    ("Название кредитора", ("creditorName",)),
    ("Юр. адрес кредитора", ("creditorAddress",)),
    ("ОГРН кредитора", ("creditorOgrn",)), ("ИНН кредитора", ("creditorInn",)),
    ("ФИО управляющего", ("managerName",)), ("Адрес управляющего", ("managerAddress",)),
    ("СРО", ("sroName",)),
    ("Общая сумма долга", ("totalDebt",)),
    ("Осн. долг", ("principalDebt", "loanDebt")),
    ("Проценты", ("interest",)), ("Штрафные санкции", ("penalties",)),
    ("Неустойка", ("forfeit",)),
    ("Банкротная ГП", ("stateDuty",)), ("Ссудная ГП", ("loanStateDuty17",)),
    ("Кем взыскано", ("priorCourtName",)), ("Взысканная сумма", ("priorAmount",)),
    ("Дата решения", ("priorDecisionDate",)),
    ("Представитель истца", ("representativeName", "mortgageRepresentative22")),
    ("Ликвидатор", ("liquidatorName",)), ("Дата смерти", ("deathDate",)),
]

МАССИВЫ = [("ДОЛЖНИКИ", "debtors"), ("ПРЕДМЕТ ИПОТЕКИ", "mortgageProperties"),
           ("СОЗАЁМЩИКИ", "coborrowers"), ("ПОРУЧИТЕЛИ", "guarantors"),
           ("ТРЕТЬИ ЛИЦА", "thirdParties"), ("НАСЛЕДНИКИ", "heirs"),
           ("ОБЯЗАТЕЛЬСТВА", "obligations"), ("ЗАЛОГИ", "collaterals")]


def путь_по_имени(часть: str, имя: str):
    """Путь по ИМЕНИ файла — устойчив к добавлению документов в корпус.

    Сверка по номеру в списке ломается, как только корпус пополняется:
    индексы сдвигаются, и эталон начинает сверять чужие документы.
    """
    if часть == "корпус":
        import _snapshot as s
        for rel in s.corpus_files():
            if os.path.basename(rel) == имя:
                return os.path.join(s.CORPUS_DIR, rel.replace("/", os.sep))
        return None
    путь = os.path.join(СВЕЖИЕ_ПАПКА, имя)
    return путь if os.path.exists(путь) else None


def путь_документа(часть: str, n: int) -> str:
    if часть == "корпус":
        import _snapshot as s
        return os.path.join(s.CORPUS_DIR, s.corpus_files()[n].replace("/", os.sep))
    файлы = sorted(p for p in glob.glob(os.path.join(СВЕЖИЕ_ПАПКА, "*.docx"))
                   if not os.path.basename(p).startswith("~$"))
    return файлы[n]


def главное(часть: str, n: int) -> None:
    from document_analyzer import DocumentAnalyzer
    путь = путь_документа(часть, n)
    r = DocumentAnalyzer().analyze(путь)
    f = r.get("fields") or {}
    рек = r.get("recommendedActs") or {}

    print(f"### {часть}[{n}] {os.path.basename(путь)}")
    print("\n[КНОПКИ]")
    print(f"   тип лица     : {ТИП_ЛИЦА.get(r.get('entityType'), r.get('entityType'))}")
    print(f"   статус лица  : {СТАТУС.get(r.get('debtorStatusHint'), '— (обычный)')}")
    print(f"   выбор залога : {рек.get('collateralOption')}")
    print(f"   тип документа: {r.get('documentType')} / ипотека: {r.get('mortgageKind')}")
    for пред in ("documentTypeWarning", "debtorNameWarning", "entityTypeWarning",
                 "collateralWarning"):
        v = r.get(пред)
        if v:
            текст = v.get("message") if isinstance(v, dict) else v
            print(f"   ! {пред}: {str(текст)[:130]}")

    print("\n[ЧТО ПОКАЗЫВАЕТ ФОРМА]")
    for подпись, ключи in ВИДИМЫЕ:
        v = next((f.get(k) for k in ключи if f.get(k)), None)
        print(f"   {подпись:28s}: {v!r}")

    for имя, ключ in МАССИВЫ:
        зап = r.get(ключ) or []
        if зап:
            print(f"\n[{имя}] {len(зап)}")
            for i, e in enumerate(зап):
                ч = {k: v for k, v in (e or {}).items() if v not in (None, "", [], {})}
                print(f"   [{i}] {ч}")

    пр = r.get("fieldIssues") or []
    if пр:
        print(f"\n[ПОМЕТКИ/ПРЕТЕНЗИИ] {len(пр)}")
        for i in пр:
            print(f"   {i.get('field')}: {i.get('reason')} | {str(i.get('value'))[:70]!r}")

    текст = re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", r.get("rawText") or "")).strip()
    print(f"\n--- ТЕКСТ ДОКУМЕНТА ({len(текст)} знаков) ---")
    print(текст)


if __name__ == "__main__":
    главное(sys.argv[1], int(sys.argv[2]))
