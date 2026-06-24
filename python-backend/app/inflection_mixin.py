# -*- coding: utf-8 -*-
import logging
import re
from typing import Optional

from morph_utils import detect_gender, inflect_surname

try:
    from pymorphy3 import MorphAnalyzer
except ImportError:  # pragma: no cover
    MorphAnalyzer = None

logger = logging.getLogger(__name__)


class InflectionMixin:
    """Методы группы, вынесенные из DocumentAnalyzer (поведение 1-в-1)."""

    def _ensure_morph(self) -> Optional[MorphAnalyzer]:
        if MorphAnalyzer is None:
            return None

        if self.morph is not None:
            return self.morph
        try:
            self.morph = MorphAnalyzer()
        except Exception as exc:
            logger.warning(f"Не удалось загрузить pymorphy3: {exc}")
            self.morph = None
        return self.morph

    def _match_original_case(self, original: str, new_value: str) -> str:
        if original.isupper():
            return new_value.upper()
        if original.istitle():
            return new_value.capitalize()
        return new_value

    def _inflect_word(self, word: str, target_case: str = "gent") -> str:
        morph = self._ensure_morph()
        if not morph or not word:
            return word

        if '-' in word:
            parts = word.split('-')
            inflected_parts = [self._inflect_word(part, target_case) for part in parts]
            return '-'.join(inflected_parts)

        parsed = morph.parse(word)[0]
        inflected = parsed.inflect({target_case})
        new_value = inflected.word if inflected else word
        return self._match_original_case(word, new_value)

    def _inflect_full_name(self, full_name: str, case: str) -> Optional[str]:
        """Просклонять ФИО в падеж `case` (gent/datv/ablt/accs).

        Единый путь для всех падежей (маркеры [2.1]–[2.4]):
        фамилия (первый токен) — через morph_utils.inflect_surname (учёт рода +
        предпочтение Surn-разбора + ручной суффиксный fallback); имя/отчество —
        через существующий _inflect_word (для винительного — одушевлённая форма).
        """
        if not full_name:
            return None
        morph = self._ensure_morph()
        if not morph:
            return None
        tokens = [token for token in re.split(r"\s+", full_name.strip()) if token]
        if not tokens:
            return None

        gender = detect_gender(tokens)
        inflected_tokens = []
        for idx, token in enumerate(tokens):
            try:
                if idx == 0:
                    inflected_tokens.append(inflect_surname(morph, token, case, gender))
                else:
                    inflected_tokens.append(self._inflect_name_token(token, case))
            except Exception as e:
                logger.warning(f"Ошибка при склонении слова '{token}' в падеж {case}: {e}")
                inflected_tokens.append(token)

        result = " ".join(inflected_tokens).strip()
        return result or None

    def _inflect_name_token(self, token: str, case: str) -> str:
        """Склонение имени/отчества. Для винительного — одушевлённая форма (кого?)."""
        if case == "accs":
            morph = self._ensure_morph()
            if morph and token:
                parsed = morph.parse(token)[0]
                inflected = parsed.inflect({'accs', 'anim'}) or parsed.inflect({'accs'})
                if inflected:
                    return self._match_original_case(token, inflected.word)
            return token
        return self._inflect_word(token, case)

    def _convert_name_to_genitive(self, full_name: str) -> Optional[str]:
        """ФИО в родительный падеж (кого? чего?). Маркер [2.1]."""
        return self._inflect_full_name(full_name, "gent")

    def _convert_name_to_instrumental(self, full_name: str) -> Optional[str]:
        """ФИО в творительный падеж (кем? чем?). Маркер [2.3]."""
        return self._inflect_full_name(full_name, "ablt")

    def _convert_name_to_accusative(self, full_name: str) -> Optional[str]:
        """ФИО в винительный падеж одушевлённый (кого?). Маркер [2.4]."""
        return self._inflect_full_name(full_name, "accs")

    def _convert_name_to_dative(self, full_name: str) -> Optional[str]:
        """ФИО в дательный падеж (кому? чему?). Маркер [2.2].

        Для женщин фамилия — в женском роде (Мартыновой, а не Мартынову): род
        определяется в detect_gender, передаётся в inflect_surname.
        """
        return self._inflect_full_name(full_name, "datv")

    def _capitalize_word(self, word: str) -> str:
        if not word:
            return word

        segments = word.split('-')
        capitalized_segments = []
        for segment in segments:
            if not segment:
                capitalized_segments.append(segment)
                continue
            capitalized_segments.append(segment[:1].upper() + segment[1:].lower())
        return '-'.join(capitalized_segments)
