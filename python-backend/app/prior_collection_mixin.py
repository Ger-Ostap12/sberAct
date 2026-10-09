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
        # «#» входит в набор: исполнительные документы приходят СОСТАВНЫМ
        # идентификатором ГАС «Правосудие» — «61MS0046#2-95/2025#1», и без
        # решётки якорь обрывался на «61MS0046», номер не проходил проверку
        # формы, и весь блок взыскания молчал (свежие-13).
        r"(?P<num>[А-ЯЁA-Z0-9/#–\-]{3,40})",
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
    # «Принудительное исполнение» — такой же признак взыскания, как само слово
    # «взыскание»: свежие-13 пишет «выдан исполнительный документ № … на сумму
    # 17738,40 рублей, который был предъявлен … на принудительное исполнение»,
    # ни одного «взыскан» рядом, и блок молчал целиком.
    # ⚠️ «Возбуждено исполнительное производство» в признак НЕ входит, хотя
    # напрашивалось: эта фраза стоит в перечне своих долгов у САМОБАНКРОТА
    # («…на основании судебного приказа № 2-1178/2024 …, было возбуждено
    # исполнительное производство»), где блока прежнего взыскания нет. Поймано
    # существующим тестом test_prior_collection.test_no_false_positive и golden.
    _RECOVERY_RE = re.compile(
        r"взыскани\w*|взыскан\w*"
        r"|принудительн\w*\s*исполнени\w*",
        re.IGNORECASE,
    )

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
        """Номер прежнего акта: обычное дело, дело мирового участка (2-4-436/2025)
        ЛИБО составной идентификатор, ВНУТРИ которого есть номер дела."""
        if not value:
            return False
        if self._is_valid_case_number(value):
            return True
        v = re.sub(r"\s+", "", str(value)).strip().upper().replace("Ё", "Е")
        if self._MAGISTRATE_CASE_NUMBER_RE.match(v):
            return True
        # Составной номер исполнительного документа: «61MS0046#2-95/2025#1».
        # Годен, если хотя бы одна часть — настоящий номер дела.
        return "#" in v and any(
            self._CASE_NUMBER_RE.match(часть) or self._MAGISTRATE_CASE_NUMBER_RE.match(часть)
            for часть in v.split("#")
        )

    _COURT_TO_ACT_GAP = 90

    def _extract_prior_court_name(self, before: str) -> Optional[str]:
        """Название суда из текста ПЕРЕД актом. Слои по убыванию точности:
        мировой участок обычный суд ничего (в т.ч. когда указан лишь код участка).
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
        """Название суда именительный падеж.

        «Мировым судьей Судебный участок № 1 Обливского судебного района»
        «Мировой судья судебного участка № 1 Обливского судебного района»;
        «Ворошиловским районным судом г.Ростова-на-Дону»
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
                    self._дополнить_судом(flat, result)
                    return result
        # Слой 3 — акт БЕЗ НОМЕРА: «<СУД> вынес судебный акт о взыскании …».
        return self._акт_без_номера(flat)

    # Акт, у которого документ не называет номера вовсе: «МС СУ №6 Советского
    # района г.Ростова-на-Дону вынес судебный акт о взыскании задолженности
    # с … в размере 96525 руб.» (свежие-30). Оба якоря выше требуют «№ номер»,
    # поэтому такой акт не опознавался ничем. Якорь здесь — ГЛАГОЛ «вынес»
    # вместе с «о взыскании»: без обоих слов слой не срабатывает.
    # ⚠️ Точка внутри названия разрешена: «г.Ростова-на-Дону» — часть имени
    # суда, а не конец фразы. Отличаем по пробелу после точки: «. » кончает
    # фразу, «г.Р» — нет. Без этого класс [^.] обрывался на «г.» и якорь молчал.
    _НЕ_КОНЕЦ_ФРАЗЫ = r"(?:[^.;!?\n]|\.(?!\s))"
    _БЕЗ_НОМЕРА_RE = re.compile(
        r"(?:^|[.;!?*)\]]\s*|\n)\s*\*?\s*"
        r"(?P<court>(?:МС|СУ|Миров\w+|Судебн\w+|[А-ЯЁ][А-Яа-яё\-]+)"
        + _НЕ_КОНЕЦ_ФРАЗЫ + r"{3,110}?)"
        r"\s+вынес(?:ло|ла|ли)?\s+"
        r"(?:судебн\w+\s+акт\w*|решени\w*|определени\w*|приказ\w*|постановлени\w*)"
        + _НЕ_КОНЕЦ_ФРАЗЫ + r"{0,60}?о\s+взыскани",
        re.IGNORECASE,
    )
    # Группа обязана выглядеть судом: сокращение «МС»/«СУ» в начале либо слово
    # «суд»/«участок» внутри. Иначе глагол «вынес» утащит в поле любую прозу.
    _ПОХОЖЕ_НА_СУД = re.compile(r"^(?:МС|СУ)\b|суд|участ", re.IGNORECASE)

    def _акт_без_номера(self, flat: str) -> Dict[str, Any]:
        """Суд и сумма из фразы «<СУД> вынес <акт> о взыскании … в размере N»."""
        for m in self._БЕЗ_НОМЕРА_RE.finditer(flat):
            суд = re.sub(r"\s+", " ", m.group("court")).strip(" ,.;*")
            if not (5 <= len(суд) <= 110) or not self._ПОХОЖЕ_НА_СУД.search(суд):
                continue
            if self._BANKRUPTCY_CTX_RE.search(flat[m.start(): m.end() + 140]):
                continue
            result: Dict[str, Any] = {"priorCourtName": суд}
            am = re.search(r"(?:в\s+размере|на\s+сумму)\s*" + self._MONEY,
                           flat[m.end(): m.end() + 200], re.IGNORECASE)
            if am:
                v = self._fin_amount(am.group(1))
                if v > 0:
                    result["priorAmount"] = self._fin_fmt(v)
            # Дату здесь НЕ берём: документ даты акта не называет, а ближайшая
            # слева — дата договора УСТУПКИ («№ О/66-91/2018 от 31.10.2018 г.»),
            # и она встала бы в поле «Дата решения». Пустое поле честнее чужой
            # даты; этот блок дат юрист заполняет сам (решение Андрея 08.09).
            logger.info("Прежний акт без номера: суд=%s сумма=%s",
                        суд, result.get("priorAmount"))
            return result
        return {}

    def _дополнить_судом(self, flat: str, result: Dict[str, Any]) -> None:
        """Берёт название суда у ДРУГОГО упоминания того же акта.

        Один и тот же акт заявление называет дважды, и суд стоит рядом только
        с одним упоминанием. Свежие-16: «Судебным актом мирового судьи судебного
        участка № 8 … по Делу № 8-2-3913/2025 удовлетворены требования …» —
        и через 230 знаков «изготовлен и выдан судебный приказ № 8-2-3913/2025».
        Якорь вида акта срабатывал на ВТОРОМ упоминании, где суд уже вне окна
        (90 знаков), возвращал результат без суда и запирал слой «по делу №»,
        который суд находит. Номер акта у обоих упоминаний ОДИН — значит это
        один акт, и дополнить его судом законно.
        """
        if result.get("priorCourtName"):
            return
        номер = re.sub(r"\s+", "", result.get("priorCaseNumber") or "").upper()
        if not номер:
            return
        for anchor_re in (self._CASE_ANCHOR_RE, self._ACT_ANCHOR_RE):
            for m in anchor_re.finditer(flat):
                if re.sub(r"\s+", "", m.group("num").strip(" .,;")).upper() != номер:
                    continue
                суд = self._extract_prior_court_name(flat[max(0, m.start() - 260): m.start()])
                if суд and not self._COURT_CODE_RE.match(суд):
                    result["priorCourtName"] = суд
                    logger.info("Суд прежнего акта взят у другого упоминания: %s", суд)
                    return

    def _build_prior_result(self, flat: str, m: "re.Match") -> Dict[str, Any]:
        """Собирает поля по конкретному кандидату-акту либо отвергает его ({})."""
        num_raw = m.group("num").strip(" .,;")
        if not self._is_valid_prior_act_number(num_raw):
            return {}
        # Окно признака взыскания — 180 знаков: у свежие-13 между номером акта
        # и «принудительное исполнение» стоит ещё «на сумму … рублей, который
        # впоследствии был предъявлен в службу судебных приставов», и прежних
        # 90 знаков не хватало.
        after = flat[m.end(): m.end() + 180]
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
        # «на сумму» наравне с «в размере»: исполнительные документы пишут
        # «выдан исполнительный документ № … НА СУММУ 17738,40 рублей»
        # (свежие-13), и взысканная сумма не доставалась вовсе.
        am = re.search(r"(?:в\s+размере|на\s+сумму)\s*" + self._MONEY,
                       win_after, re.IGNORECASE)
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
