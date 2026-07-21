# -*- coding: utf-8 -*-
"""Блок «Сведения о взыскании» — ранее вынесенный судебный акт о взыскании
задолженности (до банкротства): суд, номер акта, сумма, дата, госпошлина.

Заявления формулируют это по-разному, поэтому якорь — не «по делу №…», а сам
акт о взыскании («вынесен судебный приказ № … о взыскании», «был выдан
исполнительный документ № … о взыскании»). Дело о банкротстве, которое стоит
рядом в тексте («Решением … по делу № А53-… признан банкротом»), отсекается
негативным фильтром.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

logger = logging.getLogger(__name__)


class PriorCollectionMixin:
    if TYPE_CHECKING:
        # Реализованы в inflection_mixin.InflectionMixin / amounts_mixin.AmountsMixin;
        # здесь только для Pyright (mixin-класс вызывает методы, которые появятся
        # в итоговом составном классе DocumentAnalyzer).
        def _inflect_word(self, word: str, target_case: str = "gent") -> str: ...
        def _fin_amount(self, s: Any) -> float: ...
        def _fin_fmt(self, v: float) -> str: ...

    _CASE_NUMBER_RE = re.compile(
        r"^[А-ЯA-Z]?\d{1,4}[А-ЯA-Z]?[-–]\d{1,15}/(?:19|20)\d{2}$"
    )

    _MAGISTRATE_CASE_NUMBER_RE = re.compile(
        r"^\d{1,2}[-–]\d{1,3}[-–]\d{1,6}/(?:19|20)\d{2}$"
    )

    # Виды судебных актов, которыми взыскивают долг до банкротства. Порядок важен:
    # длинные формулировки раньше коротких, иначе «решение» съест «заочное решение».
    _PRIOR_ACT_KINDS = (
        r"судебн\w*\s+приказ\w*",
        r"исполнительн\w*\s+документ\w*",
        r"исполнительн\w*\s+лист\w*",
        r"заочн\w*\s+решени\w*",
        r"решени\w*",
        r"определени\w*",
    )

    _ACT_ANCHOR_RE = re.compile(
        r"(?P<kind>" + "|".join(_PRIOR_ACT_KINDS) + r")"
        r"\s*(?:№|N|N°)\s*"
        r"(?P<num>[А-ЯЁA-Z0-9/–\-]{3,30})",
        re.IGNORECASE | re.VERBOSE,
    )

    # Запасной якорь — прежняя формулировка «…по делу №2-2523/2025 с должника
    # взыскана сумма…», где вид акта отдельно не назван.
    _CASE_ANCHOR_RE = re.compile(
        r"по\s+(?:\w+\s+)?делу\s*№\s*(?P<num>[А-ЯЁA-Z0-9/–\-]{3,30})",
        re.IGNORECASE,
    )

    # Требование взыскания рядом с актом — то, что отличает прежнее взыскание от
    # любого другого упоминания судебного акта.
    _RECOVERY_RE = re.compile(r"взыскани\w*|взыскан\w*", re.IGNORECASE)

    # Контекст ТЕКУЩЕГО дела о банкротстве: «признал банкротом», «о несостоятельности
    # (банкротстве)», «введена процедура реализации». Такой акт — не взыскание.
    _BANKRUPTCY_CTX_RE = re.compile(
        r"призна\w*\s+(?:\w+\s+){0,4}?банкрот\w*"
        r"|о\s+несостоятельност\w*"
        r"|несостоятельным\s*\(банкротом\)"
        r"|введен\w*\s+процедур\w*"
        r"|дел\w*\s+о\s+(?:несостоятельност\w*|банкротств\w*)",
        re.IGNORECASE,
    )

    _MAGISTRATE_COURT_RE = re.compile(
        r"""(?P<court>
            (?:Миров\w+\s+судь\w+\s+)?
            Судебн\w+\s+участ\w+\s*(?:№|N)\s*\d+
            (?:\s+(?:г\.|гор\.)?\s*[А-ЯЁ][А-Яа-яё\-]*|\s+[а-яё\-]+)*?
        )
        (?=\s+(?:\d{1,2}[.,]\d{1,2}[.,]\d{4}|был|была|было|вынес|выдан|о\s+взыскан|№|N\b|,|\.|$))
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # Обычный суд: «Ворошиловским районным судом г.Ростова-на-Дону», «Ленинский
    # районный суд Ростовской области».
    _GENERIC_COURT_RE = re.compile(
        r"""(?P<court>
            (?:[А-ЯЁ][а-яё]+(?:им|ым|ий|ый|ого|ой|ом|ому|ыми)\s+){1,3}
            суд(?:ом|а|е|у)?
            (?:\s+(?:г\.?\s*[А-ЯЁ][А-Яа-яё\-]+
                    |[А-ЯЁ][а-яё]+\s+(?:области|края|республики|округа|город\w*)))?
        )""",
        re.IGNORECASE | re.VERBOSE,
    )

    _COURT_CODE_RE = re.compile(r"^\d{2}[A-ZА-Я]{2}\d{2,5}$", re.IGNORECASE)
    _DATE_RE = re.compile(r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})")
    _MONEY = r"([0-9][0-9   ]*(?:[.,]\d{1,2})?)"

    def _is_valid_case_number(self, value: Optional[str]) -> bool:
        """True, если строка похожа на реальный номер судебного дела (любой суд)."""
        if not value:
            return False
        # Без учёта пробелов, регистра и Ё (буквы дел приводим к верхнему регистру)
        v = re.sub(r"\s+", "", str(value)).strip().upper().replace("Ё", "Е")
        return bool(self._CASE_NUMBER_RE.match(v))

    def _is_valid_prior_act_number(self, value: Optional[str]) -> bool:
        """Номер прежнего акта: обычное дело ЛИБО дело мирового участка (2-4-436/2025)."""
        if not value:
            return False
        if self._is_valid_case_number(value):
            return True
        v = re.sub(r"\s+", "", str(value)).strip().upper().replace("Ё", "Е")
        return bool(self._MAGISTRATE_CASE_NUMBER_RE.match(v))

    _COURT_TO_ACT_GAP = 90

    def _extract_prior_court_name(self, before: str) -> Optional[str]:
        """Название суда из текста ПЕРЕД актом. Слои по убыванию точности:
        мировой участок → обычный суд → ничего (в т.ч. когда указан лишь код участка).
        """
        for court_re, limit in ((self._MAGISTRATE_COURT_RE, 160), (self._GENERIC_COURT_RE, 120)):
            hits = [m for m in court_re.finditer(before)
                    if len(before) - m.end() <= self._COURT_TO_ACT_GAP]
            if hits:
                court = re.sub(r"\s+", " ", hits[-1].group("court")).strip(" ,.;")
                if 5 <= len(court) <= limit:
                    return self._normalize_court_to_nominative(court)
        return None
  
    _MAGISTRATE_PREFIX_RE = re.compile(
        r"^Миров\w+\s+судь\w+\s+(?=Судебн\w+\s+участ\w+)", re.IGNORECASE
    )
    _MAGISTRATE_SECTION_RE = re.compile(r"^Судебн\w+\s+участ\w+", re.IGNORECASE)
    _COURT_HEAD_RE = re.compile(r"^суд(?:ом|а|е|у)?$", re.IGNORECASE)

    def _normalize_court_to_nominative(self, court: str) -> str:
        """Название суда → именительный падеж.

        «Мировым судьей Судебный участок № 1 Обливского судебного района» →
        «Мировой судья судебного участка № 1 Обливского судебного района»;
        «Ворошиловским районным судом г.Ростова-на-Дону» →
        «Ворошиловский районный суд г.Ростова-на-Дону».

        Топоним и «№ N» не трогаем: склонять их нельзя («г. Ростова-на-Дону»
        так и остаётся при суде). При недоступной морфологии возвращаем исходную
        строку — пустое поле хуже, чем поле в падеже документа.
        """
        if not court:
            return court
        m = self._MAGISTRATE_PREFIX_RE.match(court)
        if m:
            tail = self._MAGISTRATE_SECTION_RE.sub("судебного участка", court[m.end():])
            return "Мировой судья " + tail
        if self._MAGISTRATE_SECTION_RE.match(court):
            # «Судебный участок № 4 …» — уже именительный, приводим лишь написание.
            return self._MAGISTRATE_SECTION_RE.sub("Судебный участок", court)
        # Обычный суд: склоняем только определения и само слово «суд», хвост с
        # локацией остаётся как есть.
        tokens = court.split(" ")
        head = next((i for i, t in enumerate(tokens) if self._COURT_HEAD_RE.match(t)), None)
        if head is None:
            return court
        return " ".join([self._inflect_word(t, "nomn") for t in tokens[:head + 1]] + tokens[head + 1:])

    def _extract_prior_court_decision(self, text: str) -> Dict[str, Any]:
        """Распознаёт РАНЕЕ вынесенный акт о взыскании (до банкротства).

        Примеры формулировок:
          • «Мировым судьей Судебный участок № 1 … 16.03.2026 вынесен судебный
            приказ № 2-253/2026 о взыскании … в размере 20 854,44 руб.»
          • «18.03.2025 по гражданскому делу № 2-4-436/2025 Судебный участок № 4 …
            был выдан исполнительный документ № 2-4-436/2025 о взыскании …»
          • «…23.06.2025 Ворошиловским районным судом … по делу №2-2523/2025 с
            должника взыскана сумма задолженности в размере …»

        Возвращает priorCourtName / priorCaseNumber / priorAmount /
        priorDecisionDate / priorStateDuty (что нашлось).
        """
        if not text:
            return {}
        flat = re.sub(r"[ \t]+", " ", text.replace(" ", " ").replace("\xa0", " "))
        # Слой 1 — акт назван прямо; слой 2 — прежняя форма «по делу №…».
        for anchor_re in (self._ACT_ANCHOR_RE, self._CASE_ANCHOR_RE):
            for m in anchor_re.finditer(flat):
                result = self._build_prior_result(flat, m)
                if result:
                    return result
        return {}

    def _build_prior_result(self, flat: str, m: "re.Match") -> Dict[str, Any]:
        """Собирает поля по конкретному кандидату-акту либо отвергает его ({})."""
        num_raw = m.group("num").strip(" .,;")
        if not self._is_valid_prior_act_number(num_raw):
            return {}
        after = flat[m.end(): m.end() + 90]
        before = flat[max(0, m.start() - 260): m.start()]
        if not (self._RECOVERY_RE.search(after) or self._RECOVERY_RE.search(before[-120:])):
            return {}
        # Тот же акт, но про банкротство («…по делу № А53-2848/2026 … признал
        # банкротом») — это текущее дело, а не прежнее взыскание.
        if self._BANKRUPTCY_CTX_RE.search(flat[m.start(): m.end() + 140]):
            return {}

        result: Dict[str, Any] = {"priorCaseNumber": num_raw}

        court = self._extract_prior_court_name(before)
        if court and not self._COURT_CODE_RE.match(court):
            result["priorCourtName"] = court

        # Сумма — первая «в размере <N>» после акта: это ОБЩАЯ взысканная сумма
        # (включая госпошлину), детализация «а именно …» идёт следом.
        win_after = flat[m.end(): m.end() + 320]
        am = re.search(r"в\s+размере\s*" + self._MONEY, win_after, re.IGNORECASE)
        if am:
            v = self._fin_amount(am.group(1))
            if v > 0:
                result["priorAmount"] = self._fin_fmt(v)

        # Госпошлина по ПРОШЛОМУ делу: «…пошлины в размере 2000.00 руб.» либо
        # обратный порядок «2000.00 руб. – госпошлина».
        duty_win = flat[m.end(): m.end() + 420]
        gm = re.search(
            r"(?:госпошлин\w*|государственн\w+\s+пошлин\w*)[^\d]{0,60}?" + self._MONEY,
            duty_win, re.IGNORECASE,
        )
        if not gm:
            gm = re.search(
                self._MONEY + r"\s*(?:\[\d+\])?\s*руб[^\d]{0,40}?(?:госпошлин\w*|государственн\w+\s+пошлин\w*)",
                duty_win, re.IGNORECASE,
            )
        if gm:
            gv = self._fin_amount(gm.group(1))
            if gv > 0:
                result["priorStateDuty"] = self._fin_fmt(gv)

        dates_before = self._DATE_RE.findall(before)
        if dates_before:
            result["priorDecisionDate"] = dates_before[-1].replace(",", ".")
        else:
            dm = re.search(r"^\s*(?:г\.)?\s*от\s+" + self._DATE_RE.pattern, after)
            if dm:
                result["priorDecisionDate"] = dm.group(1).replace(",", ".")
        return result
