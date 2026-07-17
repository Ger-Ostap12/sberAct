# -*- coding: utf-8 -*-
"""Устойчивость разбора к ФОРМЕ документа (мутационный тест).

Портит оформление заявления, не трогая смысл, и требует, чтобы извлечённые данные
не изменились. Отвечает на вопрос «как разбор сработает на заявлении банка,
которого нет в корпусе»: чужой банк отличается от нашего корпуса в первую очередь
типографикой, а не содержанием.

Подвыборка — 12 документов `Заявления/НОвая конвертация` (юридически корректный
набор, подтверждён Андреем), по одному на форму: ликвидация, умерший (нативный и
OCR), отсутствующий, коллекторы, ФНС, самобанкрот, инициирование ЮЛ и ИП, РТК,
ВТБ («метки стопкой»). Полный прогон корпуса — tests/measure_format_robustness.py.

KNOWN_BRITTLE — базовая линия на 2026-07-17. Тест зелёный, пока хрупкость не
выросла: новая пара «файл × мутация» роняет тест сразу. Починка фиксируется
обратным способом — известная пара, которая перестала ломаться, тоже роняет тест
с требованием убрать её из списка (иначе список гниёт и перестаёт что-либо значить).
"""
import logging
import os
import sys

import pytest

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))
sys.path.insert(0, _THIS)

from _mutations import MUTATIONS, diff_fields, significant_result  # noqa: E402
from _snapshot import CORPUS_DIR  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402

# По одному документу на форму заявления — расширять при появлении новой формы.
SAMPLE = [
    "НОвая конвертация/Заявл_Ликвидир_Оргтехника.docx",
    "НОвая конвертация/Умерший ким клим.docx",
    "НОвая конвертация/умерший сос.docx",
    "НОвая конвертация/отсутствующий заявление.docx",
    "НОвая конвертация/коллекторы пришли включаться.docx",
    "НОвая конвертация/ФНС/Заявление РТК Богачева.docx",
    "НОвая конвертация/Самобанкрот/Заявление РФЛ1.docx",
    "НОвая конвертация/Самобанкрот/Заявление на банкротство Медведев М.Ю.docx",
    "НОвая конвертация/Остальные/Заявление о признании должника банкротом  АО  КОНЦЕРН  САРМАТ   (ИНН- 6123010803).docx",
    "НОвая конвертация/Остальные/Заявление о признании должника банкротом ИП БАЗОВ ГЕОРГИЙ НИКОЛАЕВИЧ (ИНН- 616506698400).docx",
    "НОвая конвертация/Остальные/main_Заявление о включении в РТК - 2 л.docx",
    "НОвая конвертация/Остальные/Заявление о включении требований Банка ВТБ (ПАО) в реестр требований кредиторов должника 3л.docx",
]

# Пары «документ × мутация», ломающиеся СЕЙЧАС. Снимаются фазами нормализации:
# double_spaces/nbsp — фазой 2a, quotes — 2b, yo — 2c. В комментарии — поля,
# которые поехали, чтобы при снятии было видно, что именно чинится.
KNOWN_BRITTLE = {
    ("НОвая конвертация/Остальные/main_Заявление о включении в РТК - 2 л.docx", "double_spaces"),  # documentType, applicantAddress, birthPlace
    ("НОвая конвертация/Остальные/main_Заявление о включении в РТК - 2 л.docx", "yo"),  # creditorAddress
    ("НОвая конвертация/Остальные/Заявление о включении требований Банка ВТБ (ПАО) в реестр требований кредиторов должника 3л.docx", "double_spaces"),  # documentType, applicantName, creditorName
    ("НОвая конвертация/Остальные/Заявление о признании должника банкротом ИП БАЗОВ ГЕОРГИЙ НИКОЛАЕВИЧ (ИНН- 616506698400).docx", "double_spaces"),  # applicantName + падежи
    ("НОвая конвертация/Самобанкрот/Заявление РФЛ1.docx", "double_spaces"),  # loanDebt
    ("НОвая конвертация/Самобанкрот/Заявление на банкротство Медведев М.Ю.docx", "double_spaces"),  # documentType, loanDebt
    ("НОвая конвертация/Самобанкрот/Заявление на банкротство Медведев М.Ю.docx", "label_case"),  # loanDebt
    ("НОвая конвертация/Умерший ким клим.docx", "double_spaces"),  # documentType, applicantAddress, interest
    ("НОвая конвертация/ФНС/Заявление РТК Богачева.docx", "double_spaces"),  # documentType, applicantName + падежи
    ("НОвая конвертация/коллекторы пришли включаться.docx", "double_spaces"),  # documentType, applicantAddress, stateDuty
    ("НОвая конвертация/отсутствующий заявление.docx", "double_spaces"),  # applicantAddress, creditorInn, creditorOgrn, inn
    ("НОвая конвертация/отсутствующий заявление.docx", "quotes"),  # entityType, applicantName + падежи
    ("НОвая конвертация/умерший сос.docx", "nbsp"),  # collaterals
    ("НОвая конвертация/умерший сос.docx", "quotes"),  # creditorName
}

_analyzer = DocumentAnalyzer()
_base_cache = {}


def _baseline(rel: str):
    """Разбор исходника (кешируется: analyze ~0.7 с, а мутаций на файл шесть)."""
    if rel not in _base_cache:
        path = os.path.join(CORPUS_DIR, rel)
        if not os.path.exists(path):
            pytest.skip(f"нет файла корпуса: {rel}")
        text = _analyzer.extract_text(path)
        _base_cache[rel] = (text, significant_result(_analyzer.analyze_from_text(text, 2)))
    return _base_cache[rel]


@pytest.mark.parametrize("rel", SAMPLE, ids=lambda p: os.path.basename(p)[:40])
@pytest.mark.parametrize("mutation", [m[0] for m in MUTATIONS])
def test_result_survives_cosmetic_mutation(rel: str, mutation: str):
    """Косметика не должна менять извлечённые данные."""
    text, base = _baseline(rel)
    mutate = dict(MUTATIONS)[mutation]
    mutated_text = mutate(text)
    if mutated_text == text:
        pytest.skip("мутация неприменима к этому документу")

    known = (rel, mutation) in KNOWN_BRITTLE
    changed = diff_fields(base, significant_result(_analyzer.analyze_from_text(mutated_text, 2)))

    if known:
        assert changed, (
            f"Хрупкость «{mutation}» на {rel} ИСЧЕЗЛА — похоже, починено. "
            f"Убери пару из KNOWN_BRITTLE, иначе список перестанет отражать реальность."
        )
    else:
        assert not changed, (
            f"НОВАЯ хрупкость к формату: мутация «{mutation}» изменила поля {changed} "
            f"на {rel}. Документ не изменился по смыслу — значит, разбор зацепился "
            f"за типографику."
        )
