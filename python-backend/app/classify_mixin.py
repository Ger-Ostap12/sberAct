import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Детектор САМОБАНКРОТСТВА. Паттерны через \s* между словами: в PDF-конвертации
# слова бывают склеены без пробелов («ЗАЯВЛЕНИЕФИЗИЧЕСКОГОЛИЦА…»).


# Вето: явные приметы КРЕДИТОРСКОГО заявления — при любом из них не самобанкрот.
_SELF_BK_VETO_RES = (

    re.compile(r"заявител\w*\s*\(\s*кредитор", re.IGNORECASE),
    # «взыскать … в пользу <банка>» — требование кредитора, у должника такого нет.
    re.compile(r"взыскать[\s\S]{0,120}?в\s*пользу", re.IGNORECASE),
    # «признать обоснованным заявление <банка>» — кредиторская просительная.
    re.compile(r"признать\s*обоснованн\w+\s*заявлени", re.IGNORECASE),
)


_SELF_BK_FNS_HEAD_RE = re.compile(r"НАЛОГОВ\w+\s+СЛУЖБ", re.IGNORECASE)
_SELF_BK_FNS_TITLE_RE = re.compile(r"ЗАЯВЛЕНИ\w+\s+УПОЛНОМОЧЕНН\w+\s+ОРГАН", re.IGNORECASE)


_SELF_BK_PRAYER_RE = re.compile(r"ПРО(?:ШУ|СИМ|СИТ)\s*(?:СУД\w*)?\s*:", re.IGNORECASE)

_SELF_BK_RTK_RE = re.compile(
    r"включить[\s\S]{0,160}?(?:реестр\w*\s*требован|(?:перв|втор|треть)\w*\s*очеред)",
    re.IGNORECASE,
)

# Сильные сигналы самобанкротства (достаточно одного, после вето и контр-сигнала).
_SELF_BK_FIRST_PERSON_RE = re.compile(
    # «Признать меня, гр. …», «о признании меня банкротом», «ввести в отношении
    # меня процедуру», «признать себя несостоятельным»
    r"призна(?:ть|нии)\s*[:\s]*\s*(?:меня|себя)|в\s*отношении\s*меня",
    re.IGNORECASE,
)
_SELF_BK_TITLE_RE = re.compile(
    r"""заявлени\w*\s*
        (?:должника|физическ\w*\s*лица|гражданина)?\s*   # чьё заявление (опционально)
        о\s*(?:признании\s*(?:его|меня)\s*несостоятельн  # «о признании его/меня несостоятельным»

            |признании\s*гражданина\s*(?:Российской\s*Федерации\s*)?(?:несостоятельн|банкрот)
            |реструктуризации\s*задолженност)            # «о реструктуризации задолженности»
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Подпись/реквизит «Заявитель (Должник):» — явное совпадение ролей заявителя и
# должника (зеркало кредиторской метки «Заявитель (Кредитор):»).
_SELF_BK_APPLICANT_IS_DEBTOR_RE = re.compile(
    r"заявител\w*\s*\(\s*должник", re.IGNORECASE
)

# Метки сторон в шапке (для сигнала «должник идёт первым, кредиторы — списком»).
_SELF_BK_HEAD_DEBTOR_RE = re.compile(r"(?:должник|фио)\s*:", re.IGNORECASE)
_SELF_BK_HEAD_CREDITOR_RE = re.compile(r"кредитор\w*\s*\d*\s*:", re.IGNORECASE)
_SELF_BK_HEAD_APPLICANT_RE = re.compile(r"заявител", re.IGNORECASE)


_SELF_BK_SUPPORT_RES = (
    ("ст. 213.4", re.compile(r"213\s*\.\s*4", re.IGNORECASE)),
    ("опись имущества", re.compile(r"опис\w*\s*имущества", re.IGNORECASE)),
    (
        "список кредиторов и должников",
        re.compile(r"список\s*кредиторов\s*и\s*(?:должников|дебиторов)", re.IGNORECASE),
    ),
)



_INIT_DECLARE_RE = re.compile(
    # «Признать <должника> несостоятельным (банкротом)». Инфинитив/1л мн.ч., НЕ
    # «признан» (прошедшее — ссылка на уже введённое банкротство в теле РТК).
    r"призна(?:ть|ем)\b[\s\S]{0,90}?(?:несостоятельн\w*|банкрот\w*)",
    re.IGNORECASE,
)

_INIT_PROCEDURE_RE = re.compile(
    r"ввести\b[\s\S]{0,60}?процедур", re.IGNORECASE
)
# Правовая форма ДОЛЖНИКА в просьбе «Признать <должника> …» (не реквизиты кредитора).
_INIT_LEGAL_FORM_RE = re.compile(r"\b(?:ООО|ОАО|ОДО|ПАО|ЗАО|АО|НАО)\b|обществ\w*\s+с\s+ограниченн", re.IGNORECASE)
_INIT_IP_FORM_RE = re.compile(r"\bИП\b|индивидуальн\w+\s+предпринимател", re.IGNORECASE)


_NOT_PROCEDURE_TYPES = frozenset({
    "mortgage_claim", "ip_collection", "ip_collection_collateral",
    "ip_collection_collateral_auto", "legal_collection",
    "legal_collection_collateral", "legal_collection_collateral_auto",
    "unknown",
})


def _procedure_family_from_document_type(document_type):
    """Семейство процедуры банкротства, которое ПОДРАЗУМЕВАЕТ regex-тип
    документа — «rtk» (только включение в реестр) или «initiation» (признание
    банкротом + введение процедуры). None — document_type вне этой оси
    (исковое о взыскании/ипотеке/unknown), сравнивать не с чем.

    Используется ТОЛЬКО как ожидание для сверки со вторым (семантическим)
    способом определения типа — само значение document_type не трогает.
    """
    if document_type == "rtk_application":
        return "rtk"
    if document_type in _NOT_PROCEDURE_TYPES:
        return None
    return "initiation"

_ENTITY_TYPE_BY_DOCUMENT_TYPE = {
    "ip_collection": "ip",
    "ip_collection_collateral": "ip",
    "ip_collection_collateral_auto": "ip",
    "ip_enforcement_statement": "ip",
    "ip_enforcement_statement_collateral": "ip",
    "ip_enforcement_realization": "ip",
    "ip_enforcement_realization_collateral": "ip",
    "ip_enforcement_restructuring": "ip",
    "ip_enforcement_restructuring_collateral": "ip",
    "legal_collection": "legal",
    "legal_collection_collateral": "legal",
    "legal_collection_collateral_auto": "legal",
    "initiation_legal": "legal",
    "initiation_physical": "individual",
    "physical_realization_collateral": "individual",
    "physical_restructuring_collateral": "individual",
    "observation_collateral": "individual",
    "competition_collateral": "individual",
    # rtk_application/mortgage_claim/unknown — применимы к любому типу лица,
    # document_type сам по себе тип лица не подразумевает.
}


def _entity_type_from_document_type(document_type):
    """Тип лица, который ПОДРАЗУМЕВАЕТ regex-тип документа — 'individual'/
    'legal'/'ip'. None — document_type не привязан к типу лица (rtk/mortgage/
    unknown), сравнивать не с чем.
    """
    return _ENTITY_TYPE_BY_DOCUMENT_TYPE.get(document_type)


_COLLATERAL_EXPECTED_BY_DOCUMENT_TYPE = {
    "ip_collection": False,
    "ip_collection_collateral": True,
    "ip_collection_collateral_auto": True,
    "ip_enforcement_statement": False,
    "ip_enforcement_statement_collateral": True,
    "ip_enforcement_realization": False,
    "ip_enforcement_realization_collateral": True,
    "ip_enforcement_restructuring": False,
    "ip_enforcement_restructuring_collateral": True,
    "legal_collection": False,
    "legal_collection_collateral": True,
    "legal_collection_collateral_auto": True,
    "physical_realization_collateral": True,
    "physical_restructuring_collateral": True,
    "observation_collateral": True,
    "competition_collateral": True,
    "mortgage_claim": True,
}


def _collateral_expected_from_document_type(document_type):
    """Ожидание залога (bool) по regex-типу документа. None — document_type
    не гарантирует ни присутствие, ни отсутствие залога (rtk/initiation_*/
    unknown), сравнивать не с чем.
    """
    return _COLLATERAL_EXPECTED_BY_DOCUMENT_TYPE.get(document_type)


class ClassifyMixin:
    if TYPE_CHECKING:
        # Реализован в document_analyzer.DocumentAnalyzer; здесь только для Pyright
        # (mixin-класс вызывает метод, который появится в итоговом составном классе).
        def _is_car_collateral_document(self, text: str) -> bool: ...

    def _self_bk_header_debtor_first(self, text: str) -> bool:
        """Шапка самобанкрота: первым идёт «Должник:»/«ФИО:», кредиторы — после.

        Необязательный паттерн (п.2.1 Андрея) — используется лишь как один из
        сильных сигналов. Метка «Заявитель» в шапке — признак кредиторской
        раскладки, сигнал не засчитываем.
        """
        head = text[:2500]
        m_debtor = _SELF_BK_HEAD_DEBTOR_RE.search(head)
        if not m_debtor:
            return False
        if _SELF_BK_HEAD_APPLICANT_RE.search(head):
            return False
        m_cred = _SELF_BK_HEAD_CREDITOR_RE.search(head)
        return m_cred is None or m_debtor.start() < m_cred.start()

    def _detect_self_bankruptcy(self, text: str) -> bool:
        """Определяет заявление САМОБАНКРОТСТВА (заявитель = сам должник).

        Слои с явным приоритетом:
        1) вето — явные приметы кредиторского заявления или ФНС-бланк;
        2) обязательное условие — в просительной части НЕТ «включить … в реестр
           требований / в N очередь» (кредиторские, включая инициирующие,
           всегда содержат такой пункт);
        3) хотя бы один сильный сигнал: первое лицо («признать меня/себя»),
           заголовок заявления должника, либо шапка «должник первым».
        """
        if not text:
            return False

        # 1. Вето: ФНС-бланк (заявитель — уполномоченный орган) и кредиторские приметы.
        if _SELF_BK_FNS_HEAD_RE.search(text[:400]) or _SELF_BK_FNS_TITLE_RE.search(text[:700]):
            return False
        for rx in _SELF_BK_VETO_RES:
            m = rx.search(text)
            if m:
                logger.info(
                    f"Самобанкротство: вето по кредиторскому признаку «{m.group(0)[:60]}»"
                )
                return False

        prayer_start = 0
        for m in _SELF_BK_PRAYER_RE.finditer(text):
            prayer_start = m.start()
        if _SELF_BK_RTK_RE.search(text[prayer_start:]):
            return False

        # 3. Сильные сигналы (достаточно одного).
        strong = []
        if _SELF_BK_FIRST_PERSON_RE.search(text):
            strong.append("первое лицо («признать меня/себя»)")
        if _SELF_BK_TITLE_RE.search(text):
            strong.append("заголовок заявления должника")
        if _SELF_BK_APPLICANT_IS_DEBTOR_RE.search(text):
            strong.append("метка «Заявитель (Должник)»")
        if self._self_bk_header_debtor_first(text):
            strong.append("шапка: должник первым")
        if not strong:
            return False

        support = [name for name, rx in _SELF_BK_SUPPORT_RES if rx.search(text)]
        logger.info(f"✅ Самобанкротство: сильные сигналы {strong}, поддерживающие {support}")
        return True

    def _initiation_petition_window(self, text: str) -> str:
        """Окно просительной части (от последнего «ПРОШУ/ПРОСИТ:»). Если метки нет —
        весь текст (консервативно)."""
        ps = 0
        for m in _SELF_BK_PRAYER_RE.finditer(text):
            ps = m.start()
        return text[ps:] if ps else text

    def _is_initiation_petition(self, text: str) -> bool:
        """Заявление ИНИЦИИРУЕТ банкротство: в просительной части просит суд признать
        должника банкротом и/или ввести процедуру. Отличает инициирование (в т.ч.
        кредиторское «о признании банкротом») от чистого ВКЛ-в-РТК, где просят лишь
        включить требование в реестр. Якорь — окно просьбы, чтобы не ловить прошедшее
        «должник признан банкротом решением от …» в теле включения."""
        if not text:
            return False
        window = self._initiation_petition_window(text)
        return bool(_INIT_DECLARE_RE.search(window) or _INIT_PROCEDURE_RE.search(window))

    def _initiation_type_by_entity(self, text: str, has_ip_name: bool, text_lower: str) -> str:
        """Тип инициирующего заявления по ДОЛЖНИКУ: ЮЛ → initiation_legal; ИП →
        ip_enforcement_* (процедура из текста); ФЛ → initiation_physical.

        Форму берём из сегментов, называющих ДОЛЖНИКА («о признании <должника>…»,
        «в отношении <должника>…», «Признать <должника> …банкротом»), а НЕ из
        реквизитов кредитора (иначе «ПАО»/«АО» банка-заявителя утекает в ЮЛ)."""
        window = self._initiation_petition_window(text)[:2500]
        # Сегменты, называющие ДОЛЖНИКА (после «о признании …»/«в отношении …»).
        parts = re.findall(r"(?:о\s+признани\w+|в\s+отношени\w+)\s+([^\n]{0,90})", window, re.IGNORECASE)

        if not parts:
            md = _INIT_DECLARE_RE.search(window)
            if md and not re.match(r"призна\w+\s+заявлени", window[md.start(): md.start() + 25], re.IGNORECASE):
                parts.append(window[md.start(): md.start() + 90])
        debtor_blob = " ".join(parts) if parts else window[:300]
        if _INIT_LEGAL_FORM_RE.search(debtor_blob):
            return "initiation_legal"
        if has_ip_name or _INIT_IP_FORM_RE.search(debtor_blob):
            is_restructuring = bool(re.search(r"реструктуризац", text_lower))
            return "ip_enforcement_restructuring" if is_restructuring else "ip_enforcement_realization"
        return "initiation_physical"

    def _detect_ip_debtor_name(self, text: str) -> bool:
        """Есть ли в тексте явное указание «ИП ФИО» в имени должника/ответчика.

        Логика 1-в-1 с проверкой внутри classify_document (строгие паттерны +
        контекстный fallback). Вынесено, чтобы переиспользовать в
        _maybe_upgrade_to_observation_collateral без дублирования паттернов.
        """
        ip_name_patterns = [
            r"должник[:\s]+\n\s*ИП\s+[А-ЯЁ]",
            r"ответчик[:\s]+\n\s*ИП\s+[А-ЯЁ]",
            r"должник[:\s]+ИП\s+[А-ЯЁ]",
            r"ответчик[:\s]+ИП\s+[А-ЯЁ]",
            r"должник[:\s]*\n[^\n]*ИП\s+[А-ЯЁ]",  # Более гибкий паттерн
            r"ответчик[:\s]*\n[^\n]*ИП\s+[А-ЯЁ]",  # Более гибкий паттерн
        ]
        has_ip_name = any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in ip_name_patterns)

        # Дополнительная проверка: "ИП ФИО" в контексте должника/ответчика/заемщика
        if not has_ip_name:
            ip_in_context = re.search(
                r"(?:должник|ответчик|заемщик)[^.]{0,200}?\bИП\s+[А-ЯЁ][А-ЯЁа-яё\s]{5,50}",
                text,
                re.IGNORECASE | re.MULTILINE,
            )
            if ip_in_context:
                has_ip_name = True
                logger.info("Найдено 'ИП' в контексте должника/ответчика")

        return has_ip_name

    def classify_document(self, text: str) -> str:
        """
        Классифицирует тип документа на основе содержимого
        """
        text_lower = text.lower()


        ip_name_patterns = [
            r"должник[:\s]+\n\s*ИП\s+[А-ЯЁ]",
            r"ответчик[:\s]+\n\s*ИП\s+[А-ЯЁ]",
            r"должник[:\s]+ИП\s+[А-ЯЁ]",
            r"ответчик[:\s]+ИП\s+[А-ЯЁ]",
            r"должник[:\s]*\n[^\n]*ИП\s+[А-ЯЁ]",  # Более гибкий паттерн
            r"ответчик[:\s]*\n[^\n]*ИП\s+[А-ЯЁ]",  # Более гибкий паттерн
        ]
        has_ip_name = any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in ip_name_patterns)

        if not has_ip_name:
            ip_in_context = re.search(r"(?:должник|ответчик|заемщик)[^.]{0,200}?\bИП\s+[А-ЯЁ][А-ЯЁа-яё\s]{5,50}", text, re.IGNORECASE | re.MULTILINE)
            if ip_in_context:
                has_ip_name = True
                logger.info(f"Найдено 'ИП' в контексте должника/ответчика")

        if not has_ip_name:
            logger.info("Не найдено явного указания 'ИП' в имени должника - это НЕ документ ИП")

            is_collection = any(keyword in text_lower for keyword in [
                "исковое заявление",
                "исковое заявление о взыскании",
                "взыскание с юл",
                "взыскания юл",
                "взыскание с юридического лица",
                "взыскания юридического лица"
            ])

            legal_entity_indicators = [
                "ооо", "оао", "зао", "пао", "общество с ограниченной ответственностью",
                "акционерное общество", "юридическое лицо", "юр лицо"
            ]
            has_legal_entity = any(indicator in text_lower for indicator in legal_entity_indicators)

            is_realization = any(keyword in text_lower for keyword in ["реализац", "реализации", "реализации имущества"])
            is_restructuring = any(keyword in text_lower for keyword in ["реструктуризац", "реструктуризации", "реструктуризации долгов"])
            is_observation = any(keyword in text_lower for keyword in ["наблюден", "наблюдения"])

            if is_collection and has_legal_entity and not is_realization and not is_restructuring and not is_observation:
                # Залоговым документ считается ТОЛЬКО при явной формулировке "обеспеченное залогом"
                required_collateral_phrases = [
                    r"обеспеченное\s+залогом",
                    r"обеспечено\s+залогом",
                    r"обеспечен\s+залогом",
                    r"обеспечена\s+залогом",
                    r"обеспечены\s+залогом",
                    r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                    r"обязательство.*обеспечен.*залогом",
                    r"обязательства.*обеспечен.*залогом"
                ]
                has_required_collateral_phrase = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in required_collateral_phrases)

                has_legal_collateral = False
                if has_required_collateral_phrase:
                    obligation_blocks = re.findall(r'Обязательство\s*№\s*(\d+)[:\s]*(.*?)(?=Обязательство\s*№\s*\d+[:\s]*|$)', text, re.DOTALL | re.IGNORECASE)
                    for obligation_num, block_text in obligation_blocks:
                        collateral_phrase = r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку"
                        if re.search(collateral_phrase, block_text, re.IGNORECASE | re.DOTALL):
                            has_legal_collateral = True
                            logger.info(f"Найден залог для ЮЛ в обязательстве №{obligation_num}")
                            break

                    if not has_legal_collateral:
                        legal_collateral_patterns = [
                            r"обязательство\s+№[^.]{0,1000}?В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                            r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку[^.]{0,500}?обязательство\s+№",
                            r"обязательство\s+№[^.]*?предоставил\s+в\s+залог\s+Банку",
                            r"В\s+качестве\s+обеспечения[^.]*?предоставил\s+в\s+залог\s+Банку"
                        ]
                        has_legal_collateral = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in legal_collateral_patterns)

                if has_legal_collateral:
                    if self._is_car_collateral_document(text):
                        logger.info("Определен тип документа: legal_collection_collateral_auto (Исковое заявление о взыскании с ЮЛ залог авто)")
                        return "legal_collection_collateral_auto"
                    logger.info("Определен тип документа: legal_collection_collateral (Исковое заявление о взыскании с ЮЛ с залогом)")
                    return "legal_collection_collateral"
                else:
                    logger.info("Определен тип документа: legal_collection (Исковое заявление о взыскании с ЮЛ)")
                    return "legal_collection"

        else:
            logger.info(f"Найдено имя должника с 'ИП' - это документ ИП")
            ip_score = 5  # Высокий балл, так как есть явное указание на ИП

        required_collateral_phrases = [
            r"обеспеченное\s+залогом",
            r"обеспечено\s+залогом",
            r"обеспечен\s+залогом",
            r"обеспечена\s+залогом",
            r"обеспечены\s+залогом",
            r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
            r"обязательство.*обеспечен.*залогом",
            r"обязательства.*обеспечен.*залогом"
        ]
        has_required_collateral_phrase = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in required_collateral_phrases)

        has_ip_collateral = False
        if has_ip_name and has_required_collateral_phrase:
            obligation_blocks = re.findall(r'Обязательство\s*№\s*(\d+)[:\s]*(.*?)(?=Обязательство\s*№\s*\d+[:\s]*|$)', text, re.DOTALL | re.IGNORECASE)
            for obligation_num, block_text in obligation_blocks:
                collateral_phrase = r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку"
                if re.search(collateral_phrase, block_text, re.IGNORECASE | re.DOTALL):
                    has_ip_collateral = True
                    logger.info(f"Найден залог для ИП в обязательстве №{obligation_num}")
                    break

            if not has_ip_collateral:
                ip_collateral_patterns = [
                    r"обязательство\s+№[^.]{0,1000}?В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                    r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку[^.]{0,500}?обязательство\s+№",
                    r"обязательство\s+№[^.]*?предоставил\s+в\s+залог\s+Банку",
                    r"В\s+качестве\s+обеспечения[^.]*?предоставил\s+в\s+залог\s+Банку"
                ]
                has_ip_collateral = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in ip_collateral_patterns)

        if has_ip_name:
            is_collection = any(keyword in text_lower for keyword in [
                "исковое заявление",
                "исковое заявление о взыскании",
                "взыскание с ип",
                "взыскания ип"
            ])

            is_realization = any(keyword in text_lower for keyword in ["реализац", "реализации", "реализации имущества"])
            is_restructuring = any(keyword in text_lower for keyword in ["реструктуризац", "реструктуризации", "реструктуризации долгов"])

            if is_collection and not is_realization and not is_restructuring:
                if has_ip_collateral:
                    if self._is_car_collateral_document(text):
                        logger.info("Определен тип документа: ip_collection_collateral_auto (Исковое заявление о взыскании с ИП залог авто)")
                        return "ip_collection_collateral_auto"
                    logger.info("Определен тип документа: ip_collection_collateral (Исковое заявление о взыскании с ИП с залогом)")
                    return "ip_collection_collateral"
                else:
                    logger.info("Определен тип документа: ip_collection (Исковое заявление о взыскании с ИП)")
                    return "ip_collection"

            if has_ip_collateral:
                if is_restructuring:
                    logger.info("Определен тип документа: ip_enforcement_restructuring_collateral (ИП реструктуризация с залогом)")
                    return "ip_enforcement_restructuring_collateral"
                elif is_realization:
                    logger.info("Определен тип документа: ip_enforcement_realization_collateral (ИП реализация с залогом)")
                    return "ip_enforcement_realization_collateral"
                else:
                    # По умолчанию реализация, если не указано явно
                    logger.info("Определен тип документа: ip_enforcement_realization_collateral (ИП с залогом, по умолчанию реализация)")
                    return "ip_enforcement_realization_collateral"
            else:
                if is_restructuring:
                    logger.info("Определен тип документа: ip_enforcement_restructuring (ИП реструктуризация без залога)")
                    return "ip_enforcement_restructuring"
                elif is_realization:
                    logger.info("Определен тип документа: ip_enforcement_realization (ИП реализация без залога)")
                    return "ip_enforcement_realization"
                else:
                    # По умолчанию реализация, если не указано явно
                    logger.info("Определен тип документа: ip_enforcement_realization (ИП без залога, по умолчанию реализация)")
                    return "ip_enforcement_realization"

        return self._classify_by_scoring(text, has_ip_name, text_lower)

    def _classify_by_scoring(self, text, has_ip_name, text_lower):
        """Классификация по скорингу ключевых слов: rtk/initiation/mortgage/initiation_legal, иначе unknown. Вынесено из classify_document."""
        rtk_keywords = [
            "включении в реестр требований кредиторов",
            "реестр требований кредиторов",
            "ртк",
            "банкротство",
            "арбитражный суд",
            "заявление о включении"
        ]

        rtk_score = sum(1 for keyword in rtk_keywords if keyword in text_lower)

        if rtk_score >= 2:
            # Залоговым документ считается ТОЛЬКО при явной формулировке "обеспеченное залогом"
            required_collateral_phrases = [
                r"обеспеченное\s+залогом",
                r"обеспечено\s+залогом",
                r"обеспечен\s+залогом",
                r"обеспечена\s+залогом",
                r"обеспечены\s+залогом",
                r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                r"обязательство.*обеспечен.*залогом",
                r"обязательства.*обеспечен.*залогом"
            ]
            has_required_collateral_phrase = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in required_collateral_phrases)

            has_physical_collateral = False
            if has_required_collateral_phrase:
                collateral_phrases = [
                    r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                    r"что\s+подтверждается\s+договором\s+залога",
                    r"договор\s+залога\s+№",
                    r"предоставил\s+в\s+залог\s+Банку\s+объект\s+недвижимости"
                ]
                has_physical_collateral = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in collateral_phrases)

            if has_physical_collateral and not has_ip_name:
                is_restructuring = any(keyword in text_lower for keyword in ["реструктуризац", "реструктуризации", "реструктуризации долгов"])
                is_realization = any(keyword in text_lower for keyword in ["реализац", "реализации", "реализации имущества"])
                is_observation = any(keyword in text_lower for keyword in ["наблюден", "наблюдения", "процедура наблюдения"])
                is_competition = any(keyword in text_lower for keyword in ["конкурсн", "конкурсное производство", "конкурсного производства"])

                if is_competition:
                    logger.info("Определен тип документа: competition_collateral (Конкурсное производство с залогом)")
                    return "competition_collateral"
                elif is_restructuring:
                    logger.info("Определен тип документа: physical_restructuring_collateral (ФЛ с залогом в реструктуризации)")
                    return "physical_restructuring_collateral"
                elif is_realization:
                    logger.info("Определен тип документа: physical_realization_collateral (ФЛ с залогом в реализации)")
                    return "physical_realization_collateral"
                elif is_observation:
                    logger.info("Определен тип документа: observation_collateral (Наблюдение с залогом)")
                    return "observation_collateral"


            if self._is_initiation_petition(text) and not self._detect_self_bankruptcy(text):
                itype = self._initiation_type_by_entity(text, has_ip_name, text_lower)
                logger.info(f"Определен тип документа: {itype} (инициирующая просьба, не ВКЛ-в-РТК)")
                return itype

            return "rtk_application"

        initiation_keywords = [
            "заявление о признании гражданина банкротом",
            "заявление о признании должника банкротом",
            "признать должника несостоятельным",
            "признать гражданина банкротом",
            "реструктуризаци",
            "реализац",
            "введени[ея]\\s+реструктуризации",
            "введени[ея]\\s+реализац",
            "гражданина банкротом",
            "дело о банкротстве гражданина"
        ]

        initiation_score = sum(1 for keyword in initiation_keywords if re.search(keyword, text_lower))
        if initiation_score >= 2:
            return "initiation_physical"


        if self._is_initiation_petition(text) and not self._detect_self_bankruptcy(text):
            itype = self._initiation_type_by_entity(text, has_ip_name, text_lower)
            if itype != "initiation_physical":
                logger.info(f"Определен тип документа: {itype} (инициирующая просьба, залоговые слова не мешают)")
                return itype

        mortgage_keywords = [
            r"ипотек",
            r"предмет\s+залога",
            r"кадастровый\s+номер",
            r"начальн[а-я]+\s+цен[аы]\s+продаж",
            r"заложенного\s+имуществ",
            r"жилой\s+дом",
            r"земельн[а-я]+\s+участ",
            r"установить\s+начальную\s+цену",
            r"отчет\s+об\s+оценке"
        ]
        mortgage_markers = bool(re.search(r"\[12(?:21|22|23|24|25)\]", text_lower))
        mortgage_score = sum(1 for keyword in mortgage_keywords if re.search(keyword, text_lower))

        if mortgage_markers or mortgage_score >= 2:
            return "mortgage_claim"

        initiation_legal_keywords = [
            "заявление о признании должника банкротом",
            "признать должника несостоятельным",
            "ооо",
            "оао",
            "зао",
            "пао",
            "общество с ограниченной ответственностью",
            "акционерное общество",
            "юридическое лицо",
            "юр лицо",
            "введени[ея]\\s+наблюдения",
            "наблюдение",
            "по состоянию на.*\\[88\\]",
            "\\[88\\]"
        ]

        has_marker_88 = bool(re.search(r'\[88\]', text))
        legal_entity_indicators = [
            "ооо", "оао", "зао", "пао", "общество", "акционерное",
            "юридическое лицо", "юр лицо"
        ]
        has_legal_entity = any(indicator in text_lower for indicator in legal_entity_indicators)
        initiation_legal_score = sum(1 for keyword in initiation_legal_keywords if re.search(keyword, text_lower))

        if (initiation_legal_score >= 2 and has_legal_entity) or (has_marker_88 and has_legal_entity):
            return "initiation_legal"

        return "unknown"

    def _classify_collateral(self, desc: str) -> str:
        """Определяет тип предмета залога: 'auto' / 'real_estate' / 'other'."""
        d = (desc or "").lower()
        if re.search(r"\bvin\b|идентификационн\w+\s+номер|\bмарка\b|\bмодель\b|кузов|"
                     r"\bптс\b|год\s+выпуска|транспортн\w+\s+средств|автомобил|автомаш|"
                     r"гос\.?\s*номер|госномер", d):
            return "auto"
        if re.search(r"кадастр|квартир|жил\w*\s*дом|\bдом\b|нежил|земельн\w+\s+участ|"
                     r"помещени|здани|строени|недвижим|ипотек|комнат|гараж|"
                     r"машино-?мест|сооружени", d):
            return "real_estate"
        return "other"

    def detect_entity_type(self, fields: Dict[str, Any]) -> Optional[str]:
        """
        Определяет тип должника: КФХ, ЮЛ, ИП или ФЛ по извлечённым данным.
        Важно: для решения используем только имя ДОЛЖНИКА (debtorName или applicantName как fallback),
        чтобы не принять за должника название кредитора (банка).
        Приоритет: КФХ → ЮЛ (явно в названии) → ИП (явно ИП) → ФЛ (ФИО) → ЮЛ по реквизитам.
        """
        applicant_name_raw = (fields.get("applicantName") or "").strip()
        debtor_name_raw = (fields.get("debtorName") or "").strip()
        # Имя для определения типа — приоритет у должника, иначе заявитель (в РТК заявитель = кредитор, должник = физлицо/юрлицо)
        name_for_entity = debtor_name_raw or applicant_name_raw
        name_lower = name_for_entity.lower()
        # Маркер «ИП»/«КФХ» может быть в одном имени, а ФИО — в другом
        # (debtorName = «КУКУСИК…», applicantName = «ИП Кукусик…»). Поэтому ищем в обоих.
        both_names_lower = (debtor_name_raw + " " + applicant_name_raw).lower()
        inn_value = re.sub(r"\D", "", str(fields.get("inn") or ""))
        ogrn_value = re.sub(r"\D", "", str(fields.get("ogrn") or ""))
        ogrnip_value = re.sub(r"\D", "", str(fields.get("ogrnip") or ""))
        company_inn_value = re.sub(r"\D", "", str(fields.get("companyInn") or ""))
        snils_value = re.sub(r"\D", "", str(fields.get("snils") or ""))

        # ФИО: три слова (поддержка "Иван Иванов Иванович" и "ХЛИЯН ЕЛЕНА ОГАНОВНА").
        # Скобочную девичью фамилию убираем («Атанасян (Кулемзина) Валерия Сергеевна»).
        name_no_paren = re.sub(r"\([^)]*\)", " ", name_for_entity)
        fio_pattern = r"[А-ЯЁа-яё]{2,}\s+[А-ЯЁа-яё]{2,}\s+[А-ЯЁа-яё]{2,}"
        has_fio_in_name = bool(re.search(fio_pattern, name_no_paren))

        legal_indicators = [
            "ооо", "оао", "пао", "зао", " ao", "ao ",
            "общество с ограниченной ответственностью",
            "ограниченной ответственностью",
            "акционерное общество",
            "компания с ограниченной ответственностью",
        ]
        has_legal_tokens_in_names = any(token in name_lower for token in legal_indicators)
        has_fio = has_fio_in_name and not has_legal_tokens_in_names
        has_individual_inn_or_snils = (inn_value and len(inn_value) == 12) or (snils_value and len(snils_value) == 11)

        # 1. КФХ (маркер в любом из имён должника)
        if fields.get("isKfh"):
            return "kfh"
        if "глава кфх" in both_names_lower or "кфх ип" in both_names_lower or re.search(r"\bкфх\b", both_names_lower):
            return "kfh"

        # 2. ЮЛ — только при явных признаках в названии должника (ООО, ПАО и т.д.)
        if has_legal_tokens_in_names:
            return "legal"
        if fields.get("legalShortName") and not has_fio:
            return "legal"

        # 3. ИП — маркер «ИП»/«индивидуальный предприниматель» в имени должника
        # ЛИБО наличие ОГРНИП (его имеют только ИП), даже если в имени лишь ФИО.
        if re.search(r"\bип\b", both_names_lower) or "индивидуальн" in both_names_lower:
            return "ip"
        if len(ogrnip_value) == 15:
            return "ip"

        # 3b. ОГРН (13 цифр) есть ТОЛЬКО у юрлиц — должник с ОГРН не может быть
        # физлицом (перебивает ложный has_fio из мусорного debtorName).
        if len(ogrn_value) == 13:
            return "legal"

        # 4. ФЛ — ФИО или ИНН 12 / СНИЛС; приоритет над 10-значным ИНН (который может быть от кредитора)
        if has_fio or has_individual_inn_or_snils:
            return "individual"

        # 5. ЮЛ по реквизитам — только если имя НЕ похоже на ФИО (иначе не переопределяем: ИНН/ОГРН могут быть кредитора)
        if has_fio_in_name:
            return "individual"
        if ogrn_value and len(ogrn_value) >= 10:
            return "legal"
        if company_inn_value and len(company_inn_value) in {9, 10}:
            return "legal"
        if inn_value and len(inn_value) == 10:
            return "legal"

        return None

    def determine_procedure_type(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Определяет тип процедуры банкротства (реструктуризация/реализация/умерший) на основе текста заявления.

        Возвращает кортеж (normalized, raw), где normalized принимает значения
        'restructuring', 'realization' или 'deceased'. Если определить не удалось, возвращает (None, None).
        """
        if not text:
            return None, None

        text_lower = text.lower()

        # Приоритет: процедура "умерший" проверяется первой
        deceased_keywords = ["умер", "умерший", "смерть", "смерти"]
        if any(keyword in text_lower for keyword in deceased_keywords):
            logger.info("Определена процедура: умерший (по ключевым словам)")
            return "deceased", "умерший"

        # Берем окно вокруг фразы "признан ... банкротом" чтобы гарантировать корректный контекст
        window_match = re.search(
            r"признан[^\n]{0,40}?(?:несостоятельным\s*\(\s*)?банкротом[\s\S]{0,400}?в\s+отношении\s+должника\s+введена\s+процедура\s+([А-ЯЁа-яё\s]+?)"
            r"(?=[,.;:\-—\n\r]|$)",
            text,
            re.IGNORECASE
        )

        if not window_match:
            # fallback: ищем любую фразу "введена процедура ..." без привязки к началу
            window_match = re.search(
                r"введена\s+процедура\s+([А-ЯЁа-яё\s]+?)(?=[,.;:\-—\n\r]|$)",
                text,
                re.IGNORECASE
            )

        if not window_match:
            logger.info("Не удалось определить тип процедуры - паттерн не найден")
            return None, None

        raw_procedure = window_match.group(1).strip()
        raw_procedure = re.sub(r"\s+", " ", raw_procedure)
        raw_lower = raw_procedure.lower()

        if "реструктур" in raw_lower:
            return "restructuring", raw_procedure
        if "реализац" in raw_lower:
            return "realization", raw_procedure

        logger.info(f"Не удалось нормализовать тип процедуры по тексту: {raw_procedure}")
        return None, raw_procedure

