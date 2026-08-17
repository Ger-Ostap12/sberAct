import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import field_contract
from creditor_registry import _match_creditor_registry
from fio_detector import (
    extract_debtor_details,
    extract_debtor_name,
    extract_debtors,
    extract_third_parties,
    extract_third_party_details,
    is_person_name,
)
from requisites_validation import is_valid_inn, is_valid_ogrnip

logger = logging.getLogger(__name__)


class PartiesMixin:
    if TYPE_CHECKING:
        # Реализованы в document_analyzer.DocumentAnalyzer / classify_mixin.ClassifyMixin /
        # inflection_mixin.InflectionMixin; здесь только для Pyright (mixin-класс
        # вызывает методы/константу, которые появятся в итоговом составном классе).
        _NAME_PREFIX_RE: str
        _COURT_KIND_RE: str
        _COURT_LOWER_WORDS: "set[str]"

        def clean_extracted_value(self, value: str) -> str: ...
        def detect_entity_type(self, fields: Dict[str, Any]) -> Optional[str]: ...
        def _strip_ooo_prefix(self, name: Optional[str]) -> Optional[str]: ...
        def _extract_creditor_name_from_text(self, text: str) -> Optional[str]: ...
        def extract_legal_entity_short_name(self, text: Optional[str]) -> Optional[str]: ...
        def _extract_creditor_block(self, text: str) -> Optional[str]: ...
        def _extract_creditor_address(self, text: str) -> Optional[str]: ...
        def _clean_court_line(self, s: str) -> Optional[str]: ...
        def _convert_name_to_genitive(self, full_name: str) -> Optional[str]: ...
        def _convert_name_to_dative(self, full_name: str) -> Optional[str]: ...
        def _convert_name_to_instrumental(self, full_name: str) -> Optional[str]: ...
        def _convert_name_to_accusative(self, full_name: str) -> Optional[str]: ...
    _PROVENANCE_KEY = "_provenance"

    def _extract_party_inn_ogrn(self, extracted_fields, text, field_name):
        """ИНН/ОГРН/ОГРНИП должника строго из блока «Должник:»/«Ответчик:» (а не кредитора), с валидацией контрольной суммы. Все пути исходно завершались continue. Вынесено из основного pattern-цикла extract_fields."""
        debtor_block = None

        # Сначала пытаемся найти блок "Должник:" (как в реструктуризации)
        debtor_block_match = re.search(
            r"Должник[:\s]*(.*?)(?=\n\s*\n|Временн(?:ый|ым)\s+управляющ|Сумма\s+требований|ЗАЯВЛЕНИЕ|Дело\s*№|$)",
            text,
            re.IGNORECASE | re.DOTALL
        )
        if debtor_block_match:
            debtor_block = debtor_block_match.group(1)
            debtor_block = debtor_block.replace('\u202f', ' ').replace('\xa0', ' ')
            logger.info(f"Найден блок Должник: длина {len(debtor_block)}")

        # Для взысканий ИП часто вместо полноценного "Должник:" есть блок "Ответчик(и):"
        # и он содержит ИНН/ОГРНИП. Если "Должник:" слишком короткий, пытаемся взять этот блок.
        if debtor_block and len(debtor_block.strip()) < 120:
            respondents_match = re.search(
                r"Ответчик(?:\(и\))?[:\s]*\n\s*(.*?)(?=\n\s*\n|Требовани[ея]\s*№|Требовани[ея]\s+№|ЗАЯВЛЕНИЕ|ПРОСИТ\s+СУД|ПРОШУ|$)",
                text,
                re.IGNORECASE | re.DOTALL,
            )
            if respondents_match:
                debtor_block = respondents_match.group(1)
                debtor_block = debtor_block.replace("\u202f", " ").replace("\xa0", " ")
                logger.info(f"Найден блок Ответчик(и): длина {len(debtor_block)}")

        # Если блока "Должник:" нет, ищем блок "Ответчик:"
        if not debtor_block:
            answer_matches = list(re.finditer(r"Ответчик[:\s]", text, re.IGNORECASE))
            logger.info(f"Найдено блоков 'Ответчик:': {len(answer_matches)}")
            if answer_matches:
                # Берем первый блок "Ответчик:"
                answer_match = answer_matches[0]
                start_pos = answer_match.start()
                logger.info(f"Позиция начала блока 'Ответчик:': {start_pos}")

                # Находим следующий "Истец:" ПОСЛЕ этого "Ответчик:" или конец документа
                end_pos = len(text)
                next_plaintiff = re.search(r"Истец[:\s]", text[start_pos:], re.IGNORECASE)
                if next_plaintiff:
                    end_pos = start_pos + next_plaintiff.start()
                    logger.info(f"Найден следующий 'Истец:' на позиции: {end_pos}")
                else:
                    logger.info(f"Следующий 'Истец:' не найден, используем конец документа: {end_pos}")

                debtor_block = text[start_pos:end_pos]
                logger.info(f"Найден блок Ответчик: позиция {start_pos}-{end_pos}, длина {len(debtor_block)}")
                logger.debug(f"Первые 200 символов блока: {debtor_block[:200]}")
                # Для отладки ogrnip выводим весь блок, если он не слишком длинный
                if field_name == "ogrnip" and len(debtor_block) < 1000:
                    logger.debug(f" Полный блок Ответчик для ogrnip: {debtor_block}")

        # Извлекаем ИНН или ОГРН из найденного блока должника/ответчика
        if debtor_block:
            found_value = False

            if field_name == "ogrn" or field_name == "ogrnip":
                # Извлекаем ОГРН/ОГРНИП (как в реструктуризации)
                logger.info(f"Ищем {'ОГРНИП' if field_name == 'ogrnip' else 'ОГРН'} в блоке должника/ответчика...")
                ogrn_match = None

                # Для ogrnip сначала ищем маркер [4.1] и ОГРНИП
                if field_name == "ogrnip":
                    # Паттерн для маркера [4.1] (ОГРНИП) - проверяем ПЕРВЫМ
                    ogrn_match = re.search(r"\[4\.1\]\s*([0-9\s]{12,15})", debtor_block)
                    if ogrn_match:
                        logger.info(f"Найден ОГРНИП паттерн [4.1]: {ogrn_match.group(1)}")
                    if not ogrn_match:
                        ogrn_match = re.search(r"([0-9\s]{12,15})\s*\[4\.1\]", debtor_block)
                        if ogrn_match:
                            logger.info(f"Найден ОГРНИП паттерн [4.1] (обратный): {ogrn_match.group(1)}")
                    if not ogrn_match:
                        # Ищем явное упоминание ОГРНИП с двоеточием
                        ogrn_match = re.search(r"ОГРНИП[:\s]+([0-9\s]{12,15})", debtor_block, re.IGNORECASE)
                        if ogrn_match:
                            logger.info(f"Найден ОГРНИП паттерн (с двоеточием): {ogrn_match.group(1)}")
                    if not ogrn_match:
                        # Ищем ОГРНИП без двоеточия (пробел или сразу число)
                        ogrn_match = re.search(r"ОГРНИП\s+([0-9\s]{12,15})", debtor_block, re.IGNORECASE)
                        if ogrn_match:
                            logger.info(f"Найден ОГРНИП паттерн (без двоеточия): {ogrn_match.group(1)}")
                    if not ogrn_match:
                        # Ищем число перед ОГРНИП
                        ogrn_match = re.search(r"([0-9\s]{12,15})\s+ОГРНИП", debtor_block, re.IGNORECASE)
                        if ogrn_match:
                            logger.info(f"Найден ОГРНИП паттерн (число перед): {ogrn_match.group(1)}")
                    if not ogrn_match:

                        for cand in re.finditer(r"ОГРНИП[:\s]*([0-9][0-9\s]{13,20})", text, re.IGNORECASE):
                            digits = re.sub(r"\D", "", cand.group(1))[:15]
                            if len(digits) == 15 and is_valid_ogrnip(digits):
                                extracted_fields["ogrnip"] = digits
                                found_value = True
                                logger.info(f" Extracted ogrnip (фолбэк по тексту, 15 цифр): {digits}")
                                break

                if field_name == "ogrn" and not ogrn_match:
                    ogrn_match = re.search(r"ОГРН[:\s]*([0-9\s]{12,15})", debtor_block, re.IGNORECASE)
                    if ogrn_match:
                        logger.info(f"Найден ОГРН паттерн 1: {ogrn_match.group(1)}")
                if field_name == "ogrn" and not ogrn_match:
                    ogrn_match = re.search(r"([0-9\s]{12,15})\s*\[3\]", debtor_block)
                    if ogrn_match:
                        logger.info(f"Найден ОГРН паттерн [3]: {ogrn_match.group(1)}")
                if ogrn_match:
                    ogrn_value = re.sub(r"\D", "", ogrn_match.group(1))
                    logger.info(f"Очищенное значение: '{ogrn_value}', длина: {len(ogrn_value) if ogrn_value else 0}")
                    if field_name == "ogrnip":
                        # ОГРНИП индивидуального предпринимателя — строго 15 цифр.
                        # Если кандидат не 15 цифр — это не ОГРНИП (напр. ОГРН ЮЛ 13 цифр), не пишем.
                        if ogrn_value and len(ogrn_value) == 15:
                            extracted_fields["ogrnip"] = ogrn_value
                            found_value = True
                            logger.info(f" Extracted ogrnip (15 цифр): {ogrn_value}")
                        else:
                            logger.info(f" Кандидат в ОГРНИП не 15 цифр ('{ogrn_value}') — пропускаем (не ОГРНИП)")
                    else:
                        # ОГРН юрлица — 13 цифр (допускаем 12-15 ради совместимости с прежним поведением).
                        if ogrn_value and 12 <= len(ogrn_value) <= 15:
                            extracted_fields["ogrn"] = ogrn_value
                            found_value = True
                            logger.info(f" Extracted ogrn: {ogrn_value}")
                        else:
                            logger.warning(f" ОГРН не прошёл проверку длины: '{ogrn_value}' (длина: {len(ogrn_value) if ogrn_value else 0})")
                else:
                    logger.warning(f" ОГРН/ОГРНИП не найден в блоке должника/ответчика")

            elif field_name == "inn" or field_name == "companyInn":
                # Извлекаем ИНН (как в реструктуризации)
                logger.info(f"Ищем {field_name} в блоке должника/ответчика...")
                inn_candidates = re.findall(r"ИНН[:\s]*([0-9\s]{9,12})", debtor_block, re.IGNORECASE)
                inn_candidates += re.findall(r"([0-9\s]{9,12})\s*\[4\]", debtor_block)
                inn_clean = []
                for raw in inn_candidates:
                    digits = re.sub(r"\D", "", raw)
                    if 9 <= len(digits) <= 12:
                        inn_clean.append(digits)
                inn_value = None
                if inn_clean:
                    # Первый валидный по контрольной сумме, иначе — первый найденный.
                    inn_value = next((c for c in inn_clean if is_valid_inn(c)), inn_clean[0])
                    if not is_valid_inn(inn_value):
                        logger.debug(f"ИНН '{inn_value}' не прошёл контрольную сумму, оставлен как есть")
                if inn_value:
                    extracted_fields["inn"] = inn_value
                    extracted_fields["companyInn"] = inn_value
                    logger.info(f" Extracted {field_name} из блока должника/ответчика: {inn_value}")
                    found_value = True
                else:
                    logger.warning(f" ИНН не найден в блоке должника/ответчика")

            # Если нашли значение в блоке должника/ответчика, пропускаем дальнейший поиск
            if found_value:
                logger.info(f" {field_name} найден в блоке должника/ответчика: {extracted_fields.get(field_name)}")
                return
            else:
                logger.info(f" {field_name} НЕ найден в блоке должника/ответчика - пропускаем дальнейший поиск, чтобы не брать данные кредитора")
                # Пропускаем дальнейший поиск, чтобы не брать ИНН/ОГРН кредитора
                return
        else:
            logger.info(f" Блоки 'Должник:' и 'Ответчик:' не найдены для {field_name}")
            # Если блоков нет, пропускаем поиск, чтобы не брать данные кредитора
            return

    def _extract_party_address(self, extracted_fields, text, field_name):
        """Адрес должника из блока «Должник:»/«Ответчик:» (юр.адрес/адрес регистрации/место нахождения), с очисткой строк от маркеров и служебных токенов. Возвращает True, если адрес установлен (тогда основной цикл делает continue). Вынесено из pattern-цикла."""
        debtor_block = None

        debtor_block_match = re.search(
            r"Должник[:\s]*(.*?)(?=\n\s*\n|Временн(?:ый|ым)\s+управляющ|Сумма\s+требований|ЗАЯВЛЕНИЕ|Дело\s*№|$)",
            text,
            re.IGNORECASE | re.DOTALL
        )
        if debtor_block_match:
            debtor_block = debtor_block_match.group(1)
        else:
            answer_matches = list(re.finditer(r"Ответчик[:\s]", text, re.IGNORECASE))
            if answer_matches:
                answer_match = answer_matches[0]
                start_pos = answer_match.start()
                end_pos = len(text)
                next_plaintiff = re.search(r"Истец[:\s]", text[start_pos:], re.IGNORECASE)
                if next_plaintiff:
                    end_pos = start_pos + next_plaintiff.start()
                debtor_block = text[start_pos:end_pos]

        if debtor_block:
            debtor_block = debtor_block.replace('\u202f', ' ').replace('\xa0', ' ')
            # Первичная попытка — единый надёжный многострочный сборщик
            # (ловит перенос строки, отсекает префикс ОГРН/ИНН и хвост-мусор).
            robust_addr = self._collect_block_address(debtor_block)
            if robust_addr:
                extracted_fields[field_name] = robust_addr
                logger.info(f" Extracted applicantAddress (robust): {robust_addr}")
                return True
            addr_match = re.search(
                # Берем только текущую строку после маркера адреса,
                # чтобы не захватывать дальнейший текст иска.
                r"(?:юридический\s+адрес|адрес\s+регистрации|место\s+нахождения)[:\s]*([^\n\r]+)",
                debtor_block,
                re.IGNORECASE
            )
            if addr_match:
                addr_raw = addr_match.group(1)
                addr_lines = re.split(r"[\n\r]+", addr_raw)
                cleaned_lines = []
                for line in addr_lines:
                    line = re.sub(r"\[[0-9\.]+\]", "", line)
                    line = line.strip(" ,.:-;")
                    if not line:
                        continue
                    lower_line = line.lower()
                    if any(token in lower_line for token in [
                        "инн", "огрн", "огрнип", "кпп", "телефон", "e-mail", "email",
                        "цена иска", "исковое заявление", "о взыскании", "просит суд"
                    ]):
                        continue
                    cleaned_lines.append(line)

                if cleaned_lines:
                    extracted_fields[field_name] = ", ".join(cleaned_lines).strip()
                    logger.info(f" Extracted applicantAddress из блока должника/ответчика: {extracted_fields[field_name]}")
                    return True
        return False

    def _extract_legal_entity_requisites(self, extracted_fields, text):
        """Реквизиты ЮЛ из блока «Должник:»: юридический адрес (в т.ч. многострочный), ОГРН, ИНН (по контрольной сумме), адрес КФХ. Возвращает найденный debtor_block для downstream-логики. Вынесено из extract_fields."""
        debtor_block_match = re.search(
            r"Должник[:\s]*(.*?)(?=\n\s*\n|Временн(?:ый|ым)\s+управляющ|Сумма\s+требований|ЗАЯВЛЕНИЕ|Дело\s*№|$)",
            text,
            re.IGNORECASE | re.DOTALL
        )
        debtor_block = None
        if debtor_block_match:
            debtor_block = debtor_block_match.group(1)
            debtor_block = debtor_block.replace('\u202f', ' ').replace('\xa0', ' ')

            # Единый надёжный сбор адреса (перенос строк, отсечение префикса ОГРН/ИНН).
            robust_addr = self._collect_block_address(debtor_block)
            if robust_addr:
                extracted_fields["applicantAddress"] = robust_addr

            # Извлекаем юридический адрес, если он есть в блоке должника
            address_match = re.search(
                r"юридический\s+адрес[:\s]*([^\n\r]+(?:[\n\r]+[^\n\r]+)*)",
                debtor_block,
                re.IGNORECASE
            )
            if not extracted_fields.get("applicantAddress") and address_match:
                address_text = address_match.group(1)
                address_lines = re.split(r"[\n\r]+", address_text)
                cleaned_lines = []
                for line in address_lines:
                    line = re.sub(r"\[[0-9\.]+\]", "", line)
                    line = line.strip(" ,.:-;")
                    if not line:
                        continue
                    lower_line = line.lower()
                    if any(token in lower_line for token in ["инн", "огрн", "кпп", "телефон", "e-mail", "email"]):
                        continue
                    cleaned_lines.append(line)

                if cleaned_lines:
                    extracted_fields["applicantAddress"] = ", ".join(cleaned_lines)
            elif not extracted_fields.get("applicantAddress"):
                # fallback: для физических лиц ищем адрес регистрации/проживания в блоке должника
                # Сначала пробуем вариант с индексом
                residence_match = re.search(
                    r"(?:место\s+жительства|адрес\s+регистрации)[:\s]*([0-9]{6}[^\n]+)",
                    debtor_block,
                    re.IGNORECASE
                )
                if not residence_match:
                    # Если индекса нет (как в "Адрес регистрации: Ростовская область, г РОСТОВ-НА-ДОНУ,\nул ЕРЕМЕНКО, ..."),
                    # берём всё после "Адрес регистрации:" / "место жительства:" включая следующую строку.
                    residence_match = re.search(
                        r"(?:место\s+жительства|адрес\s+регистрации)[:\s]*([^\n\r]+(?:[\n\r]+[^\n\r]+)*)",
                        debtor_block,
                        re.IGNORECASE
                    )
                if residence_match:
                    addr_raw = residence_match.group(1)
                    addr_clean = self.clean_extracted_value(addr_raw)
                    # Очищаем мусор после служебных слов (ИНН, ОГРН и т.п.)
                    for token in ["инн", "огрн", "огрнип", "кпп", "телефон", "e-mail", "email"]:
                        token_lower = token.lower()
                        idx = addr_clean.lower().find(token_lower)
                        if idx != -1:
                            addr_clean = addr_clean[:idx].strip()
                    extracted_fields["applicantAddress"] = addr_clean

                # Универсальный фолбэк: пытаемся собрать многострочный адрес (в т.ч. для ипотеки)
                if not extracted_fields.get("applicantAddress"):
                    multi_addr = self._extract_multiline_address_from_block(debtor_block)
                    if multi_addr:
                        extracted_fields["applicantAddress"] = multi_addr
                        logger.info(f" Extracted applicantAddress (multiline fallback): {multi_addr}")

            # Извлекаем ОГРН (только если еще не извлечен в основном цикле)
            if "ogrn" not in extracted_fields or not extracted_fields.get("ogrn"):
                ogrn_match = re.search(r"ОГРН[:\s]*([0-9\s]{12,15})", debtor_block, re.IGNORECASE)
                if not ogrn_match:
                    ogrn_match = re.search(r"ОГРНИП[:\s]*([0-9\s]{15})", debtor_block, re.IGNORECASE)
                if not ogrn_match:
                    ogrn_match = re.search(r"([0-9\s]{12,15})\s*\[3\]", debtor_block)
                if ogrn_match:
                    ogrn_value = re.sub(r"\D", "", ogrn_match.group(1))
                    # Проверяем длину ОГРН: 12-15 цифр (для ЮЛ может быть 12 или 13 цифр, для ИП - 15)
                    if ogrn_value and len(ogrn_value) >= 12 and len(ogrn_value) <= 15:
                        extracted_fields["ogrn"] = ogrn_value
                        logger.info(f" Extracted ogrn из блока Должник (после цикла): {ogrn_value}")

            # Извлекаем ИНН (только если еще не извлечен в основном цикле).
            # Среди кандидатов предпочитаем валидного по контрольной сумме.
            if "inn" not in extracted_fields or not extracted_fields.get("inn"):
                inn_candidates = re.findall(r"ИНН[:\s]*([0-9\s]{10,12})", debtor_block, re.IGNORECASE)
                inn_candidates += re.findall(r"([0-9\s]{10,12})\s*\[4\]", debtor_block)
                inn_clean = [re.sub(r"\D", "", c) for c in inn_candidates]
                inn_clean = [c for c in inn_clean if 10 <= len(c) <= 12]
                if inn_clean:
                    inn_value = next((c for c in inn_clean if is_valid_inn(c)), inn_clean[0])
                    extracted_fields["inn"] = inn_value
                    extracted_fields["companyInn"] = inn_value
                    logger.info(f"Extracted inn из блока Должник (после цикла): {inn_value}")

            # Определяем КФХ: после "Должник" указывается "ГЛАВА КФХ ИП ФИО"
            # Пример: "ГЛАВА КФХ ИП Иванов Иван Иванович"
            # Если КФХ уже было определено ранним определением, не перезаписываем
            if not extracted_fields.get("isKfh"):
                kfh_match = re.search(
                    r"глава\s+кфх\s+ип\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})",
                    debtor_block,
                    re.IGNORECASE
                )
                if kfh_match:
                    extracted_fields["isKfh"] = True
                    extracted_fields["kfhHeadName"] = kfh_match.group(1).strip()
                    # Для КФХ адрес берём строго из блока должника по первому "индекс + строка"
                    kfh_addr_match = re.search(r"([0-9]{6}[,\s]+[А-ЯЁ][^\n\r]+)", debtor_block)
                    if kfh_addr_match:
                        addr = self.clean_extracted_value(kfh_addr_match.group(1))
                        # Обрезаем всё после маркеров ИНН/ОГРН, если они попали в строку
                        for token in ["инн", "огрн", "кпп", "телефон", "e-mail", "email"]:
                            token_lower = token.lower()
                            idx = addr.lower().find(token_lower)
                            if idx != -1:
                                addr = addr[:idx].strip()
                        extracted_fields["applicantAddress"] = addr.strip()
        return debtor_block

    def _extract_multiline_address_from_block(self, block_text: str) -> Optional[str]:
        """
        Извлекает многострочный адрес после "адрес регистрации/место жительства/адрес прописки"
        с продолжением на следующих строках до служебных маркеров.
        """
        if not block_text:
            return None

        lines = [ln.strip() for ln in re.split(r"[\r\n]+", block_text) if ln.strip()]
        if not lines:
            return None

        start_idx = -1
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if any(k in lower_line for k in ["место жительства", "адрес регистрации", "адрес прописки"]):
                start_idx = i
                break

        if start_idx == -1:
            return None

        stop_tokens = [
            "инн", "огрн", "огрнип", "кпп", "телефон", "e-mail", "email",
            "дата рождения", "место рождения", "представитель", "заявление",
            "исковое", "просит суд"
        ]

        addr_parts: List[str] = []

        # 1) берем хвост текущей строки после двоеточия
        first_line = lines[start_idx]
        first_part = re.sub(
            r"^(?:место\s+жительства|адрес\s+регистрации|адрес\s+прописки)\s*:?\s*",
            "",
            first_line,
            flags=re.IGNORECASE
        ).strip(" ,.;:-")
        if first_part:
            addr_parts.append(first_part)

        # 2) добавляем следующие строки, пока не встретили служебные маркеры
        for next_line in lines[start_idx + 1:start_idx + 8]:
            lower_next = next_line.lower()
            if any(token in lower_next for token in stop_tokens):
                break
            cleaned = next_line.strip(" ,.;:-")
            if cleaned:
                addr_parts.append(cleaned)

        if not addr_parts:
            return None

        normalized = ", ".join(addr_parts)
        normalized = re.sub(r"\s+", " ", normalized).strip(" ,.;:-")
        return normalized or None

    # Маркеры, после которых адрес заведомо закончился (реквизиты/новые секции).
    _ADDR_STOP_TOKENS = [
        "инн", "огрн", "огрнип", "кпп", "снилс", "паспорт", "телефон",
        "e-mail", "email", "дата рождения", "место рождения", "д.р", "д/р",
        "представитель", "финансовый управляющий", "временный управляющий",
        "арбитражный управляющий", "конкурсный управляющий", "заявление",
        "исковое", "просит суд", "размер требований", "сумма требований",
        "цена иска", "госпошлина", "заинтересованные лица", "заинтересованное лицо",
        "третьи лица", "третье лицо", "третьих лиц", "заявитель",
        "на №", "о направлении", "заемщик", "заёмщик",
    ]

    def _collect_block_address(self, block_text):
        """Единый надёжный сбор адреса должника из его блока.

        1) ищет метку адреса (юридический адрес / адрес регистрации / место
           нахождения / место жительства / адрес прописки / просто «адрес»),
           берёт хвост строки ПОСЛЕ метки (отсекая префикс ОГРН/ИНН, если метка
           стоит в середине строки), и отбрасывает «прилипшие» служебные слова;
        2) если метки нет — стартует с «голой» строки, начинающейся с индекса (6 цифр);
        3) добавляет последующие строки до служебного маркера/пустой строки,
           обрезая строку по первому встреченному маркеру; строки склеиваются
           ПРОБЕЛОМ (сохраняет точки «д.», «ЗД.» и не плодит ложные запятые).
        """
        if not block_text:
            return None
        block_text = block_text.replace(" ", " ").replace("\xa0", " ")
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", block_text)]

        # Метки адреса; зазор между словами необязателен (бывает «Адресрегистрации:»).
        label_re = re.compile(
            r"(?:юридическ\w*\s*адрес|адрес\w*\s*регистрации|адрес\w*\s*прописки|"
            r"адрес\s*мест\w*\s*нахождени\w*|мест\w*\s*нахождени\w*|"
            r"мест\w*\s*жительства|адрес)\s*:?\s*",
            re.IGNORECASE,
        )
        # Прилипшие служебные слова в начале хвоста (когда сработала голая метка «адрес»).
        lead_junk_re = re.compile(
            r"^\s*(?:регистрации|прописки|нахождения|жительства|"
            r"мест\w*\s*нахождени\w*|мест\w*\s*жительства)\s*:?\s*",
            re.IGNORECASE,
        )

        def cut_at_stop(s):
            """(строка_до_первого_маркера, встретился_ли_маркер). Точки сохраняем."""
            s = re.sub(r"\[[0-9.]+\]", "", s)
            low = s.lower()
            idxs = [low.find(t) for t in self._ADDR_STOP_TOKENS if low.find(t) != -1]
            if idxs:
                return s[:min(idxs)].strip(" ,;:\t"), True
            return s.strip(" ,;:\t"), False

        start_idx, first_tail = -1, ""
        for i, line in enumerate(lines):
            for m in label_re.finditer(line):
                tail = line[m.end():]
                # Отрезаем повторные/вложенные ярлыки и прилипшие служебные слова.
                prev = None
                while prev != tail:
                    prev = tail
                    mm = label_re.match(tail)
                    if mm:
                        tail = tail[mm.end():]
                    tail = lead_junk_re.sub("", tail)
                tc, _ = cut_at_stop(tail)
                if tc:
                    start_idx, first_tail = i, tail
                    break
            if start_idx != -1:
                break
        if start_idx == -1:
            for i, line in enumerate(lines):
                if re.match(r"^\d{6}[,\s]", line):
                    start_idx, first_tail = i, line
                    break
        if start_idx == -1:
            return None

        parts = []
        tail_clean, stopped = cut_at_stop(first_tail)
        if tail_clean:
            parts.append(tail_clean)
        if not stopped:
            for nxt in lines[start_idx + 1:start_idx + 7]:
                if not nxt:
                    break
                cleaned, stopped = cut_at_stop(nxt)
                if not cleaned:
                    break
                parts.append(cleaned)
                if stopped:
                    break
        if not parts:
            return None
        addr = " ".join(parts)                      # склейка строк пробелом
        addr = re.sub(r"\s+", " ", addr)
        addr = re.sub(r"(?:\s*,\s*){2,}", ", ", addr)   # «,,» / «, ,» -> «, »
        addr = re.sub(r"\s*,\s*", ", ", addr).strip(" ,;:\t")
        return addr or None

    def _finalize_debtor_person_requisites(self, extracted_fields, text):
        """Авторитетные реквизиты должника-физлица из его записи (дата/место 
           рождения, ИНН, ОГРН/ОГРНИП, СНИЛС). Возвращает details для последующего 
           dedup. Вынесено из analyze."""
        details = extract_debtor_details(text)
        # birthDate авторитетно из записи должника: если валидной даты там нет,
        # очищаем мусор существующего фолбэка (невозможные/фабрикованные даты).
        if details.get("birthDate"):
            extracted_fields["birthDate"] = details["birthDate"]
        else:
            extracted_fields.pop("birthDate", None)
        if details.get("birthPlace"):
            extracted_fields["birthPlace"] = details["birthPlace"]
        # ИНН должника — авторитетно из его записи (исправляет подстановку ИНН банка).
        if details.get("inn"):
            extracted_fields["inn"] = details["inn"]
            extracted_fields["companyInn"] = details["inn"]
        # ОГРН/ОГРНИП должника — авторитетно из его записи.
        if details.get("ogrn"):
            if len(details["ogrn"]) == 15:
                extracted_fields["ogrnip"] = details["ogrn"]
            else:
                extracted_fields["ogrn"] = details["ogrn"]
        # СНИЛС берём строго из записи основного должника. Если там его нет —
        # очищаем значение, утёкшее от представителя/со-ответчика.
        if details.get("snils"):
            extracted_fields["snils"] = details["snils"]
        else:
            extracted_fields.pop("snils", None)
        return details

    def _finalize_debtor_type(self, extracted_fields, text, debtor_clean):
        """Финализация типа должника и финуправляющего: entityType, ОПФ в applicantName для ЮЛ, ИНН управляющего в ФИО, коррекция типа для наблюдения, фолбэк [3]. Вынесено из extract_fields."""
        detected_entity_type = self.detect_entity_type(extracted_fields)
        if detected_entity_type:
            extracted_fields['entityType'] = detected_entity_type
            logger.info(f"Определён тип должника: {detected_entity_type}")
            if detected_entity_type == "legal":
                # Для юрлиц: legalShortName и debtorName могут быть без ОПФ, но applicantName должен сохранять ОПФ для маркеров [2], [2.1], [2.2]
                name_source_legal = debtor_clean or extracted_fields.get("debtorName") or extracted_fields.get("applicantName")
                if name_source_legal:
                    short_legal_name = self._strip_ooo_prefix(name_source_legal)
                    if short_legal_name:
                        extracted_fields["debtorName"] = short_legal_name
                        # applicantName НЕ перезаписываем здесь, чтобы сохранить ОПФ для маркеров [2], [2.1], [2.2]
                        # Если applicantName еще не установлен, используем исходное значение с ОПФ
                        if not extracted_fields.get("applicantName"):
                            extracted_fields["applicantName"] = name_source_legal
                        extracted_fields["legalShortName"] = short_legal_name
                        debtor_clean = short_legal_name

                # Для ЮЛ дата рождения не применяется (иначе сюда ошибочно попадает ОГРН).
                extracted_fields.pop("birthDate", None)
                extracted_fields.pop("birthPlace", None)

                # ВАЖНО: Используем inn в первую очередь, так как он извлечен из блока "Ответчик:"
                # companyInn может быть неправильным (из кредитора), если он был установлен до специальной логики
                inn_clean = extracted_fields.get("inn") or extracted_fields.get("companyInn")
                if inn_clean:
                    inn_clean = re.sub(r"\D", "", inn_clean)
                    # Проверяем длину ИНН перед установкой
                    if len(inn_clean) >= 10 and len(inn_clean) <= 12:
                        extracted_fields["inn"] = inn_clean
                        extracted_fields["companyInn"] = inn_clean
                    else:
                        logger.warning(f" ИНН не прошел проверку длины при перезаписи: '{inn_clean}' (длина: {len(inn_clean)})")

                extracted_fields.pop("snils", None)

                extracted_fields['procedureType'] = 'observation'
                extracted_fields.setdefault('procedureTypeRaw', 'наблюдение')

                # Для ЮЛ добавляем ИНН в отображаемое ФИО финансового управляющего (для актов и интерфейса)
                manager_name = extracted_fields.get("managerName")
                manager_inn_final = extracted_fields.get("managerInn")
                if manager_name and manager_inn_final and "инн" not in manager_name.lower():
                    extracted_fields["managerName"] = f"{manager_name.strip()} (ИНН {manager_inn_final})"
            elif detected_entity_type in ("individual", "ip"):
                extracted_fields.pop("ogrn", None)
                extracted_fields.pop("companyInn", None)
            elif detected_entity_type == "kfh":
                # КФХ — не юрлицо, очищаем ОГРН/ИНН организации при необходимости
                extracted_fields.pop("companyInn", None)

        # Дополнительная коррекция типа должника для процедур наблюдения:
        # принудительно ЮЛ только если есть признаки ЮЛ и имя должника НЕ похоже на ФИО (используем только debtorName/applicantName как в detect_entity_type).
        procedure_type_final = (extracted_fields.get("procedureType") or "").lower()
        if procedure_type_final == "observation":
            current_entity = (extracted_fields.get("entityType") or "").lower()
            name_for_entity = (extracted_fields.get("debtorName") or "").strip() or (extracted_fields.get("applicantName") or "").strip()
            name_looks_like_fio = bool(re.search(r"[А-ЯЁа-яё]{2,}\s+[А-ЯЁа-яё]{2,}\s+[А-ЯЁа-яё]{2,}", name_for_entity))
            legal_tokens_in_name = any(t in name_for_entity.lower() for t in ["ооо", "оао", "пао", "зао", "общество с ограниченной", "акционерное общество"])
            if current_entity not in ("kfh", "ip") and (extracted_fields.get("ogrn") or extracted_fields.get("legalShortName") or extracted_fields.get("companyInn")) and not (name_looks_like_fio and not legal_tokens_in_name):
                extracted_fields["entityType"] = "legal"

        # Если на более поздних этапах (например, для competition_collateral) тип явно проставили как legal,
        # добавляем ИНН в отображаемое ФИО финансового управляющего
        final_entity_type = extracted_fields.get("entityType")
        if final_entity_type == "legal":
            manager_name_final = extracted_fields.get("managerName")
            manager_inn_final = extracted_fields.get("managerInn")
            if manager_name_final and manager_inn_final and "инн" not in manager_name_final.lower():
                extracted_fields["managerName"] = f"{manager_name_final.strip()} (ИНН {manager_inn_final})"

        # Фолбэк для [3] допустим только для не-ЮЛ.
        if extracted_fields.get("entityType") != "legal":
            if extracted_fields.get("ogrn") and not extracted_fields.get("birthDate"):
                extracted_fields["birthDate"] = extracted_fields["ogrn"]

    def _resolve_debtor_address(self, extracted_fields, text, debtor_block):
        """Валидация и фолбэки адреса должника: адрес != кредитор/суд, повторное извлечение из шапки (РТК) и из блока должника (КФХ). Вынесено из extract_fields."""
        # Адрес должника не должен совпадать с адресом кредитора (частая ошибка извлечения)
        applicant_addr = (extracted_fields.get("applicantAddress") or "").strip()
        creditor_addr = (extracted_fields.get("creditorAddress") or "").strip()
        if applicant_addr and creditor_addr and applicant_addr == creditor_addr:
            extracted_fields.pop("applicantAddress", None)
            logger.warning(" Адрес заявителя совпадал с адресом кредитора — поле очищено")

        # Адрес должника не должен быть названием/адресом суда (индекс + "Арбитражный суд ... области")
        if extracted_fields.get("applicantAddress"):
            addr = (extracted_fields.get("applicantAddress") or "").strip()
            if "Арбитражный суд" in addr or (re.search(r"\bсуд\b", addr) and "области" in addr):
                extracted_fields.pop("applicantAddress", None)
                logger.warning(" Адрес заявителя совпадал с названием/адресом суда — поле очищено")

        # Специальный fallback по заявлениям РТК:
        # если адрес пустой или был очищен как адрес суда/кредитора — пробуем ещё раз взять его из блока "Должник: Адрес ..."
        if not extracted_fields.get("applicantAddress"):
            # Ищем адрес в шапке заявления после блока "Должник ... Адрес"
            debtor_address_match = re.search(
                r"Должник[:\s][\s\S]{0,400}?Адрес[:\s]*([^\n]+(?:\n[^\n]+)?)",
                text,
                re.IGNORECASE
            )
            if debtor_address_match:
                raw_addr = debtor_address_match.group(1).strip()
                # Убираем служебные слова "регистрации", "место жительства" в начале
                raw_addr = re.sub(
                    r'^(адрес|адрес\s+регистрации|регистрации|место\s+жительства|место\s+регистрации)\s*[:\-–—]*\s*',
                    '',
                    raw_addr,
                    flags=re.IGNORECASE
                )
                # Заменяем переводы строк на запятую и пробел
                raw_addr = re.sub(r"\s*\n\s*", ", ", raw_addr)
                # Оставляем только буквы, цифры, точки, запятые, дефисы и пробелы
                cleaned_addr = re.sub(r"[^0-9,\s\-а-яёА-ЯЁ\.]+", "", raw_addr)
                cleaned_addr = re.sub(r"\s+", " ", cleaned_addr).strip(" ,")

                if cleaned_addr and "Арбитражный суд" not in cleaned_addr:
                    extracted_fields["applicantAddress"] = cleaned_addr
                    logger.info(f" Адрес должника (fallback из блока 'Должник: Адрес'): {cleaned_addr}")

        # Фолбэк: «зарегистрирован(а) по адресу: 346404,…» в теле документа
        # (ФНС-банкротство — адрес должника не в блоке «Должник:», а в тексте).
        if not extracted_fields.get("applicantAddress"):
            reg = re.search(
                r"зарегистрирован\w*\s+по\s+адресу[:\s]*([0-9]{6}[^\n;]+)",
                text, re.IGNORECASE,
            )
            if reg:
                addr = re.sub(r"(?:\s*,\s*)+", ", ", reg.group(1))   # двойные/пустые запятые
                addr = re.sub(r"\s+", " ", addr).strip(" ,;.")
                if addr and re.search(r"[А-ЯЁа-яё]", addr):
                    extracted_fields["applicantAddress"] = addr
                    logger.info(f" Адрес должника (fallback 'зарегистрирован по адресу'): {addr}")

        # Для КФХ: если адрес не найден, извлекаем его из текста документа
        if extracted_fields.get("isKfh") and not extracted_fields.get("applicantAddress"):
            # Ищем адрес в тексте после "Адрес:" или в блоке должника
            kfh_addr_patterns = [
                r"Адрес[:\s]+([0-9]{6}[,\s]+[А-ЯЁ][^\n]+?)(?=\n|$|ИНН|ОГРН|ОГРНИП|телефон|e-mail)",
                r"адрес[:\s]+([0-9]{6}[,\s]+[А-ЯЁ][^\n]+?)(?=\n|$|ИНН|ОГРН|ОГРНИП|телефон|e-mail)",
                r"место\s+жительства[:\s]+([0-9]{6}[,\s]+[А-ЯЁ][^\n]+?)(?=\n|$|ИНН|ОГРН|ОГРНИП|телефон|e-mail)",
                r"адрес\s+регистрации[:\s]+([0-9]{6}[,\s]+[А-ЯЁ][^\n]+?)(?=\n|$|ИНН|ОГРН|ОГРНИП|телефон|e-mail)",
            ]

            # Также ищем в блоке должника, если он есть
            debtor_block_for_kfh = None
            if debtor_block:
                debtor_block_for_kfh = debtor_block
            else:
                # Пытаемся найти блок должника в тексте
                debtor_block_match = re.search(
                    r"должник[:\s]+([^\n]+(?:\n[^\n]+){0,10}?)(?=\n\s*\n|ПРОСИТ|Сумма|Дело|$)",
                    text,
                    re.IGNORECASE | re.MULTILINE
                )
                if debtor_block_match:
                    debtor_block_for_kfh = debtor_block_match.group(0)

            for pattern in kfh_addr_patterns:
                if debtor_block_for_kfh:
                    match = re.search(pattern, debtor_block_for_kfh, re.IGNORECASE)
                else:
                    match = re.search(pattern, text, re.IGNORECASE)

                if match:
                    addr = self.clean_extracted_value(match.group(1))
                    # Обрезаем всё после маркеров ИНН/ОГРН, если они попали в строку
                    for token in ["инн", "огрн", "огрнип", "кпп", "телефон", "e-mail", "email"]:
                        token_lower = token.lower()
                        idx = addr.lower().find(token_lower)
                        if idx != -1:
                            addr = addr[:idx].strip()
                    # Проверяем, что адрес содержит буквы
                    if addr and re.search(r'[А-ЯЁа-яё]', addr):
                        extracted_fields["applicantAddress"] = addr.strip()
                        logger.info(f" Адрес КФХ извлечен: {addr.strip()}")
                        break

    def _reconcile_applicant_is_debtor(self, extracted_fields, text):
        """Исправляет «своп сторон»: applicantName (поле должника, маркер [2]) ошибочно
        равен КРЕДИТОРУ. Частая ошибка на раскладках с меткой «Заявитель:» перед
        «Должник:» (другие банки): позиционный паттерн цепляет кредитора в должника.

        Гвард (срабатывает ТОЛЬКО при явном свопе, иначе не трогаем):
          applicantName == creditorName  И  есть валидное иное имя должника
          (debtorName/legalShortName из блока «Должник:», отличное от кредитора).
        Тогда восстанавливаем applicantName из имени должника и пересобираем падежи
        (ЮЛ — как есть; ФЛ — склоняем через _convert_name_to_*).
        """
        def _norm(s: str) -> str:
            s = re.sub(r'[«»"\'\s]', '', (s or '').lower())
            s = re.sub(r'^(ип|ооо|оао|пао|зао|ао)', '', s)
            return s

        applicant = extracted_fields.get("applicantName")
        creditor = extracted_fields.get("creditorName")
        if not applicant or not creditor:
            return
        if _norm(applicant) != _norm(creditor):
            return  # свопа нет — applicantName не равен кредитору

        debtor = (extracted_fields.get("debtorName")
                  or extracted_fields.get("legalShortName") or "").strip()
        if not debtor or _norm(debtor) == _norm(creditor):
            return  # нет валидного иного должника — не трогаем, чтобы не навредить

        entity_type = (extracted_fields.get("entityType") or "").lower()
        display_name = debtor
        if entity_type == "legal":
            core = re.escape(re.sub(r'[«»"]', '', debtor).strip())
            mm = re.search(r"(?:ООО|ОАО|ПАО|ЗАО|АО)\s*«?" + core + r"»?", text, re.IGNORECASE)
            if not mm:
                mm = re.search(
                    r"Обществ\w*\s+с\s+ограниченной\s+ответственностью\s*«?" + core + r"»?",
                    text, re.IGNORECASE,
                )
            if mm:
                display_name = re.sub(r"\s+", " ", mm.group(0)).strip()

        extracted_fields["applicantName"] = display_name
        if entity_type == "legal":
            # Организации пословно не склоняем — все падежи равны наименованию.
            for k in ("applicantNameGenitive", "applicantNameDative",
                      "applicantNameInstrumental", "applicantNameAccusative"):
                extracted_fields[k] = display_name
        else:
            for key, conv in (
                ("applicantNameGenitive", self._convert_name_to_genitive),
                ("applicantNameDative", self._convert_name_to_dative),
                ("applicantNameInstrumental", self._convert_name_to_instrumental),
                ("applicantNameAccusative", self._convert_name_to_accusative),
            ):
                val = conv(debtor)
                if val:
                    extracted_fields[key] = val
        logger.info(f" Своп сторон исправлен: applicantName был кредитором, восстановлен должник: {debtor!r}")

    def _cleanup_party_artifacts(self, extracted_fields, text):
        """Косметическая пост-очистка артефактов извлечения сторон (гвардированно):
          1. Роль-суффикс «(заёмщик)»/«(должник)» в конце наименования/ФИО — срезаем.
          2. courtName с прилипшей хвостовой меткой соседнего блока («…области Заявитель») — обрезаем.
          3. managerName, не похожий на ФИО (мусорная фраза «из числа членов…») — удаляем.
        Все правки строго локальные и условные, чтобы не задеть корректные значения.
        """
        # 1. Роль-суффикс в скобках в конце имени/наименования.
        role_suffix = re.compile(
            r'\s*\(\s*(?:заёмщик|заемщик|должник|ответчик|кредитор|истец|взыскатель)\s*\)\s*$',
            re.IGNORECASE,
        )
        for k in ("applicantName", "debtorName", "legalShortName", "creditorName"):
            v = extracted_fields.get(k)
            if isinstance(v, str) and v:
                nv = role_suffix.sub("", v).strip()
                if nv and nv != v:
                    extracted_fields[k] = nv
                    logger.info(f" Срезан роль-суффикс в {k}: '{v}' -> '{nv}'")

        # 2. courtName: обрезаем всё начиная с прилипшей метки соседнего блока.
        cn = extracted_fields.get("courtName")
        if isinstance(cn, str) and cn:
            cut = re.split(
                r'\s+(?:Заявител[ья]|Должник|Ответчик|Истец|Кредитор|Взыскатель|Заинтересованн|Адрес)\b',
                cn, maxsplit=1,
            )[0].strip(" ,")
            # Название суда заканчивается обозначением региона; всё после (улица/индекс)
            # — прилипший адрес суда, отсекаем («…области Станиславского» -> «…области»).
            mreg = re.match(
                r'(.*?\b(?:област[ьи]|кра[йя]|округа?|города?\s+[А-ЯЁ][А-Яа-яёЁ-]+|'
                r'[Рр]еспублик\w*(?:\s+[А-ЯЁ][А-Яа-яёЁ-]+)?))\b',
                cut,
            )
            if mreg:
                cut = mreg.group(1).strip(" ,")
            if cut and cut != cn:
                extracted_fields["courtName"] = cut
                logger.info(f" Обрезан хвост метки в courtName: '{cn}' -> '{cut}'")

        # 3. managerName: должно быть ФИО (два слова с заглавных). Иначе — мусор, удаляем.
        mn = extracted_fields.get("managerName")
        if isinstance(mn, str) and mn.strip():
            looks_like_fio = bool(re.search(r'[А-ЯЁ][А-Яа-яёЁ.\-]+\s+[А-ЯЁ]', mn))
            if not looks_like_fio:
                extracted_fields.pop("managerName", None)
                logger.info(f"Удалён мусорный managerName (не ФИО): '{mn}'")
        # 3a. Нет ФИО управляющего, а его «ИНН» совпал с ИНН/ОГРН должника это
        #     утёкшие реквизиты должника (пункт «определить СРО … случайным выбором»),
        #     а не реальный управляющий. Чистим. Если ИНН иной — это может быть реальный
        #     управляющий, чьё ФИО не извлеклось; не трогаем, чтобы не потерять данные.
        if not (extracted_fields.get("managerName") or "").strip():
            _d = lambda v: re.sub(r"\D", "", str(v or ""))
            _mi = _d(extracted_fields.get("managerInn"))
            if _mi and _mi in (_d(extracted_fields.get("inn")), _d(extracted_fields.get("ogrn")),
                               _d(extracted_fields.get("companyInn"))):
                for _mk in ("managerInn", "managerAddress", "managerSnils"):
                    extracted_fields.pop(_mk, None)

        # 4. Адрес должника: обрезать «прилипший» хвост после адреса (суммы/реквизиты/
        #    служебные блоки), напр. «…КОМ. 16 Размер требований 2 789 060,93 руб.».
        addr = extracted_fields.get("applicantAddress")
        if isinstance(addr, str) and addr.strip():
            cut = re.split(
                r'\s+(?:Размер\s+требований|Сумма\s+требований|Госпошлина|Государственн\w+\s+пошлин\w+|'
                r'Паспорт|Дата\s+рождения|Дата\s+государственн\w+|Представитель|Телефон|тел\.|'
                r'e-?mail|ЗАЯВЛЕНИЕ|ОГРНИП|ОГРН|ИНН|КПП|СНИЛС|Почтовый\s+адрес|'
                r'Адрес\s+для\s+(?:направлен\w+|корреспонден\w+))\b',
                addr, maxsplit=1, flags=re.IGNORECASE,
            )[0].rstrip(" ,;")
            looks_addr = bool(re.search(
                r'облас|город|\bг\.|улиц|\bул\.|переул|проспект|посёл|посел|район|деревн|слобод|\bш\.|шоссе',
                cut, re.IGNORECASE,
            ))
            if cut and cut != addr and looks_addr:
                extracted_fields["applicantAddress"] = cut
                logger.info(f" Обрезан хвост в адресе должника: '{addr}' -> '{cut}'")

        if not (extracted_fields.get("creditorName") or "").strip():
            cn = self._extract_creditor_name_from_text(text)
            if cn:
                extracted_fields["creditorName"] = cn
                logger.info(f" creditorName из текста (фолбэк по метке): '{cn}'")

        if (extracted_fields.get("entityType") or "").lower() == "ip":
            base = (extracted_fields.get("applicantName") or extracted_fields.get("debtorName") or "").strip()
            already = re.match(r"^\s*ИП\b", base, re.IGNORECASE)
            if base and not already and re.search(r"\bИП\s+" + re.escape(base), text, re.IGNORECASE):
                for k in ("applicantName", "debtorName",
                          "applicantNameGenitive", "applicantNameDative",
                          "applicantNameInstrumental", "applicantNameAccusative"):
                    v = extracted_fields.get(k)
                    if isinstance(v, str) and v.strip() and not re.match(r"^\s*ИП\b", v, re.IGNORECASE):
                        extracted_fields[k] = "ИП " + v.strip()
                logger.info(f" Восстановлен префикс «ИП» в наименовании должника: 'ИП {base}'")

        # 7. Достройка наименования ЮЛ: раскладка «Должник Общество с ограниченной
        #    ответственностью\n«Имя»» даёт обрезанное имя без кавычек. Берём полное
        #    «<ОПФ> «Имя»» из блока должника.
        if (extracted_fields.get("entityType") or "").lower() == "legal":
            an = (extracted_fields.get("applicantName") or "").strip()
            # Достраиваем ТОЛЬКО когда имя без кавычек вообще («Спн Трак»); если кавычки
            # уже есть (в т.ч. прямые/множественные, как «АО "КОНЦЕРН "САРМАТ"») — не трогаем.
            if "«" not in an and '"' not in an:
                # Кавычки названия — «ёлочки» ИЛИ прямые ("СПН ТРАК"); нормализуем в «».
                m = re.search(
                    r"Должник[:\s][\s\S]{0,80}?"
                    r"((?:Обществ\w+\s+с\s+ограниченной\s+ответственностью|ООО|ОАО|ПАО|ЗАО|АО)"
                    r"\s*\n?\s*[«\"]\s*[^»\"\n]+\s*[»\"])",
                    text, re.IGNORECASE,
                )
                if m:
                    full = re.sub(r"\s+", " ", m.group(1)).strip()
                    # Прямые кавычки -> «ёлочки»: первая " -> «, остальные " -> ».
                    if '"' in full:
                        full = full.replace('"', "«", 1).replace('"', "»")
                    extracted_fields["applicantName"] = full
                    extracted_fields["debtorName"] = full
                    logger.info(f" Достроено наименование ЮЛ должника: '{full}'")

    def _tune_legal_entity_naming(self, extracted_fields, text, debtor_clean, applicant_clean, applicant_name_raw, debtor_block, debtor_name_raw):
        """Короткое наименование ЮЛ (legalShortName) и донастройка для initiation_legal: переустановка applicantName с ОПФ из блока «Должник:», адрес из шапки. Возвращает обновлённый debtor_clean. Вынесено из extract_fields."""
        # Для юрлиц пытаемся получить короткое название. Игнорируем мусорные значения вроде "введена процедура наблюдения".
        legal_name_source = debtor_clean or applicant_clean or debtor_block or applicant_name_raw or debtor_name_raw
        if legal_name_source and re.search(r"введена\s+процедура\s+наблюдения", legal_name_source, re.IGNORECASE):
            legal_name_source = applicant_clean or applicant_name_raw or debtor_block

        legal_short_name = self.extract_legal_entity_short_name(legal_name_source)
        if legal_short_name:
            extracted_fields["legalShortName"] = legal_short_name

        # Специальная донастройка ТОЛЬКО для юр. инициирования
        source_doc_type = (extracted_fields.get("sourceDocumentType") or "").lower()
        if source_doc_type.startswith("initiation_legal"):
            # Для заявлений о инициировании банкротства ЮЛ берём название должника строго из блока "Должник:"
            if debtor_block:
                # Полное наименование организации из шапки
                company_match = re.search(
                    r"(?:ООО|ОАО|ПАО|ЗАО|АО|Обществ[ао]\s+с\s+ограниченной\s+ответственностью)\s*[«\"]?([^\"\n]+)[»\"]?",
                    debtor_block,
                    re.IGNORECASE,
                )
                if company_match:
                    short_name = company_match.group(1).strip()
                    # company_match.group(0) содержит форму с организационно‑правовой формой
                    full_name = company_match.group(0).strip(' «»"')

                    # Для маркеров [2], [2.1], [2.2] applicantName должен содержать ОПФ
                    # debtorName и legalShortName могут быть без ОПФ
                    name_core = short_name or full_name
                    extracted_fields["debtorName"] = name_core
                    # applicantName сохраняем с ОПФ для маркеров [2], [2.1], [2.2]
                    extracted_fields["applicantName"] = full_name if full_name else name_core
                    extracted_fields["legalShortName"] = name_core
                    debtor_clean = name_core

        address_raw = extracted_fields.get("applicantAddress")
        if address_raw:
            address_clean = self.clean_extracted_value(address_raw.replace('\u202f', ' ').replace('\xa0', ' '))
            address_clean = re.sub(r"\[[0-9\.]+\]", "", address_clean)
            for token in [
                "почтовый адрес", "телефон", "e-mail", "инн", "огрн", "кпп",
                "банк", "банковских", "сбербанк", "банк россии",
                "исковое заявление", "о взыскании", "просит суд", "цена иска"
            ]:
                token_lower = token.lower()
                idx = address_clean.lower().find(token_lower)
                if idx != -1:
                    address_clean = address_clean[:idx].strip()
            # Проверка: адрес не должен быть только цифрами (ИНН, ОГРН и т.д.)
            # Адрес должен содержать буквы (область, город, улица)
            address_clean_stripped = address_clean.strip()
            # Если адрес состоит только из цифр, пробелов и знаков препинания - это не адрес
            if address_clean_stripped and not re.search(r'[А-ЯЁа-яё]', address_clean_stripped):
                # Это не адрес, скорее всего ИНН или другой номер
                logger.warning(f"Адрес содержит только цифры, удаляем: {address_clean_stripped}")
                extracted_fields.pop("applicantAddress", None)
            else:
                extracted_fields["applicantAddress"] = address_clean_stripped
        return debtor_clean

    def _cleanup_extracted_fields(self, extracted_fields, text):
        """Пост-очистка извлечённых полей: срез метки из адреса должника, 
           валидация имени/реквизитов третьего лица, фолбэк и нормализация 
           названия суда. Вынесено из analyze."""
        _digits = lambda v: re.sub(r"\D", "", str(v or ""))
        _mgr_name = (extracted_fields.get("managerName") or "").strip()
        _mgr_real = bool(re.search(r"[А-ЯЁ][А-Яа-яёЁ.\-]+\s+[А-ЯЁ]", _mgr_name))
        mgr_inn = _digits(extracted_fields.get("managerInn")) if _mgr_real else ""
        if mgr_inn and _digits(extracted_fields.get("inn")) == mgr_inn:
            extracted_fields.pop("inn", None)
            extracted_fields.pop("companyInn", None)
        mgr_blk = re.search(
            r"(?:финансов|временн|конкурсн|арбитражн)\w+\s+управляющ[^\n]*\(([^)]*)\)",
            text, re.IGNORECASE,
        )
        if mgr_blk:
            ms = re.search(r"СНИЛС[:\s]*([\d \-]{11,16})", mgr_blk.group(1), re.IGNORECASE)
            if ms and _digits(ms.group(1)) and _digits(extracted_fields.get("snils")) == _digits(ms.group(1)):
                extracted_fields.pop("snils", None)

        # Баланс кавычек в наименованиях: ранние .strip(' «»"') срезают закрывающую
        # «»», когда ««» — внутренняя (ООО «Азбука» -> ООО «Азбука). Дописываем «»».
        for _nk in ("applicantName", "debtorName", "legalShortName",
                    "applicantNameGenitive", "applicantNameDative",
                    "applicantNameInstrumental", "applicantNameAccusative"):
            _v = extracted_fields.get(_nk)
            if not _v:
                continue
            # Одиночная прямая кавычка (ООО "ТМД — закрывающая срезана): «-> «…»».
            if _v.count('"') == 1:
                _v = _v.replace('"', "«") + "»"
                extracted_fields[_nk] = _v
            elif _v.count("«") > _v.count("»"):
                extracted_fields[_nk] = _v + "»"

        # Срезаем ведущую метку из адреса должника («Адрес регистрации: 867624…»
        # «867624…»), если она попала в значение при извлечении.
        addr_val = extracted_fields.get("applicantAddress")
        if addr_val:
            cleaned_addr = re.sub(
                r"^\s*(?:Адрес(?:\s+регистрации|\s+проживания|\s+места\s+жительства)?|"
                r"Место\s+(?:жительства|регистрации|нахождения)|"
                r"Зарегистрирован\w*(?:\s+по\s+адресу)?)\s*[:\-]?\s*",
                "", addr_val, flags=re.IGNORECASE,
            ).strip()
            if cleaned_addr:
                extracted_fields["applicantAddress"] = cleaned_addr

        # Валидация имени третьего лица: должно быть ФИО или организацией.
        # Иначе это мусор из тела (например, «и должник отвечают перед») — чистим блок.
        tp_name = extracted_fields.get("thirdPartyName")
        if tp_name:
            is_org = re.match(r"^(?:ИП|ООО|АО|ПАО|ЗАО|ОАО|Общество|Публичное)\b", tp_name, re.IGNORECASE)
            if not (is_person_name(tp_name) or is_org):
                for key in ("thirdPartyName", "thirdPartyAddress", "thirdPartyInn",
                            "thirdPartyBirthDate", "thirdPartySnils"):
                    extracted_fields.pop(key, None)
                tp_name = None

        # Реквизиты первого третьего лица (ИНН/дата рождения/СНИЛС), если блок валиден.
        if tp_name:
            tp = extract_third_party_details(text)
            for key in ("thirdPartyInn", "thirdPartyBirthDate", "thirdPartySnils"):
                if tp.get(key) and not extracted_fields.get(key):
                    extracted_fields[key] = tp[key]

        # Название суда: универсальный фолбэк, если не извлеклось основным путём
        # (ипотека/взыскание — суд общей юрисдикции, а не арбитраж).
        if not extracted_fields.get("courtName"):
            court = self._extract_court_name(text)
            if court:
                extracted_fields["courtName"] = court
        # Нормализуем регистр названия суда («…Суд… Области» «…суд… области»).
        if extracted_fields.get("courtName"):
            extracted_fields["courtName"] = self._normalize_court_name(extracted_fields["courtName"])

    def _resolve_debtors_and_third_parties(self, extracted_fields, text, details):
        """Разбор списков должников (со-ответчиков) и третьих лиц + кросс-блочный дедуп 
           реквизитов. Возвращает (debtors_result, third_parties_result). 
           Вынесено из analyze."""
        parsed_debtors = extract_debtors(text)
        # Третьи лица считаем заранее — их ИНН нужны для отсева кросс-контаминации
        # ИНН у одиночного должника (плоское поле могло взять ИНН третьего лица).
        parsed_tp = extract_third_parties(text)
        tp_ids = {p.get("inn") for p in parsed_tp if p.get("inn")}
        if len(parsed_debtors) >= 2:
            extracted_fields.update(self._combine_debtors(parsed_debtors))
            debtors_result = parsed_debtors
        else:
            single = self._single_debtor_from_fields(extracted_fields)
            # Восполняем поля из распознанной записи блока «Ответчик:/Должник:».
            # Плоский applicantAddress мог не извлечься, когда блок «Представитель
            # истца:» между Истцом и Ответчиком сбивает разбор адреса (ипотека);
            # паспорт разбирается только в записи блока, не в плоских полях.
            if len(parsed_debtors) == 1:
                rec = parsed_debtors[0]
                for k in ("address", "passportSeries", "passportNumber"):
                    if not single.get(k) and rec.get(k):
                        single[k] = rec[k]
                # ИНН: если плоский совпал с ИНН третьего лица (контаминация из-за
                # общей нормализации блоков), а запись блока даёт свой — берём из записи.
                if single.get("inn") in tp_ids and rec.get("inn") and rec["inn"] not in tp_ids:
                    single["inn"] = rec["inn"]
            debtors_result = [single]

        # Несколько третьих лиц: если извлеклись — отдаём как есть; иначе одно лицо
        # из плоских полей (если есть).
        if parsed_tp:
            third_parties_result = parsed_tp
        elif extracted_fields.get("thirdPartyName"):
            third_parties_result = [{
                "name": extracted_fields.get("thirdPartyName") or "",
                "address": extracted_fields.get("thirdPartyAddress") or "",
                "inn": extracted_fields.get("thirdPartyInn") or "",
                "birthDate": extracted_fields.get("thirdPartyBirthDate") or "",
                "snils": extracted_fields.get("thirdPartySnils") or "",
            }]
        else:
            third_parties_result = []

        # Кросс-блочный дедуп индивидуальных реквизитов: один ИНН/ОГРН/СНИЛС не
        # может принадлежать сразу должнику и третьему лицу/кредитору/управляющему.
        self._dedup_cross_block_ids(extracted_fields, details, third_parties_result)
        return debtors_result, third_parties_result

    def _combine_debtors(self, debtors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Склеивает реквизиты нескольких должников в плоские поля через запятую.

        Имя/адрес/ИНН/ОГРНИП/дата-место рождения/СНИЛС — join значений через ", ".
        Падежные формы — каждое имя склоняется через _convert_name_to_*, затем join.
        Для одного должника результат эквивалентен исходным плоским полям.
        """
        out: Dict[str, Any] = {}
        names = [d["name"] for d in debtors if d.get("name")]
        if names:
            out["applicantName"] = ", ".join(names)
            out["debtorName"] = out["applicantName"]

            def join_cases(converter) -> str:
                vals = []
                for n in names:
                    base = re.sub(self._NAME_PREFIX_RE, "", n, flags=re.IGNORECASE).strip()
                    inflected = None
                    if base:
                        try:
                            inflected = converter(base)
                        except Exception:
                            inflected = None
                    vals.append(inflected or n)
                return ", ".join(vals)

            out["applicantNameGenitive"] = join_cases(self._convert_name_to_genitive)
            out["applicantNameDative"] = join_cases(self._convert_name_to_dative)
            out["applicantNameAccusative"] = join_cases(self._convert_name_to_accusative)
            out["applicantNameInstrumental"] = join_cases(self._convert_name_to_instrumental)

        for src_key, flat_key in (
            ("address", "applicantAddress"),
            ("inn", "inn"),
            ("ogrn", "ogrn"),
            ("ogrnip", "ogrnip"),
            ("birthDate", "birthDate"),
            ("birthPlace", "birthPlace"),
            ("snils", "snils"),
        ):
            vals = [d[src_key] for d in debtors if d.get(src_key)]
            if vals:
                out[flat_key] = ", ".join(vals)
        if out.get("inn"):
            out["companyInn"] = out["inn"]
        return out

    def _single_debtor_from_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Собирает запись одного должника из плоских полей (для формы).

        Имя обычно берём из applicantName (самобанкротство: заявитель = должник). Но
        в кредиторских заявлениях (ФНС/банк/ООО) заявитель — это КРЕДИТОР, а должник
        лежит в debtorName; в таком случае имя/адрес должника берём из debtor* полей,
        иначе в блок должника утекает кредитор (ФНС)."""
        appl = fields.get("applicantName") or ""
        debt = fields.get("debtorName") or ""
        cred = fields.get("creditorName") or ""
        appl_is_creditor = bool(appl) and (appl == cred or bool(re.search(r"\bФНС\b", appl, re.IGNORECASE)))
        if debt and appl_is_creditor and debt != appl:
            name = debt
            # ВАЖНО: в кредиторском заявлении applicantAddress — адрес КРЕДИТОРА
            # (ФНС/банка), а не должника. Поэтому адрес должника берём ТОЛЬКО из
            # debtorAddress; если он не извлёкся — оставляем пустым, иначе должнику
            # подставится юр-адрес ФНС (напр. Чернов адрес инспекции в Уфе).
            address = fields.get("debtorAddress") or ""
        else:
            name = appl or debt
            address = fields.get("applicantAddress") or ""
        return {
            "name": name,
            "address": address,
            "inn": fields.get("inn") or fields.get("companyInn") or "",
            "ogrn": fields.get("ogrn") or "",
            "ogrnip": fields.get("ogrnip") or "",
            "birthDate": fields.get("birthDate") or "",
            "birthPlace": fields.get("birthPlace") or "",
            "snils": fields.get("snils") or "",
        }

    def _dedup_cross_block_ids(self, fields: Dict[str, Any], debtor_details: Dict[str, Any],
                               third_parties: List[Dict[str, Any]]) -> None:
        """Гарантирует, что один ИНН/ОГРН/СНИЛС не принадлежит сразу нескольким блокам.

        Если у должника проставлен ИНН/ОГРН/СНИЛС, которого НЕТ в его собственной
        записи (значит, он утёк), но он есть у третьего лица / кредитора / управляющего,
        то поле должника очищается. Так у должника с одним ФИО не появятся чужие реквизиты.
        """
        debtor_own = {str(debtor_details.get(k)) for k in ("inn", "ogrn", "snils") if debtor_details.get(k)}

        others = set()
        for tp in third_parties or []:
            for k in ("inn", "ogrn", "snils"):
                if tp.get(k):
                    others.add(str(tp[k]))
        for k in ("creditorInn", "creditorOgrn", "managerInn", "managerSnils"):
            if fields.get(k):
                others.add(str(fields[k]))

        for fld in ("inn", "companyInn", "ogrnip", "ogrn", "snils"):
            val = fields.get(fld)
            if val and str(val) not in debtor_own and str(val) in others:
                logger.info(f"Кросс-блочный дедуп: поле должника {fld}={val} принадлежит другому блоку — очищено")
                fields.pop(fld, None)

    def _fix_debtor_name(self, text: str, fields: Dict[str, Any]) -> None:
        """Заменяет некорректное ФИО должника на позиционно извлечённое и пересчитывает падежи.

        Срабатывает ТОЛЬКО если текущее applicantName/debtorName не похоже на ФИО
        физлица (организации и валидные имена не трогаем). Падежные формы
        пересчитываются лишь для тех ключей, что уже присутствовали.
        """
        current = fields.get("applicantName") or fields.get("debtorName")
        candidate = extract_debtor_name(text)
        _strip_ip = lambda s: re.sub(r"^\s*ип\s+", "", (s or ""), flags=re.IGNORECASE).strip()

        # Если блок «Должник:» даёт ТО ЖЕ лицо в иной (как-написано, именительной)
        # форме — предпочитаем форму из документа (совпадает фамилия, отличаются формы).
        same_person_other_form = False
        if current and candidate and is_person_name(current) and is_person_name(candidate):
            cs, ds = _strip_ip(current).split(), _strip_ip(candidate).split()
            if (cs and ds and cs[0].lower() == ds[0].lower()
                    and _strip_ip(current).lower() != _strip_ip(candidate).lower()):
                same_person_other_form = True
                candidate = _strip_ip(candidate)  # «ИП» восстановит шаг 6

        # Если уже валидное ФИО или это организация (детектор вернёт None) — выходим
        # (кроме случая, когда нашли ту же фамилию в иной форме из блока «Должник:»).
        if current and is_person_name(current) and not same_person_other_form:
            return

        if not candidate or not is_person_name(candidate):
            db = (fields.get("debtorName") or "").strip()
            entity = (fields.get("entityType") or "").lower()
            if (entity != "legal" and db and is_person_name(db)
                    and db != (fields.get("applicantName") or "")):
                candidate = db
            else:
                return

        logger.info(f"ФИО должника скорректировано: {current!r} -> {candidate!r}")
        fields["applicantName"] = candidate
        fields["debtorName"] = candidate

        # Для склонения убираем девичью фамилию в скобках — иначе она искажает
        # падежные формы (в самом ФИО скобки сохраняются).
        name_for_inflection = re.sub(r"\s*\([^)]*\)\s*", " ", candidate).strip()

        # Пересчитываем уже имеющиеся падежные формы по новому имени.
        converters = {
            "applicantNameGenitive": self._convert_name_to_genitive,
            "applicantNameDative": self._convert_name_to_dative,
            "applicantNameAccusative": self._convert_name_to_accusative,
            "applicantNameInstrumental": self._convert_name_to_instrumental,
        }
        for key, convert in converters.items():
            if key in fields:
                try:
                    inflected = convert(name_for_inflection)
                    if inflected:
                        fields[key] = inflected
                except Exception as exc:
                    logger.warning(f"Не удалось пересчитать {key}: {exc}")

    def _fill_creditor_requisites(self, fields: Dict[str, Any], text: str) -> None:
        """
        Заполняет creditorInn, creditorOgrn, creditorAddress.
        Если кредитор есть в реестре CREDITOR_BANKS — берёт данные из кода;
        иначе извлекает ИНН, ОГРН, адрес из блока кредитора в тексте.
        """
        creditor_name = (fields.get("creditorName") or "").strip()
        if not creditor_name or len(creditor_name) > 200:
            return
        matched = _match_creditor_registry(creditor_name)

        # Приоритет — данные из документа; реестр известных банков только как фолбэк,
        # когда в документе соответствующего реквизита нет.
        block = self._extract_creditor_block(text)
        doc_inn = doc_ogrn = None
        if block:
            # ВАЖНО: класс [0-9 ] (пробел, НЕ \s) — чтобы не «прихватить» цифру
            # с соседней строки через перенос и не получить лишний разряд.
            inn_m = re.search(r"ИНН[:\s]*([0-9 ]{9,13})", block, re.IGNORECASE)
            if inn_m:
                inn_clean = re.sub(r"\D", "", inn_m.group(1))
                if len(inn_clean) in (10, 12):  # ЮЛ=10, ИП/физлицо=12
                    doc_inn = inn_clean
            # ОГРН (13) и ОГРНИП (15) — строгая длина, поддержка обоих ярлыков.
            ogrn_m = re.search(r"ОГРН(?:ИП)?[:\s]*([0-9 ]{13,17})", block, re.IGNORECASE)
            if ogrn_m:
                ogrn_clean = re.sub(r"\D", "", ogrn_m.group(1))
                if len(ogrn_clean) in (13, 15):
                    doc_ogrn = ogrn_clean

        if not doc_inn or not doc_ogrn:
            pay = re.search(
                r"Реквизит\w*\s+для\s+перечислен\w+[^\n]*:\s*\n?\s*"
                r"ИНН[:\s]*([0-9]{10,12})[,\s]+ОГРН[:\s]*([0-9]{13,15})",
                text, re.IGNORECASE,
            )
            if pay:
                if not doc_inn and len(pay.group(1)) in (10, 12):
                    doc_inn = pay.group(1)
                if not doc_ogrn and len(pay.group(2)) in (13, 15):
                    doc_ogrn = pay.group(2)
        doc_addr = self._extract_creditor_address(text)

        inn = doc_inn or (matched["inn"] if matched else None)
        ogrn = doc_ogrn or (matched["ogrn"] if matched else None)
        addr = doc_addr or (matched["address"] if matched else None)
        provenance = fields.setdefault(self._PROVENANCE_KEY, {})
        for field_name, value, from_doc in (
            ("creditorInn", inn, doc_inn),
            ("creditorOgrn", ogrn, doc_ogrn),
            ("creditorAddress", addr, doc_addr),
        ):
            if not value:
                continue
            fields[field_name] = value
            provenance[field_name] = (
                field_contract.SOURCE_DOCUMENT if from_doc else field_contract.SOURCE_REGISTRY
            )
        logger.info(
            f"Реквизиты кредитора '{creditor_name[:40]}': "
            f"ИНН {'док' if doc_inn else 'реестр'}, "
            f"ОГРН {'док' if doc_ogrn else 'реестр'}, "
            f"адрес {'док' if doc_addr else 'реестр'}"
        )

    def _extract_court_name(self, text: str) -> Optional[str]:
        """Извлекает название ЛЮБОГО суда из текста (универсально, многословное).

        Построчный разбор: берёт целиком строку с упоминанием суда — так название
        из нескольких слов (город/регион, «города Санкт-Петербурга и Ленинградской
        области» и т.п.) сохраняется полностью. Поддерживает все типы судов РФ
        (районный/городской/межрайонный/областной/краевой/окружной/верховный/военный/
        гарнизонный/арбитражный/апелляционный/кассационный/конституционный), а также
        мирового судью и судебный участок.
        """
        court_line_re = re.compile(
            rf"(?:{self._COURT_KIND_RE}\s+суд(?:а|у|ом|е)?\b|"
            r"Судебн\w+\s+участ\w+\s+№|Мирово\w+\s+судь)",
            re.IGNORECASE,
        )
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # Сначала верхние строки (там адресуется суд), затем весь документ.
        for scope in (lines[:12], lines):
            for s in scope:
                if court_line_re.search(s):
                    name = self._clean_court_line(s)
                    if name:
                        return name
        return None

    def _normalize_court_name(self, name: str) -> str:
        """Приводит регистр названия суда: общие слова — строчными, имена собственные — как есть.

        Пример: «Арбитражный Суд Ростовской Области» «Арбитражный суд Ростовской области».
        """
        if not name:
            return name
        out = []
        for w in name.split():
            out.append(w.lower() if w.lower() in self._COURT_LOWER_WORDS else w)
        res = " ".join(out)
        return (res[0].upper() + res[1:]) if res else res

    def _clean_court_name_deceased(self, value: str) -> str:
        """Очищает название суда от лишнего текста специально для процедуры 'умерший'"""
        if not value:
            return value

        # Убираем слово "Возникает" и другие лишние слова
        stop_words = [
            "возникает",
            "у конкурсного",
            "по денежным",
            "обязательствам",
            "с даты",
            "вступления",
            "в законную",
            "силу",
            "решения",
            "суда",
            "арбитражного",
            "или",
            "третейского",
            "о взыскании",
            "с должника",
            "денежных",
            "средств"
        ]

        value_lower = value.lower()
        for stop_word in stop_words:
            if stop_word in value_lower:
                # Обрезаем текст до первого вхождения стоп-слова
                idx = value_lower.find(stop_word)
                value = value[:idx].strip()
                break

        # Ограничиваем длину названия суда (обычно не более 100 символов)
        if len(value) > 100:
            # Пытаемся найти естественную границу (точка, запятая, или конец предложения)
            for delimiter in ['.', ',', '\n']:
                idx = value.find(delimiter)
                if 20 < idx < 100:
                    value = value[:idx].strip()
                    break
            else:
                # Если не нашли естественную границу, просто обрезаем до 100 символов
                value = value[:100].strip()

        return value.strip()

