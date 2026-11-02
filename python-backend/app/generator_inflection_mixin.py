"""Регистр ФИО и подключение общего механизма склонения к генератору."""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class GeneratorInflectionMixin:
    def _capitalize_full_name(self, full_name: str) -> str:
        if not full_name:
            return full_name

        def _capitalize_token(token: str) -> str:
            if not token:
                return token
            if "-" in token:
                return "-".join(_capitalize_token(part) for part in token.split("-"))
            return token[:1].upper() + token[1:].lower()

        tokens = [token for token in re.split(r"\s+", full_name.strip()) if token]
        return " ".join(_capitalize_token(token) for token in tokens)

    def _decline_person_name(self, name: str, case: str) -> str:
        """Склонение отдельного ФИО через общий с анализатором механизм."""
        from morph_utils import get_name_morph, inflect_full_name, looks_like_fio

        src = self._capitalize_full_name((name or "").strip())
        if not src:
            return src
        morph = get_name_morph()
        if morph is None:
            return src
        if looks_like_fio(src.split()) or " в лице законного представителя " in src.lower():
            return inflect_full_name(morph, src, case)
        out = []
        for word in src.split():
            inflected = morph.parse(word)[0].inflect({case})
            out.append(inflected.word if inflected else word)
        return self._capitalize_full_name(" ".join(out))

    def _correct_applicant_cases(self, cleaned_data: Dict[str, Any]) -> None:
        """Падежи должника пересчитываются из актуального исходного ФИО."""
        from morph_utils import get_name_morph, refresh_debtor_case_forms

        for warning in refresh_debtor_case_forms(cleaned_data, get_name_morph()):
            logger.warning(warning)

    def _normalize_name_case(self, name: str) -> str:
        """
        Нормализует регистр имени: первая буква заглавная, остальные строчные.
        Для ИП префикс "ИП" остается заглавным.
        Примеры:
        - "РОМАНОВ ИВАН ЛЮДМИЛОВИЧ" -> "Романов Иван Людмилович"
        - "ИП РОМАНОВ ВАСИЛИЙ СЕРГЕЕВИЧ" -> "ИП Романов Василий Сергеевич"
        - "ип романов василий сергеевич" -> "ИП Романов Василий Сергеевич"
        """
        if not name:
            return name

        name = name.strip()

        # Проверяем наличие префикса "ИП" (может быть в разных регистрах)
        ip_prefix = ""
        remaining_name = name

        # Ищем префикс "ИП" в начале строки (может быть с пробелом или без)
        ip_match = re.match(r"^(ИП|ип|Ип)\s*(.+)$", name, re.IGNORECASE)
        if ip_match:
            ip_prefix = "ИП"  # Всегда заглавными
            remaining_name = ip_match.group(2).strip()

        # Если имя пустое после удаления префикса, возвращаем только префикс
        if not remaining_name:
            return ip_prefix if ip_prefix else name

        # Нормализуем оставшуюся часть имени
        def _capitalize_word(word: str) -> str:
            if not word:
                return word
            # Аббревиатуры орг-правовых форм должны оставаться заглавными: ПАО, АО, ООО и т.п.
            upper_abbrs = {"ПАО", "АО", "ООО", "ОАО", "ЗАО"}
            if word.upper() in upper_abbrs:
                return word.upper()
            # Обрабатываем дефисы (например, "Иванов-Петров")
            if "-" in word:
                parts = word.split("-")
                capitalized_parts = []
                for part in parts:
                    if part:
                        capitalized_parts.append(part[:1].upper() + part[1:].lower())
                    else:
                        capitalized_parts.append(part)
                return "-".join(capitalized_parts)
            # Для обычных слов: первая буква заглавная, остальные строчные
            return word[:1].upper() + word[1:].lower()

        # Разбиваем на слова и нормализуем каждое
        words = [w for w in re.split(r"\s+", remaining_name) if w]
        normalized_words = [_capitalize_word(word) for word in words]
        normalized_name = " ".join(normalized_words)

        # Возвращаем с префиксом "ИП", если он был
        if ip_prefix:
            return f"{ip_prefix} {normalized_name}"

        return normalized_name
