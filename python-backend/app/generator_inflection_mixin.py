# -*- coding: utf-8 -*-
"""Падежи/регистр ФИО для генератора (вынос без изменения поведения).

Капитализация и склонение ФИО заявителя-женщины в род./дат. падеж,
нормализация регистра имени. Группа самодостаточна (внешних self-вызовов нет;
внутри — только взаимные _female_*). Поведение 1-в-1 под gen-golden.
"""
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

    def _female_surname_to_genitive_dative(self, surname: str) -> tuple:
        """Женская фамилия: (родительный, дательный). Калугина -> (Калугиной, Калугиной)."""
        s = surname.strip()
        if not s:
            return ("", "")
        low = s.lower()
        if low.endswith("ова"):
            base = s[:-3]
            return (base + "овой", base + "овой")
        if low.endswith("ева") or low.endswith("ёва"):
            base = s[:-3]
            return (base + "евой", base + "евой")
        if low.endswith("ина"):
            base = s[:-3]
            return (base + "иной", base + "иной")
        if low.endswith("а"):
            base = s[:-1]
            return (base + "ой", base + "ой")
        if low.endswith("я"):
            base = s[:-1]
            return (base + "и", base + "е")
        return (s, s)

    def _female_name_to_genitive_dative(self, name: str) -> tuple:
        """Женское имя: (родительный, дательный). Наталья -> (Натальи, Наталье)."""
        n = name.strip()
        if not n:
            return ("", "")
        low = n.lower()
        if low.endswith("ья"):
            base = n[:-2]
            return (base + "ьи", base + "ье")
        if low.endswith("ия"):
            base = n[:-2]
            return (base + "ии", base + "ии")
        if low.endswith("я"):
            base = n[:-1]
            return (base + "и", base + "е")
        if low.endswith("а"):
            base = n[:-1]
            return (base + "ы", base + "е")
        return (n, n)

    def _female_patronymic_to_genitive_dative(self, patronymic: str) -> tuple:
        """Женское отчество: (родительный, дательный). Юрьевна -> (Юрьевны, Юрьевне)."""
        p = patronymic.strip()
        if not p:
            return ("", "")
        low = p.lower()
        if low.endswith("овна"):
            base = p[:-4]
            return (base + "овны", base + "овне")
        if low.endswith("евна") or low.endswith("ёвна"):
            base = p[:-4]
            return (base + "евны", base + "евне")
        if low.endswith("ична"):
            base = p[:-4]
            return (base + "ичны", base + "ичне")
        if low.endswith("инична"):
            base = p[:-6]
            return (base + "иничны", base + "иничне")
        if low.endswith("а"):
            base = p[:-1]
            return (base + "ы", base + "е")
        return (p, p)

    def _correct_female_applicant_cases(self, cleaned_data: Dict[str, Any]) -> None:
        """
        Для ФЛ-женщин пересчитывает applicantNameDative и applicantNameGenitive из applicantName,
        исправляет дательный (Калугину -> Калугиной) и восстанавливает обрезанную фамилию в родительном (Лугиной -> Калугиной).
        """
        # Для юридических лиц падежи ФИО не применяются.
        entity_type = (cleaned_data.get("entityType") or "").strip().lower()
        if entity_type == "legal":
            return

        applicant_name = (cleaned_data.get("applicantName") or "").strip()
        if not applicant_name:
            return
        # Несколько должников склеены через запятую — единичное склонение неприменимо
        # (падежи уже посчитаны и склеены в _combine_debtors).
        if "," in applicant_name:
            return
        parts = [w for w in re.split(r"\s+", applicant_name) if w]
        if len(parts) < 3:
            return
        surname_nom, name_nom, patronymic_nom = parts[0], parts[1], parts[2]
        name_low = name_nom.lower()
        # Женские окончания имени
        if not (name_low.endswith("а") or name_low.endswith("я") or name_low.endswith("ия") or name_low.endswith("ья")):
            return

        gen_surname, dat_surname = self._female_surname_to_genitive_dative(surname_nom)
        gen_name, dat_name = self._female_name_to_genitive_dative(name_nom)
        gen_patr, dat_patr = self._female_patronymic_to_genitive_dative(patronymic_nom)

        new_genitive = f"{gen_surname} {gen_name} {gen_patr}".strip()
        new_dative = f"{dat_surname} {dat_name} {dat_patr}".strip()

        current_gen = (cleaned_data.get("applicantNameGenitive") or "").strip()
        current_dat = (cleaned_data.get("applicantNameDative") or "").strip()

        cleaned_data["applicantNameGenitive"] = new_genitive
        cleaned_data["applicantNameDative"] = new_dative

        if current_gen != new_genitive:
            logger.info(f"🔧 Исправлен родительный падеж (жен.): '{current_gen}' -> '{new_genitive}'")
        if current_dat != new_dative:
            logger.info(f"🔧 Исправлен дательный падеж для женщины: '{current_dat}' -> '{new_dative}'")

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
        ip_match = re.match(r'^(ИП|ип|Ип)\s*(.+)$', name, re.IGNORECASE)
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

