# -*- coding: utf-8 -*-
"""Блок «Сведения о взыскании» — ранее вынесенный судебный акт о взыскании
задолженности (до банкротства): суд, номер акта, сумма, дата, госпошлина.
"""

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PriorCollectionMixin:

    # Канонический формат номера судебного дела. Структура:
    #   [опц. буква][цифры региона/типа][опц. буква] - [цифры номера] / ГОД
    # Покрывает все суды:
    #   • Арбитражные:  А53-2222/2024  (А=арбитражный, 53=регион, 2222=№, 2024=год)
    #   • СОЮ (гражд./угол./админ.): 2-1234/2024, 1-123/2024, 5-67/2024
    #   • КАС / апелляция / кассация (буква ПОСЛЕ цифры): 2а-1234/2024, 33а-456/2024
    # Обязательны дефис перед номером и «/ГОД» (19xx/20xx) в конце — это отсекает
    # доверенности (ЮЗБ/415-Д, ЮЗБ-РД/158-Д), договоры и прочие №… без года.
    _CASE_NUMBER_RE = re.compile(
        r"^[А-ЯA-Z]?\d{1,4}[А-ЯA-Z]?[-–]\d{1,15}/(?:19|20)\d{2}$"
    )

    def _is_valid_case_number(self, value: Optional[str]) -> bool:
        """True, если строка похожа на реальный номер судебного дела (любой суд)."""
        if not value:
            return False
        # Без учёта пробелов, регистра и Ё (буквы дел приводим к верхнему регистру)
        v = re.sub(r"\s+", "", str(value)).strip().upper().replace("Ё", "Е")
        return bool(self._CASE_NUMBER_RE.match(v))

    def _extract_prior_court_decision(self, text: str) -> Dict[str, Any]:
        """Распознаёт РАНЕЕ вынесенное решение ДРУГОГО суда (взыскание до банкротства).

        Пример: «…23.06.2025 Ворошиловским районным судом г.Ростова-на-Дону по делу
        №2-2523/2025 с должника взыскана сумма задолженности в размере ___» либо
        «Вступившим в законную силу решением … по делу №… взыскана …». Возвращает
        priorCourtName / priorCaseNumber / priorAmount / priorDecisionDate (что нашлось).
        Формулировка может отличаться — опираемся на якорь «по делу №<дело>» рядом со
        словами вступивш/вынесен/взыскан/решени.
        """
        if not text:
            return {}
        flat = re.sub(r"[ \t]+", " ", text)
        for m in re.finditer(r"по\s+делу\s*№\s*([А-ЯЁA-Z0-9/–\-]{3,30})", flat, re.IGNORECASE):
            case_raw = m.group(1).strip(" .,;")
            if not self._is_valid_case_number(case_raw):
                continue
            win = flat[max(0, m.start() - 220): min(len(flat), m.end() + 220)]
            win_low = win.lower()
            # Контекст должен говорить о ранее вынесенном/вступившем решении/взыскании.
            if not re.search(r"взыскан|вступивш|вынесен\w*\s+решени|решени\w+\s+суд", win_low):
                continue
            result: Dict[str, Any] = {"priorCaseNumber": case_raw}
            # Суд — фраза «[прилагательные] суд[падеж] [город/область]» БЛИЖАЙШАЯ
            # перед «по делу» (после «суд» может идти локация: «судом г.Ростова-на-Дону»,
            # «суда Ростовской области»).
            before = flat[max(0, m.start() - 160): m.start()]
            court_matches = list(re.finditer(
                r"((?:[А-ЯЁ][а-яё]+(?:им|ым|ого|ой|ом|ому|ыми)\s+){1,3}"
                r"суд(?:ом|а|е|у)?"
                r"(?:\s+(?:г\.?\s*[А-ЯЁ][А-Яа-яё\-]+|[А-ЯЁ][а-яё]+\s+(?:области|края|республики|округа|город\w*)))?)",
                before, re.IGNORECASE,
            ))
            if court_matches:
                court = re.sub(r"\s+", " ", court_matches[-1].group(1)).strip(" ,.;")
                if 5 <= len(court) <= 120:
                    result["priorCourtName"] = court
            # Сумма — «взыскан… в размере <сумма>» (может отсутствовать: «___»).
            am = re.search(
                r"взыскан\w*[^\n]{0,140}?в\s+размере\s*([0-9][0-9   .,]*)",
                win, re.IGNORECASE,
            )
            if am:
                v = self._fin_amount(am.group(1))
                if v > 0:
                    result["priorAmount"] = self._fin_fmt(v)
            # Госпошлина по ПРОШЛОМУ делу (если упомянута рядом с прежним решением).
            _gmoney = r"([0-9][0-9   .,]*)"
            gm = re.search(r"(?:госпошлин\w*|государственн\w+\s+пошлин\w*)[^\d]{0,40}?" + _gmoney + r"\s*(?:\[\d+\])?\s*руб", win, re.IGNORECASE)
            if not gm:
                gm = re.search(_gmoney + r"\s*(?:\[\d+\])?\s*руб[^\d]{0,40}?(?:госпошлин\w*|государственн\w+\s+пошлин\w*)", win, re.IGNORECASE)
            if gm:
                gv = self._fin_amount(gm.group(1))
                if gv > 0:
                    result["priorStateDuty"] = self._fin_fmt(gv)
            # Дата решения: приоритет дате ПЕРЕД судом/«по делу» (это дата решения,
            # а не дата кредитного договора, идущая дальше по тексту).
            dm = re.search(r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})", before)
            if not dm:
                dm = re.search(r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})", win)
            if dm:
                result["priorDecisionDate"] = dm.group(1).replace(",", ".")
            return result
        return {}
