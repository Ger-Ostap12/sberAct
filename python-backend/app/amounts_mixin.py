import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import field_contract
from patterns import FNS_CAT_LABELS, FNS_QUEUE_ORDINAL_WORDS

logger = logging.getLogger(__name__)


class AmountsMixin:
    if TYPE_CHECKING:
        # Реализован в document_analyzer.DocumentAnalyzer; здесь только для Pyright
        # (mixin-класс вызывает метод, который появится в итоговом составном классе).
        def _extract_kommersant_publication(self, extracted_fields: Dict[str, Any], text: str) -> None: ...

    # Денежный токен целиком: «180 532,78», «1 234 567», «7013,00», «0,00».
    # Разряды — РОВНО по три цифры, копейки только в конце. Иначе за сумму
    # сходит склейка соседних чисел таблицы («221 487,12 446 340,73») и любая
    # цифровая строка, из которой нормализатор выбрасывает разделители
    # (номер дела «А47-7950/2011» -> 4 779 502 011,00).
    _MONEY_TOKEN_RE = re.compile(
        r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d{1,2})?(?!\d)"
        r"|\d+(?:[.,]\d{1,2})?(?!\d)"
    )
    # Буква в захвате денежного поля — верный признак, что поймано не число
    # («А47-7950/2011», «Кому выдана», «руб.» отрезаем отдельно).
    _MONEY_LETTERS_RE = re.compile(r"[^\W\d_]", re.UNICODE)

    def money_token_from_capture(self, raw: Union[str, None]) -> str:
        """Первый денежный токен из захвата паттерна; '' — денег в захвате нет.

        Захваты вида `([0-9\\s,]+)` тянутся через переводы строк и склеивают
        соседние ячейки таблицы, а `normalize_amount_value` молча выбрасывает
        любые не-цифры — вместе они превращали номер дела в миллиардный долг.
        Здесь захват сначала обрезается по первому переводу строки, затем из
        него берётся первый корректно сгруппированный токен.
        """
        if not raw:
            return ""
        text = str(raw).split("\n")[0]
        text = re.sub(r"(?:руб(?:\.|лей|ля)?|₽|коп(?:\.|еек)?)", " ", text, flags=re.IGNORECASE)
        if self._MONEY_LETTERS_RE.search(text):
            return ""
        match = self._MONEY_TOKEN_RE.search(text)
        return match.group(0).strip() if match else ""

    def normalize_amount_value(self, value: str) -> str:
        """
        Приводит строку с денежной суммой к виду '4 111 142,81'
        """
        if not value:
            return value

        cleaned = value.replace("\u202f", " ").replace("\xa0", " ")
        cleaned = re.sub(r'(?:руб(?:\.|лей)?|₽|р\.?)', "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        cleaned = re.sub(r"[^0-9,.\s]", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)

        cleaned = re.sub(r"^[,.\s]+", "", cleaned)
        if not cleaned:
            return cleaned

        tmp = cleaned.replace(" ", "")
        has_comma = "," in tmp
        has_dot = "." in tmp

        if has_comma and has_dot:
            # Запятая правее точки — запятая это разделитель копеек ('1.234.567,89')
            if tmp.rfind(",") > tmp.rfind("."):
                tmp = tmp.replace(".", "")
                tmp = tmp.replace(",", ".")
            else:
                tmp = tmp.replace(",", "")
        else:
            tmp = tmp.replace(",", ".")

        tmp = re.sub(r"[^0-9.]", "", tmp)
        parts = tmp.split(".")
        if len(parts) > 2:
            tmp = parts[0] + "." + "".join(parts[1:])

        try:
            number = float(tmp)
        except Exception:
            return cleaned

        formatted = f"{number:,.2f}".replace(",", " ").replace(".", ",")
        return formatted

    def _extract_claim_block_amounts(self, extracted_fields, text):
        """Суммы из блока «ПРОСИТ СУД» (rtk_application): основной долг, проценты, неустойка, госпошлина, публикация. Вынесено из extract_fields."""
        # --- Неустойки ([15]) из блока "ПРОСИТ СУД" ---
        forfeit15_sum_values = []
        claim_start = re.search(r"ПРОСИТ\s+СУД", text, re.IGNORECASE)
        claim_block = ""
        if claim_start:
            start_pos = claim_start.start()
            claim_block = text[start_pos : start_pos + 5000]
        search_text = claim_block if claim_block else text

        money_pattern = r"\d[\d\u00a0\u202f\s]*[.,]\d{2}"

        # Основной долг [13] и проценты [14] из блока "ПРОСИТ СУД": построчный
        # разбор, чтобы проценты не подменялись суммой основного долга.
        principal_candidate = None
        interest_candidate = None
        principal_candidate_val = -1.0
        interest_candidate_val = -1.0
        if search_text:
            for raw_line in search_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                lower_line = line.lower()
                # Денежные суммы берем только из строк, где явно есть рубли/₽,
                # чтобы даты вида "09.09.2025" не превращались в "9,09".
                if "руб" not in lower_line and "₽" not in line:
                    continue
                money_matches = re.findall(money_pattern, line)
                if not money_matches:
                    continue
                # В строке может быть несколько чисел — берем максимальную денежную сумму
                # (например, чтобы "53 349,00" не превращалось в "4,03" из-за частичного совпадения).
                best_amount = None
                best_amount_val = -1.0
                for m in money_matches:
                    normalized = self.normalize_amount_value(m)
                    val = self._safe_amount_field(normalized)
                    if val > best_amount_val:
                        best_amount_val = val
                        best_amount = normalized
                amount = best_amount
                if not amount:
                    continue

                is_principal_line = ("основн" in lower_line and "долг" in lower_line)
                is_interest_line = ("процент" in lower_line)

                # Берём МАКСИМАЛЬНУЮ сумму среди подходящих строк (а не первую),
                # чтобы мелкие значения/шум не побеждали реальные суммы.
                if is_principal_line and not is_interest_line:
                    v = self._safe_amount_field(amount)
                    if v > principal_candidate_val:
                        principal_candidate_val = v
                        principal_candidate = amount

                # Для процентов исключаем строки основного долга, чтобы не было подмены.
                if is_interest_line and "основн" not in lower_line:
                    v = self._safe_amount_field(amount)
                    if v > interest_candidate_val:
                        interest_candidate_val = v
                        interest_candidate = amount

        if principal_candidate:
            logger.info(f"Найден основной долг [13] по строке: {principal_candidate}")
        if interest_candidate:
            logger.info(f"Найдены проценты [14] по строке: {interest_candidate}")

        if principal_candidate:
            extracted_fields["principalDebt13"] = principal_candidate
            extracted_fields["principalDebt"] = principal_candidate
        if interest_candidate:
            extracted_fields["interest14"] = interest_candidate
            extracted_fields["interest"] = interest_candidate

        if search_text:
            seen_amounts = set()
            for raw_line in search_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                lower_line = line.lower()
                if "неустойк" not in lower_line:
                    continue
                # Игнорируем сводные формулировки вида
                # "3. Задолженность по неустойке в размере 35,89 рублей учесть ..."
                if re.match(r"\d+\.", line):
                    continue
                if "задолженность по неустойке" in lower_line and "учесть" in lower_line:
                    continue

                # Берём именно денежные суммы целиком (с пробелами внутри: "8 226,00")
                number_matches = re.findall(money_pattern, line)
                if not number_matches:
                    continue

                for num_str in number_matches:
                    normalized = (
                        num_str.replace("\u00a0", "")
                        .replace("\u202f", "")
                        .replace(" ", "")
                        .replace(",", ".")
                    )
                    if not normalized or normalized in seen_amounts:
                        continue
                    try:
                        value = float(normalized)
                    except ValueError:
                        continue
                    seen_amounts.add(normalized)
                    forfeit15_sum_values.append(value)
                    logger.info(
                        f"Найдена неустойка в блоке ПРОСИТ СУД по строке: '{line[:80]}...' -> {num_str} ({value})"
                    )

        if forfeit15_sum_values:
            total_forfeit = sum(forfeit15_sum_values)
            formatted_forfeit = f"{total_forfeit:,.2f}".replace(",", " ").replace(".", ",")
            extracted_fields["forfeit15"] = formatted_forfeit
            extracted_fields["forfeit"] = formatted_forfeit
            logger.info(
                f"Сумма всех неустоек [15]: {formatted_forfeit} руб. (найдено {len(forfeit15_sum_values)} значений)"
            )


        state_duty_values: List[str] = []
        existing_state_duty_nonzero = self._safe_amount_field(
            extracted_fields.get("stateDuty16") or extracted_fields.get("stateDuty")
        )
        if search_text:
            seen_state_duty_raw: set[str] = set()
            for raw_line in search_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                lower_line = line.lower()
                if (
                    "госпошл" not in lower_line
                    and "государственной пошл" not in lower_line
                    and "нотариальн" not in lower_line
                ):
                    continue


                line_no_refs = re.sub(
                    r"\b(?:ст(?:атьи|атья|\.)|пп?\.|подпункт\w*|пункт\w*|части?|ч\.)\s*\d+(?:[.,]\d+)?",
                    " ", line, flags=re.IGNORECASE,
                )
                money_matches = re.findall(money_pattern, line_no_refs)
                if not money_matches:
                    continue

                # В одной строке может быть несколько чисел (или частичные совпадения).
                # Берем ОДНО — максимальное — чтобы не выбрать "4,03" вместо "53 349,00".
                best_value = None
                best_raw_norm = None
                for num_str in money_matches:
                    normalized = (
                        num_str.replace("\u00a0", "")
                        .replace("\u202f", "")
                        .replace(" ", "")
                        .replace(",", ".")
                    )
                    if not normalized:
                        continue
                    try:
                        value = float(normalized)
                    except ValueError:
                        continue
                    if best_value is None or value > best_value:
                        best_value = value
                        best_raw_norm = normalized

                if best_value is None or best_raw_norm is None:
                    continue
                if best_raw_norm in seen_state_duty_raw:
                    continue

                formatted_state_duty = f"{best_value:,.2f}".replace(",", " ").replace(".", ",")
                state_duty_values.append(formatted_state_duty)
                seen_state_duty_raw.add(best_raw_norm)
                logger.info(
                    f"Госпошлина из блока ПРОСИТ СУД: {formatted_state_duty} (строка: '{line[:80]}...')"
                )

        unique_state_duty_values: List[str] = []
        for v in state_duty_values:
            if v not in unique_state_duty_values:
                unique_state_duty_values.append(v)
        state_duty_values = unique_state_duty_values


        has_nonzero_from_claim = any(self._safe_amount_field(v) > 0 for v in state_duty_values)
        if existing_state_duty_nonzero > 0 and not has_nonzero_from_claim:
            logger.info(
                "Госпошлина из блока ПРОСИТ СУД равна 0,00; сохраняем ранее извлеченную ненулевую госпошлину"
            )
            state_duty_values = []

        if state_duty_values:
            # Ненулевая госпошлина всегда приоритетнее 0,00.
            nonzero_duties = [v for v in state_duty_values if self._safe_amount_field(v) > 0]
            if nonzero_duties:

                existing_nonzero_any = max(
                    self._safe_amount_field(extracted_fields.get("stateDuty16")),
                    self._safe_amount_field(extracted_fields.get("stateDuty")),
                )
                best_nonzero = max(nonzero_duties, key=lambda x: self._safe_amount_field(x))
                best_val = self._safe_amount_field(best_nonzero)
                if existing_nonzero_any > 0 and best_val > 0 and best_val < existing_nonzero_any / 5:
                    logger.info(
                        f"Госпошлина из блока ПРОСИТ СУД ({best_nonzero}) слишком мала относительно ранее найденной ({extracted_fields.get('stateDuty16') or extracted_fields.get('stateDuty')}); игнорируем"
                    )
                    nonzero_duties = []
                    state_duty_values = []
                else:
                    # Сортируем по убыванию — чтобы первой была наиболее вероятная
                    nonzero_duties = sorted(nonzero_duties, key=lambda x: self._safe_amount_field(x), reverse=True)
                if len(nonzero_duties) == 1:
                    duty = nonzero_duties[0]
                    extracted_fields["stateDuty16"] = duty
                    extracted_fields["stateDuty"] = duty
                    logger.info(f"Установлена госпошлина (ненулевой приоритет): {duty}")
                elif len(nonzero_duties) >= 2:
                    bankruptcy_duty = nonzero_duties[0]
                    loan_duty = nonzero_duties[1]
                    extracted_fields["stateDuty16"] = bankruptcy_duty
                    extracted_fields["stateDuty"] = bankruptcy_duty
                    extracted_fields["loanStateDuty17"] = loan_duty
                    logger.info(f"Госпошлина (банкротная) [16]: {bankruptcy_duty}")
                    logger.info(f"Госпошлина (ссудная) [17]: {loan_duty}")
                else:
                    # После защитных фильтров список мог стать пустым — ничего не перезаписываем.
                    logger.info("После фильтрации госпошлины в блоке ПРОСИТ СУД значений не осталось")
            elif len(state_duty_values) == 1:
                # Все найденные значения нулевые: используем 0,00 только когда ненулевых вариантов нет.
                duty = state_duty_values[0]
                existing_nonzero_any = max(
                    self._safe_amount_field(extracted_fields.get("stateDuty16")),
                    self._safe_amount_field(extracted_fields.get("stateDuty")),
                )
                # Никогда не даём 0,00 перезатереть ранее найденную ненулевую госпошлину.
                if existing_nonzero_any > 0 and self._safe_amount_field(duty) <= 0:
                    logger.info(
                        "Госпошлина из блока ПРОСИТ СУД равна 0,00; сохраняем ранее извлеченную ненулевую госпошлину"
                    )
                else:
                    extracted_fields["stateDuty16"] = duty
                    extracted_fields["stateDuty"] = duty
                    logger.info(f"Установлена банкротная госпошлина (единственная в заявлении): {duty}")
            else:
                bankruptcy_duty = state_duty_values[0]
                loan_duty = state_duty_values[1]
                extracted_fields["stateDuty16"] = bankruptcy_duty
                extracted_fields["stateDuty"] = bankruptcy_duty
                extracted_fields["loanStateDuty17"] = loan_duty
                logger.info(f"Госпошлина (банкротная) [16]: {bankruptcy_duty}")
                logger.info(f"Госпошлина (ссудная) [17]: {loan_duty}")

        # [67]/[68] — газета «Коммерсантъ»
        self._extract_kommersant_publication(extracted_fields, text)

    def _sanitize_credit_params(self, extracted_fields, text):
        """Санити-проверка кредитных параметров: срок (мес.) и ставка (%) не должны быть денежными суммами. Вынесено из extract_fields."""
        term_raw = extracted_fields.get("creditTermMonths")
        if term_raw:
            term_digits = re.sub(r"\D", "", str(term_raw))
            term_value = int(term_digits) if term_digits else None
            # Реалистичный срок кредита в месяцах.
            if not term_value or term_value < 1 or term_value > 600:

                term_match = re.search(
                    r"на\s+срок\s+([0-9]{1,3})\s*(?:\[[0-9.]+\]\s*)?(?:месяц(?:ев)?|мес\.?)",
                    text,
                    re.IGNORECASE,
                ) or re.search(
                    r"срок\s+кредита[:\s]+([0-9]{1,3})\s*(?:\[[0-9.]+\]\s*)?(?:месяц(?:ев)?|мес\.?)",
                    text,
                    re.IGNORECASE,
                )
                if term_match:
                    extracted_fields["creditTermMonths"] = term_match.group(1)
                    logger.info(
                        f"Скорректировано creditTermMonths по строгому паттерну: {extracted_fields['creditTermMonths']}"
                    )
                else:
                    logger.warning(
                        f"Удалено некорректное значение creditTermMonths: '{term_raw}'"
                    )
                    extracted_fields.pop("creditTermMonths", None)
            else:
                extracted_fields["creditTermMonths"] = str(term_value)

        rate_raw = extracted_fields.get("creditInterestRate")
        if rate_raw:
            rate_match = re.search(r"([0-9]{1,3}(?:[.,][0-9]{1,2})?)", str(rate_raw))
            rate_value = None
            if rate_match:
                try:
                    rate_value = float(rate_match.group(1).replace(",", "."))
                except Exception:
                    rate_value = None

            # Процентная ставка в таких документах не должна быть денежной суммой
            # и обычно находится в диапазоне 0..100.
            if rate_value is None or rate_value <= 0 or rate_value > 100:
                strict_rate_match = re.search(
                    r"под\s+([0-9]{1,3}(?:[.,][0-9]{1,2})?)\s*(?:\[[0-9.]+\]\s*)?%",
                    text,
                    re.IGNORECASE,
                )
                if strict_rate_match:
                    corrected_rate = strict_rate_match.group(1).replace(".", ",")
                    extracted_fields["creditInterestRate"] = corrected_rate
                    logger.info(
                        f"Скорректировано creditInterestRate по строгому паттерну: {corrected_rate}"
                    )
                else:
                    logger.warning(
                        f"Удалено некорректное значение creditInterestRate: '{rate_raw}'"
                    )
                    extracted_fields.pop("creditInterestRate", None)
            else:
                if rate_value.is_integer():
                    extracted_fields["creditInterestRate"] = str(int(rate_value))
                else:
                    extracted_fields["creditInterestRate"] = str(rate_value).replace(".", ",")

    def _extract_summable_field(self, extracted_fields, text, field_name, field_patterns):
        """Суммируемые поля (долг/проценты/неустойка/итого): выбор значения из паттернов с приоритетом первого для debtAmount/totalDebt. Возвращает True (поле обработано -> continue). Вынесено из pattern-цикла."""
        collected_values = []
        # Для общей суммы долга и суммы долга: берём значение только из первого совпавшего паттерна
        # (чтобы не подставлять сумму выдачи кредита вместо суммы требований)
        use_first_pattern_only = field_name in ("debtAmount", "totalDebt")

        for i, pattern in enumerate(field_patterns):
            logger.info(f"  Паттерн {i+1} для {field_name}: {pattern}")
            matches = re.findall(pattern, text, re.IGNORECASE)
            logger.info(f"  Найдено совпадений: {len(matches)}")
            pattern_values = []
            for match in matches:
                if isinstance(match, tuple):
                    match_value = next((part for part in match if part), "")
                else:
                    match_value = match

                match_value = (match_value or "").strip()
                if not match_value:
                    continue

                # Захват `[0-9\s,]+` тянется через переводы строк и склеивает
                # соседние числа таблицы в одно — берём из него первый корректный
                # денежный токен, а не всё подряд.
                match_value = self.money_token_from_capture(match_value) or match_value
                normalized_amount = self.normalize_amount_value(match_value)
                if normalized_amount:
                    pattern_values.append(normalized_amount)
                    if not use_first_pattern_only:
                        collected_values.append(normalized_amount)
                    logger.info(f"Found {field_name} amount: {normalized_amount}")

            if use_first_pattern_only and pattern_values:
                # Для totalDebt берём последнюю найденную сумму в паттерне (например, "а всего 163 210,00 руб.")
                chosen_value = pattern_values[-1] if field_name == "totalDebt" else pattern_values[0]
                extracted_fields[field_name] = chosen_value
                logger.info(f"Selected {field_name} (первый приоритетный паттерн): {extracted_fields[field_name]}")
                break
            elif not use_first_pattern_only:
                collected_values.extend(pattern_values)
        else:
            if not use_first_pattern_only and collected_values:
                # Для сумм без строгого приоритета берём первое найденное значение,
                # чтобы избежать искусственного завышения (особенно для forfeit)
                extracted_fields[field_name] = collected_values[0]
                logger.info(f"Selected {field_name}: {extracted_fields[field_name]}")
        return True
        return False

    def _fin_amount(self, s) -> float:
        """Парсит денежную строку в float (учёт пробелов/неразрывных пробелов/запятой)."""
        if not s:
            return 0.0
        n = (str(s).replace(" ", "").replace(" ", "")
             .replace(" ", "").replace(",", "."))
        n = re.sub(r"[^\d.]", "", n)
        if not n or n == ".":
            return 0.0
        try:
            return float(n)
        except ValueError:
            return 0.0

    def _fin_fmt(self, v: float) -> str:
        """Форматирует float в «1 234 567,89»."""
        return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", " ")

    # Сумма в самобанкротной формулировке: разряды пробелами, копейки могут быть
    # оторваны пробелом («24 395 516, 3 руб.» — так печатает конвертер скана).
    _SB_AMOUNT = r"(\d[\d   ]*(?:,[   ]?\d{1,2})?)"

    # Грандтотал в заявлении САМОБАНКРОТА. Кредитора-заявителя здесь нет, суммы
    # разложены по кредиторам, а общий долг назван отдельной фразой. Требование
    # «перед кредиторами»/«общий объём» отсекает построчные «общая сумма
    # задолженности ПО кредитному договору №… составляет …» — их в заявлении
    # десяток, и любая из них уезжала в итог вместо целого.
    _SB_TOTAL_RES = (
        re.compile(
            r"общ\w+\s+объ[её]м\w*\s+задолженност\w+\s+составляет\s*" + _SB_AMOUNT,
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:размер|сумма|общая\s+сумма)\s+(?:непогашенн\w+\s+)?задолженност\w+\s+"
            r"(?:должника\s+)?перед\s+кредиторами\s+составляет\s*" + _SB_AMOUNT,
            re.IGNORECASE,
        ),
    )

    def _apply_self_bankruptcy_total(self, fields: Dict[str, Any], text: str) -> None:
        """Общая сумма долга в заявлении самобанкрота — из его сводной фразы.

        В таком заявлении нет ни таблицы расчёта, ни просительной с разбивкой:
        долг перечислен по кредиторам, а целое названо один раз («общий объём
        задолженности составляет 824 831,33 рублей»). Без этой фразы в итог
        попадала сумма ПЕРВОГО кредитора из списка (или мусор из соседней
        ячейки), и она же уезжала во все акты.
        """
        if not text:
            return
        for rx in self._SB_TOTAL_RES:
            match = rx.search(text)
            if not match:
                continue
            raw = re.sub(r",[   ]+(\d)", r",\1", match.group(1))  # «516, 3» -> «516,3»
            token = self.money_token_from_capture(raw)
            total = self._fin_amount(token)
            if total <= 0:
                continue
            formatted = self._fin_fmt(total)
            fields["totalDebt"] = formatted
            fields["debtAmount"] = formatted
            fields["requirementsSum"] = formatted
            # Разбивка (если её успели набрать регулярки) относится к ОДНОМУ
            # кредитору из списка, а не к целому: печатать её в акте как
            # «из них основного долга …» нельзя.
            parts = sum(self._fin_amount(fields.get(k)) for k in
                        ("principalDebt", "loanDebt", "interest", "forfeit", "penalties"))
            if parts and abs(parts - total) > 0.05:
                for key in ("principalDebt", "loanDebt", "interest", "forfeit", "penalties"):
                    fields.pop(key, None)
                logger.info("Самобанкротство: разбивка долга не сходится с целым — очищена")
            logger.info("Самобанкротство: общая сумма долга %s", formatted)
            return

    def _apply_prayer_finances(self, fields: Dict[str, Any], text: str) -> None:
        """Финансы из ПРОСИТЕЛЬНОЙ части: суммирует разбивки долга по категориям
        (осн.долг/проценты/неустойка/ссудная госпошлина), итог = их сумма.

        Структуры:
          - многоблочная: несколько верхнеуровневых пунктов «включить/установить …
            в размере SUB …, из которых: …» (3-я очередь + залог) — суммируются,
            каждый блок валидируется (сумма компонентов = подытогу);
          - одиночная «… в размере TOTAL, из которых: …» — с валидацией итога по тексту;
          - тире-категории «X руб – основной долг, Y руб – неустойка».
        Банкротная госпошлина (отдельные пункты) суммируется и в долг НЕ входит.
        """
        if not text:
            return
        text = text.replace("	", " ")  # табы внутри чисел («5 100 	000») -> пробел
        # Пробел после запятой в копейках («15 952 445, 85» -> «15 952 445,85»),
        # иначе «85» парсится как отдельная сумма и ломает разбивку.
        text = re.sub(r"(\d),[   ]+(\d{2})(?!\d)", r"\1,\2", text)
        low = text.lower()
        NUM = r"(\d[\d   ]*(?:[.,]\d{1,2})?)"

        amt_re = re.compile(r"(\d[\d   ]*(?:[.,]\d{1,2})?)\s*руб(?:л\w*|\.)?", re.IGNORECASE)
        dash_cat_re = re.compile(
            r"\d[\d   ]*(?:,\d{2})?\s*руб[^\u2013\-]{0,15}[\u2013\-]\s*"
            r"(?:основн\w*\s+долг|ссудн\w*|процент\w*|неустойк\w*|штраф\w*|госпошлин\w*|пошлин\w*)",
            re.IGNORECASE,
        )

        def classify(ph):
            ph = ph.lower()
            # штраф vs неустойка — по ВЕДУЩЕМУ (раннему) слову: «неустойки
            # (штрафы, пени)» неустойка, а «штрафные санкции» штраф.
            _sp = ph.find("штраф")
            _np = min([p for p in (ph.find("неустой"), ph.find("пени")) if p != -1], default=-1)
            if _sp != -1 and _np != -1:
                return "forfeit" if _np < _sp else "penalty"
            if _sp != -1:
                return "penalty"
            if _np != -1:
                return "forfeit"
            if "процент" in ph:
                return "interest"
            if "госпошл" in ph or "пошлин" in ph:
                return "loan_duty"
            if ("основн" in ph or "ссудн" in ph or "просроченный кредит" in ph
                    or "просроченному кредиту" in ph):
                return "principal"
            return None

        def parse_seg(seg):
            seg = re.sub(r"\n[ \t]*\d{1,4}[ \t]*(?=\n)", "", seg)

            def is_total(m):
                tail = seg[m.end():m.end() + 18].lower()
                return "из котор" in tail or "в том числе" in tail

            allm = list(amt_re.finditer(seg))
            starts = [a.start() for a in allm]
            ends = [a.end() for a in allm]
            ms = [(i, m) for i, m in enumerate(allm) if not is_total(m)]

            # Окно подписи ограничиваем границами соседних сумм (один пункт разбивки),
            # иначе «80 727,56 - проценты; 8893,98 - пени» даёт «пени» в окне процентов.
            def win_after(i, m):
                nb = starts[i + 1] if i + 1 < len(allm) else len(seg)
                return seg[m.end():min(nb, m.end() + 45)]

            def win_before(i, m):
                pe = ends[i - 1] if i - 1 >= 0 else 0
                return seg[max(pe, m.start() - 45):m.start()]

            after_n = before_n = 0
            for i, m in ms:
                if classify(win_after(i, m)):
                    after_n += 1
                if classify(win_before(i, m)):
                    before_n += 1
            if after_n != before_n:
                use_after = after_n > before_n
            else:
                # Ничья: направление по позиции тире — «категория – ЧИСЛО» (before)
                # против «ЧИСЛО руб – категория» (after); формат САРМАТ/КОЛОР — before.
                da = db = 0
                for i, m in ms:
                    wb = win_before(i, m)
                    wa = win_after(i, m)
                    if re.search(r"[–\-]\s*$", wb) and classify(wb):
                        db += 1
                    if re.match(r"\s*(?:руб\w*\.?)?\s*[–\-]", wa) and classify(wa.split("\n", 1)[0]):
                        da += 1
                use_after = da >= db
            pr = it = fo = pen = ld = 0.0
            hits = 0
            seen = set()
            # Отдельные слагаемые по категориям (для тултипа-разбивки на фронте).
            add: Dict[str, list] = {"principal": [], "interest": [], "forfeit": [],
                                    "penalty": [], "loan_duty": []}
            for i, m in ms:
                val = self._fin_amount(m.group(1))
                ph = win_after(i, m) if use_after else win_before(i, m)
                cat = classify(ph)
                if not cat:
                    continue
                key = (cat, round(val, 2))
                if key in seen:
                    continue
                seen.add(key)
                if cat == "forfeit":
                    fo += val
                elif cat == "penalty":
                    pen += val
                elif cat == "interest":
                    it += val
                elif cat == "loan_duty":
                    ld += val
                else:
                    pr += val
                add[cat].append(val)
                hits += 1
            return pr, it, fo, pen, ld, hits, add

        p_anchor = -1
        for a in ("просим суд", "прошу суд", "просит суд",
                  "включить в третью очередь", "включить в реестр требований"):
            k = low.find(a)
            if k != -1:
                p_anchor = k
                break
        region = text[p_anchor:] if p_anchor != -1 else text
        cutp = re.search(r"\n\s*Приложени", region, re.IGNORECASE)
        prayer_full = region[:cutp.start()] if cutp else region

        principal = interest = forfeit = penalty = loan_duty = 0.0
        validated = False
        # Слагаемые по категориям (для тултипа-разбивки поля на фронте).
        addends: Dict[str, list] = {"principal": [], "interest": [], "forfeit": [],
                                    "penalty": [], "loan_duty": []}

        verb_block_re = re.compile(
            r"(?:включить|установить|призна\w+[^.\n]{0,60}?включить)"
            r"[^.]{0,400}?(?:в\s*размере|вразмере|на\s+сумму)\s+" + NUM +
            r"\s*(?:руб\w*\.?)?[^\n]{0,40}?(?:из\s+котор\w+|в\s+том\s+числе)\s*:?",
            re.IGNORECASE,
        )
        vblocks = list(verb_block_re.finditer(text))
        if vblocks:
            seen_sub = set()
            g = [0.0, 0.0, 0.0, 0.0, 0.0]
            nvalid = 0
            for idx, m in enumerate(vblocks):
                subtotal = self._fin_amount(m.group(1))
                wstart = m.end()
                wend = vblocks[idx + 1].start() if idx + 1 < len(vblocks) else len(text)
                window = text[wstart:wend]
                cw = re.search(
                    r"\n\s*Приложени|также\s+прос|\bутвердить|\bвзыскать|"
                    r"\bустановить|\bввести|призна\w+\s+(?:понесен|обоснов)",
                    window, re.IGNORECASE,
                )
                if cw:
                    window = window[:cw.start()]
                window = window[:1800]
                pr, it, fo, pen, ld, h, add = parse_seg(window)
                ssum = pr + it + fo + pen + ld
                if h and abs(ssum - subtotal) < 1.5 and round(subtotal, 2) not in seen_sub:
                    seen_sub.add(round(subtotal, 2))
                    g[0] += pr; g[1] += it; g[2] += fo; g[3] += pen; g[4] += ld
                    for cat, vals in add.items():
                        addends[cat].extend(vals)
                    nvalid += 1
            if nvalid:
                principal, interest, forfeit, penalty, loan_duty = g
                validated = True

        if not validated:
            start = -1
            # «из котор\w+» = из которых/которой/которого (разбивка долга).
            _izm = re.search(r"из\s+котор\w+", low)
            iz = _izm.start() if _izm else -1
            if iz == -1:
                for mm in re.finditer("в том числе", low):
                    if re.search(r"руб\w*\W{0,5}$", low[max(0, mm.start() - 25):mm.start()]):
                        iz = mm.start()
                        break
            if iz != -1:
                vm = -1
                for kw in ("размере", "составляет", "составила", "составил"):
                    pkw = low.rfind(kw, max(0, iz - 130), iz)
                    if pkw > vm:
                        vm = pkw
                start = vm if vm != -1 else max(0, iz - 130)
            if start == -1:
                for anchor in ("включить в третью очередь", "включить в реестр требований",
                               "просим суд", "прошу суд", "просит суд"):
                    k = low.find(anchor)
                    if k != -1:
                        start = k
                        break
            if start == -1:
                return
            seg = text[start:]
            cut = re.search(r"\n\s*Приложени", seg, re.IGNORECASE)
            if cut:
                seg = seg[:cut.start()]
            has_iz = ("из котор" in seg.lower()) or ("в том числе" in seg.lower())
            if iz != -1:
                wb = re.search(
                    r"(?:нормативно|согласно\b|таким\s+образом|на\s+основани|"
                    r"в\s+соответствии|расч[её]т\s+задолжен|также\s+просим|"
                    r"прос(?:им|ит)\s+суд|прошу\s+суд|\bвзыскать|\bустановить|"
                    r"залогов\w*\s+требовани|\n\s*\n)",
                    seg[30:], re.IGNORECASE,
                )
                if wb:
                    seg = seg[: wb.start() + 30]
            if not has_iz:
                if len(dash_cat_re.findall(seg)) < 2:
                    return
                b = re.search(
                    r"\n\s*(?:\d+[.\)]\s*)?(?:Утвердить|Признать|Взыскать|Установить|Ввести)\b",
                    seg[20:], re.IGNORECASE,
                )
                if b:
                    seg = seg[: b.start() + 20]
                if len(dash_cat_re.findall(seg)) < 2:
                    return
            principal, interest, forfeit, penalty, loan_duty, hits, addends = parse_seg(seg)
            if hits == 0 or (principal + interest + forfeit + penalty) <= 0:
                return
            if has_iz:
                _strip_sp = lambda z: z.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
                total_chk = principal + interest + forfeit + penalty + loan_duty
                if str(int(total_chk)) not in _strip_sp(text):
                    logger.info("PRAYER: total not confirmed in text - skip")
                    return

        if (principal + interest + forfeit + penalty) <= 0:
            return
        total = principal + interest + forfeit + penalty + loan_duty

        if principal > 0:
            fields["principalDebt"] = self._fin_fmt(principal)
            fields["principalDebt13"] = fields["principalDebt"]
        fields["interest"] = self._fin_fmt(interest)
        fields["interest14"] = fields["interest"]
        fields["forfeit"] = self._fin_fmt(forfeit)
        fields["forfeit15"] = fields["forfeit"]
        # Штрафные санкции — отдельное поле (penalties), не путать с неустойкой.
        fields["penalties"] = self._fin_fmt(penalty)
        fields["totalDebt"] = self._fin_fmt(total)
        fields["debtAmount"] = fields["totalDebt"]

        if loan_duty > 0:
            fields["loanStateDuty17"] = self._fin_fmt(loan_duty)
        else:
            fields.pop("loanStateDuty17", None)


        _brk_map = [("principal", "principalDebt"), ("interest", "interest"),
                    ("forfeit", "forfeit"), ("penalty", "penalties"),
                    ("loan_duty", "loanStateDuty17")]
        breakdown = {}
        for cat, fkey in _brk_map:
            vals = [v for v in addends.get(cat, []) if round(v, 2) != 0]  # нули не показываем
            if vals:
                breakdown[fkey] = [self._fin_fmt(v) for v in vals]
        if breakdown:
            fields["financeBreakdown"] = breakdown
        else:
            fields.pop("financeBreakdown", None)

        bankr_duty = 0.0
        for bm in re.finditer(
            r"(?:гос)?пошлин\w*[^\d]{0,120}?в\s*размере\s*(\d[\d   ]*(?:,\d{2})?)\s*руб",
            prayer_full, re.IGNORECASE,
        ):
            bankr_duty += self._fin_amount(bm.group(1))
        if bankr_duty > 0:
            duty = self._fin_fmt(bankr_duty)
            fields["stateDuty16"] = duty
            fields["stateDuty"] = duty

        logger.info(
            "PRAYER finances: pr=%s int=%s fo=%s loanD=%s bankrD=%s total=%s" % (
                fields.get("principalDebt"), fields["interest"], fields["forfeit"],
                fields.get("loanStateDuty17"), fields.get("stateDuty16"), fields["totalDebt"],
            )
        )


    _FNS_AMT_RE = re.compile(
        r"(\d[\d\s  ]*(?:[.,]\d{1,2})?)\s*(?:руб\w*|рублей|py6\w*|р\.|лей)",
        re.IGNORECASE,
    )
    # Маркер очереди: прописью «в первую/во вторую/в третью очередь» ИЛИ цифрой
    # «2-ой очереди», «3-ю очередь». Слово/цифра номер (label-anchored на «очеред»).
    _FNS_QUEUE_RE = re.compile(
        r"(?:в|во)\s+(перв|втор|трет)\w*\s+очеред\w*"
        # Цифровая форма «2-ои/3-ой/3-ю очереди». Порядковый хвост после дефиса —
        # ЛЮБЫЕ буквы (кир./лат. «o» из OCR), не фиксированный класс: раньше «2-ои»
        # не ловилось, т.к. «и» не входило в перечень 2-я очередь терялась целиком.
        r"|(\d)\s*[-–—]?\s*[а-яёo]{0,4}\s*очеред\w*",
        re.IGNORECASE,
    )
    # Подытог очереди: сумма сразу после слова «очередь» + «в размере/в сумме/–».
    _FNS_SUBTOTAL_RE = re.compile(
        r"(?:в\s+размере|в\s+сумме|размере|сумме|[–—\-])\s*[–—\-]?\s*"
        r"(\d[\d\s  ]*(?:[.,]\d{1,2})?)\s*(?:руб\w*|рублей|py6\w*|р\.|лей)",
        re.IGNORECASE,
    )
    _FNS_CAT_COMPILED = [(re.compile(rx, re.IGNORECASE), suf) for rx, suf in FNS_CAT_LABELS]
    # Грандтотал (до разбивки по очередям): «в размере/в (общей) сумме/составляет N».
    _FNS_GRANDTOTAL_RE = re.compile(
        r"(?:в\s+размере|в\s+общей\s+сумме|в\s+сумме|составля\w+)\s*[–—\-]?\s*"
        r"(\d[\d\s  ]*(?:[.,]\d{1,2})?)\s*(?:руб\w*|рублей|py6\w*|р\.|лей)",
        re.IGNORECASE,
    )

    _FNS_GRAND_VSEGO_RE = re.compile(
        r"(?:всего|в\s+общей\s+сумме)\s*[:\-–—]?\s*[-–—]?\s*"
        r"(\d[\d\s]*[.,]\d{2}|\d[\d\s]*\d)\s*(?:руб\w*|рублей|py6\w*|р\.|лей)",
        re.IGNORECASE,
    )

    _FNS_GRANDTOTAL_INCL_RE = re.compile(
        r"(\d[\d\s.  ]*,\d{2})\s*(?:руб\w*|рублей|py6\w*|р\.|лей)[.,\s]*в\s+том\s+числе",
        re.IGNORECASE,
    )
    # Общие поля «Финансовых данных», которые в ФНС-режиме не показываются: чистим,
    # чтобы скрытый общий блок и golden не несли артефакты общего парсера.
    _FNS_CLEAR_FIELDS = (
        "principalDebt", "principalDebt13", "loanDebt", "interest", "interest14",
        "forfeit", "forfeit15", "penalties", "loanStateDuty17", "bankCommission",
        "stateDuty16", "stateDuty", "financeBreakdown",
    )

    _FNS_QUEUE_DEFAULT_SUF = "LoanDebt"

    def _fns_amount(self, s: str) -> float:
        """Денежная строка ФНС float. Знак игнорируем: минус в ФНС-заявлениях
        встречается лишь как артефакт разделителя («по взносам – -96396,39»), суммы
        задолженности всегда положительны (правило Андрея)."""
        return self._fin_amount(s)

    def _fns_grandtotal(self, seg: str) -> Optional[float]:
        """Общая сумма долга ИЗ ТЕКСТА (приоритет над вычислением по очередям):
        сначала ЯВНОЕ «всего N руб» (ключевое слово — надёжный признак итога), затем
        fallback «N руб., в том числе». НЕ используем голое «в размере N»: оно вводит
        и подытоги очередей, из-за чего грандтотал брался неверным (напр. 208472.30
        вместо 1712229.07). Если явного итога нет — вернём None, и вызывающий код
        посчитает сумму по очередям и пометит её флагом «вычислено»."""
        m = self._FNS_GRAND_VSEGO_RE.search(seg)
        if m:
            return self._fin_amount(m.group(1))
        m = self._FNS_GRANDTOTAL_INCL_RE.search(seg)
        if m:
            return self._fin_amount(m.group(1).replace(".", " "))  # точка-тысячи пробел
        return None

    def _fns_queue_num(self, m: "re.Match") -> Optional[int]:
        """Номер очереди из матча _FNS_QUEUE_RE (прописью или цифрой)."""
        if m.group(1):
            return FNS_QUEUE_ORDINAL_WORDS.get(m.group(1).lower())
        if m.group(2):
            n = int(m.group(2))
            return n if 1 <= n <= 3 else None
        return None

    def _parse_fns_segment(self, seg: str, skip_span: Optional[tuple] = None) -> Dict[str, str]:
        """Чистый разбор сегмента одной очереди: категория (по метке ПЕРЕД суммой)
         отформатированная сумма. `skip_span` — позиция подытога (её не берём в
        категории). Без сайд-эффектов; один вход один результат."""
        out: Dict[str, str] = {}
        amts = list(self._FNS_AMT_RE.finditer(seg))
        for i, m in enumerate(amts):
            if skip_span and m.start() <= skip_span[0] < m.end():
                continue
            prev_end = amts[i - 1].end() if i > 0 else 0
            window = seg[prev_end:m.start()]
            # Метка категории — та, чей матч заканчивается БЛИЖЕ всего к сумме слева.
            best_suf, best_pos = None, -1
            for rx, suf in self._FNS_CAT_COMPILED:
                for lm in rx.finditer(window):
                    if lm.end() > best_pos:
                        best_pos, best_suf = lm.end(), suf
            if best_suf and best_suf not in out:
                out[best_suf] = self._fin_fmt(self._fin_amount(m.group(1)))
        return out

    def _apply_fns_queue_finances(self, fields: Dict[str, Any], text: str) -> None:
        """Финансы ФНС-заявлений по ОЧЕРЕДЯМ реестра требований кредиторов.

        Заполняет `totalDebt` (грандтотал) + `fnsQ{n}<Suffix>` (подытог очереди и
        категории: недоимка/штраф/пени/НДФЛ/взносы/осн.долг(=налог)/госпошлина).
        Работает ТОЛЬКО для ФНС (гейт по creditorName), вызывается ПОСЛЕ общего
        `_apply_prayer_finances` и перекрывает его результат на ФНС-файлах. Схема
        полей и маппинг — память fns-queue-finances.
        """
        if not text:
            return
        cred = (fields.get("creditorName") or "").lower()
        if "фнс" not in cred and "налог" not in cred:
            return

        # Просительный регион: от первого якоря требования до «Приложения».
        low = text.lower()
        anchor = -1
        for a in ("включить в реестр требований", "признать требование",
                  "установить требовани", "включить в ртк", "включить в третью очередь",
                  "прошу суд", "просим суд", "просит суд"):
            k = low.find(a)
            if k != -1 and (anchor == -1 or k < anchor):
                anchor = k
        region = text[anchor:] if anchor != -1 else text
        cut = re.search(r"\n\s*Приложени", region, re.IGNORECASE)
        if cut:
            region = region[:cut.start()]

        # Сегменты очередей по маркерам (в порядке появления в тексте).
        markers = [(m.start(), self._fns_queue_num(m)) for m in self._FNS_QUEUE_RE.finditer(region)]
        markers = [(pos, n) for pos, n in markers if n]

        queues: Dict[int, Dict[str, str]] = {}
        if markers:
            for idx, (pos, n) in enumerate(markers):
                end = markers[idx + 1][0] if idx + 1 < len(markers) else len(region)
                seg = region[pos:end]
                data = dict(queues.get(n, {}))
                # Подытог очереди = ПЕРВАЯ денежная сумма после слова «очеред…».
                # Форма связки не важна: «очередь N руб.» (без «в размере», как у
                # Зайцева), «очередь в размере N», «очереди по уплате … в размере N» —
                # все сводятся к «первой сумме за маркером». Единица (руб) обязательна,
                # поэтому ИНН/даты/индексы/№ не попадают. Ранее требовалась явная связка
                # в окне seg[:160] бессвязный подытог терялся.
                mo = re.search(r"очеред\w*", seg, re.IGNORECASE)
                sub = self._FNS_AMT_RE.search(seg, mo.end()) if mo else None
                if sub:
                    data["Total"] = self._fin_fmt(self._fns_amount(sub.group(1)))
                data.update(self._parse_fns_segment(
                    seg, skip_span=(sub.start(1), sub.end(1)) if sub else None))
                queues[n] = data
        else:
            # Очередь не указана 3-я (правило Андрея). Разбивка идёт после грандтотала.
            gt = self._FNS_GRANDTOTAL_RE.search(region)
            data: Dict[str, str] = {}
            if gt:
                data["Total"] = self._fin_fmt(self._fns_amount(gt.group(1)))
                data.update(self._parse_fns_segment(
                    region, skip_span=(gt.start(1), gt.end(1))))
            if data:
                queues[3] = data

        if not queues:
            return

        # ВАЛИДАЦИЯ ОЧЕРЕДИ «минимум 2 поля или пусто» (правило Андрея). Категории —
        # всё, кроме подытога Total. Три случая:
        #   • есть только Total вся сумма очереди = ссудная задолженность (LoanDebt),
        #     равная Total (правило Андрея для любой очереди) 2 РАВНЫХ поля;
        #   • есть категории, но нет Total Total = Σ категорий (получаем ≥2 поля);
        #   • есть и Total, и категории, но Total ≠ Σ НЕ правим (доверяем Total из
        #     документа; фронт покажет — решение Андрея).
        # Пустую очередь (0 полей) убираем — «полностью пустая» вместо «полуживой».
        for n, data in list(queues.items()):
            cats = [s for s in data if s != "Total"]
            total = data.get("Total")
            if total and not cats:
                data[self._FNS_QUEUE_DEFAULT_SUF] = total
            elif cats and not total:
                s = sum(self._fns_amount(data[c]) for c in cats)
                if s > 0:
                    data["Total"] = self._fin_fmt(s)
            if not data:
                queues.pop(n, None)
        if not queues:
            return

        # Грандтотал: СНАЧАЛА берём ЯВНУЮ общую сумму ИЗ ДОКУМЕНТА («…всего N руб»)
        # в зачине просительной части — от начала просительного региона до первого
        # маркера очереди (не весь документ, иначе поймаем число из шапки; но и не
        # узкие 300 симв. — «всего» может стоять чуть раньше разбивки). Только если
        # явного «всего» нет — вычисляем как Σ подытогов очередей и помечаем флагом
        # (фронт покажет «значение вычислено»).
        head = region[:markers[0][0]] if markers else ""
        grand_doc = self._fns_grandtotal(head) if head else None
        total_computed = False
        if grand_doc is not None:
            grand = grand_doc
        else:
            grand = sum(self._fin_amount(q["Total"]) for q in queues.values() if q.get("Total"))
            # Флаг «вычислено» — только когда итог реально СЛОЖЕН из НЕСКОЛЬКИХ очередей.
            # При ОДНОЙ очереди итог = её подытог, взятый из документа (Артемов/Геворгян/
            # Мишунин: только 3-я очередь) — это не «сумма трёх очередей», не ставим.
            if len(queues) >= 2:
                total_computed = True

        # Чистим общий блок финансов (в ФНС-режиме он скрыт) и пишем ФНС-поля.
        for k in self._FNS_CLEAR_FIELDS:
            fields.pop(k, None)
        fields.pop("fnsTotalComputed", None)
        if grand > 0:
            fields["totalDebt"] = self._fin_fmt(grand)
            fields["debtAmount"] = fields["totalDebt"]
            if total_computed:
                fields["fnsTotalComputed"] = "1"
        for n, data in queues.items():
            for suf, val in data.items():
                fields[f"fnsQ{n}{suf}"] = val

        logger.info(
            "FNS queue finances: total=%s queues=%s" % (
                fields.get("totalDebt"),
                {n: sorted(d) for n, d in queues.items()},
            )
        )

        # Диагностическая сверка (не правит данные — только сигнализирует в лог о
        # расхождениях, чтобы ловить недоизвлечение/битые исходники; на фронте те же
        # расхождения показываются пользователю ). Допуск 1 руб. на округление.
        _cmp = [suf for suf in ("Arrears", "Penalties", "Forfeit", "Ndfl", "Insurance",
                                "LoanDebt", "LoanDuty", "Commission")]
        for n, data in queues.items():
            sub = self._fin_amount(data.get("Total"))
            parts = sum(self._fns_amount(data[s]) for s in _cmp if s in data)
            if sub and parts and abs(sub - parts) > 1.0:
                logger.warning(
                    "FNS сверка: очередь %s — подытог %.2f ≠ Σ строк %.2f (расхождение %.2f)"
                    % (n, sub, parts, sub - parts)
                )
        totals_sum = sum(self._fin_amount(q["Total"]) for q in queues.values() if q.get("Total"))
        if grand and totals_sum and abs(grand - totals_sum) > 1.0:
            logger.warning(
                "FNS сверка: общая сумма %.2f ≠ Σ подытогов очередей %.2f (расхождение %.2f)"
                % (grand, totals_sum, grand - totals_sum)
            )

    def _sum_bankruptcy_duty(self, fields: Dict[str, Any], text: str) -> None:
        """Банкротная госпошлина ДВУМЯ слагаемыми после одной метки.

        Банки указывают банкротную госпошлину суммой двух чисел под одной меткой:
        «Госпошлина: 1 490 913 руб.+ 100 000 руб.» / «(судебные расходы по оплате
        государственной) пошлины в размере 100 000 рублей и 1 490 913 руб.». Общая
        логика разносила первое число в банкротную, второе — в ссудную [17] (или
        брала max). Здесь суммируем ОБА в банкротную госпошлину (stateDuty) и убираем
        ложную ссудную, равную одному из слагаемых. Срабатывает только на редком
        паттерне «метка + N (+|и|,) M …» в контексте банкротного заявления, поэтому
        прочий корпус не задевает. Госпошлина в итог долга не входит (её тут не трогаем).
        """
        flat = re.sub(r"[  \t]", " ", text)
        if not re.search(r"банкрот|несостоятельн", flat, re.IGNORECASE):
            return
        NUM = r"\d[\d ]*(?:[.,]\d{1,2})?"
        run_re = re.compile(
            r"(?:гос)?пошлин\w*[^\d]{0,40}?"
            r"(" + NUM + r"\s*руб\w*\.?\s*[+и,]\s*" + NUM
            + r"(?:\s*руб\w*\.?\s*[+и,]\s*" + NUM + r")*)",
            re.IGNORECASE,
        )
        m = run_re.search(flat)
        if not m:
            return
        parts = [self._fin_amount(x) for x in re.findall(NUM, m.group(1))]
        parts = [p for p in parts if p and p >= 100]
        if len(parts) < 2:
            return
        total_duty = sum(parts)
        fields["stateDuty16"] = self._fin_fmt(total_duty)
        fields["stateDuty"] = self._fin_fmt(total_duty)
        # Ссудная госпошлина, равная одному из слагаемых, — тот же платёж; убираем.
        sd17 = self._fin_amount(fields.get("loanStateDuty17") or "0")
        if any(abs(sd17 - p) < 0.01 for p in parts):
            fields.pop("loanStateDuty17", None)

    def _normalize_financial_block(self, fields: Dict[str, Any], text: str) -> None:
        """Нормализует поля блока «Финансовые данные» по явным формулировкам.

        Исправляет известные баги: неустойка тянула основной долг/мусор; даты ПП
        (депозит/госпошлина) не извлекались; одна госпошлина дублировалась в
        банкротную и ссудную; госпошлина = итог/мусор; итог < основного долга.
        """
        if not text:
            return
        money = r"(\d[\d   ]*(?:[.,]\s?\d{1,2})?)"
        amt = self._fin_amount
        fmt = self._fin_fmt

        total = amt(fields.get("totalDebt"))
        principal = amt(fields.get("principalDebt") or fields.get("loanDebt") or fields.get("principalDebt13"))
        interest = amt(fields.get("interest") or fields.get("interest14"))

        # Текст в одну строку — суммы ищем рядом с ключевым словом.
        flat = re.sub(r"\s+", " ", text)
        # Сумма ОБЯЗАТЕЛЬНО со словом «руб» (опц. маркер вида [15]); это отсекает
        # проценты ставок («0,1 % за день») и номера статей/пунктов.
        amount_kw = money + r"\s*(?:\[\d+\])?\s*руб"


        neu = {"principal": {}, "interest": {}, "single": {}}
        for m in re.finditer(r"неустойк\w*([^\d]{0,55}?)" + amount_kw, flat, re.IGNORECASE):
            label = m.group(1).lower()
            val = amt(m.group(2))
            if val <= 0:
                continue
            if "основн" in label and "долг" in label:
                bucket = "principal"
            elif "процент" in label:
                bucket = "interest"
            else:
                bucket = "single"
            neu[bucket][round(val, 2)] = val  # дедуп по значению (строки повторяются)
        forfeit_val = None
        if neu["principal"] or neu["interest"]:
            forfeit_val = sum(neu["principal"].values()) + sum(neu["interest"].values())
        elif neu["single"]:
            # Берём максимум, чтобы случайный мелкий «остаток» из шаблонной оговорки
            # не суммировался с реальной неустойкой.
            forfeit_val = max(neu["single"].values())
        if forfeit_val and forfeit_val > 0 and (total <= 0 or forfeit_val <= total + 0.01):
            fields["forfeit"] = fmt(forfeit_val)
            fields["forfeit15"] = fmt(forfeit_val)

        # --- Штрафные санкции (penalties) — только явные «штраф»/«пени» ---
        pen = {}
        for m in re.finditer(r"(?:штраф\w*|пени|пеня|пеней)([^\d]{0,40}?)" + amount_kw, flat, re.IGNORECASE):
            label = m.group(1).lower()
            if "неустойк" in label or "госпошл" in label or "пошлин" in label:
                continue
            val = amt(m.group(2))
            if val > 0:
                pen[round(val, 2)] = val
        if pen:
            pen_val = sum(pen.values())
            if total <= 0 or pen_val <= total:
                fields["penalties"] = fmt(pen_val)

        # --- Даты платёжных поручений: депозит [80] и госпошлина [81] ---
        for raw in text.splitlines():
            low = raw.lower()
            if "поручени" not in low:
                continue
            dm = re.search(r"от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})", raw)
            if not dm:
                continue
            date_val = dm.group(1).replace(",", ".")
            if "депозит" in low:
                if not fields.get("ppDepositDate80"):
                    fields["ppDepositDate80"] = date_val
            elif "госпошл" in low or "государственной пошл" in low or "государственную пошл" in low:
                if not fields.get("ppStateDutyDate81"):
                    fields["ppStateDutyDate81"] = date_val

        # --- Госпошлина: банкротная [16] / ссудная [17] — СЕМАНТИЧЕСКИ ---
        sd16 = amt(fields.get("stateDuty16") or fields.get("stateDuty"))
        sd17 = amt(fields.get("loanStateDuty17"))

        def duty_is_garbage(v: float) -> bool:

            if v <= 0:
                return False
            if total > 0 and v > 100000 and (abs(v - total) < 0.01 or v >= total * 0.4):
                return True
            if principal > 0 and v > 100000 and abs(v - principal) < 0.01:
                return True
            return False

        def plausible_duty(v: float) -> bool:
            return v >= 100 and not duty_is_garbage(v)

        def classify_duty(ctx: str):
            """Тип госпошлины по формулировке: (банкротная, ссудная)."""
            bank = (
                ("за подачу" in ctx and "заявлен" in ctx)
                or "о банкротстве" in ctx
                or "о несостоятельн" in ctx
                or ("о признании" in ctx and ("банкрот" in ctx or "несостоятельн" in ctx))
                or ("за рассмотрение заявлен" in ctx and ("банкрот" in ctx or "несостоятельн" in ctx))
            )
            loan = (
                # Основы слов — устойчивы к падежам («судебных расходов по уплате»).
                ("судебн" in ctx and "расход" in ctx)
                or ("расход" in ctx and "уплат" in ctx)
                or ("уплаченн" in ctx and "пошлин" in ctx)
                or "по иску" in ctx
                or "за рассмотрение исков" in ctx
                or "за рассмотрение требован" in ctx
            )
            return bank, loan

        # Сканируем суммы рядом со словом «госпошлина/пошлина/судебные расходы»
        # в ОБОИХ порядках (ключ сумма и сумма ключ) и классифицируем по контексту.
        sem_bankrupt = 0.0
        sem_loan = 0.0
        duty_patterns = (
            r"(?:госпошлин\w*|государственн\w+\s+пошлин\w*)[^\d]{0,40}?" + amount_kw,
            amount_kw + r"[^\d]{0,40}?(?:госпошлин\w*|пошлин\w*|судебн\w+\s+расход\w*)",
        )
        for pat in duty_patterns:
            for m in re.finditer(pat, flat, re.IGNORECASE):
                val = amt(m.group(1))
                if not plausible_duty(val):
                    continue
                ctx = flat[max(0, m.start() - 80): m.end() + 60].lower()
                is_bank, is_loan = classify_duty(ctx)
                if is_bank and not is_loan:
                    sem_bankrupt = max(sem_bankrupt, val)
                elif is_loan and not is_bank:
                    sem_loan = max(sem_loan, val)

        if sem_bankrupt > 0 or sem_loan > 0:
            # Есть явные формулировки раскладываем типо-эксклюзивно.
            if sem_bankrupt > 0:
                fields["stateDuty16"] = fmt(sem_bankrupt)
                fields["stateDuty"] = fmt(sem_bankrupt)
                sd16 = sem_bankrupt
            else:
                fields.pop("stateDuty16", None)
                fields.pop("stateDuty", None)
                sd16 = 0.0
            if sem_loan > 0:
                fields["loanStateDuty17"] = fmt(sem_loan)
                sd17 = sem_loan
            else:
                fields.pop("loanStateDuty17", None)
                sd17 = 0.0
        elif duty_is_garbage(sd16):
            # Меток нет, но текущее значение — мусор: переизвлекаем правдоподобное.
            cap = total * 0.3 if total > 0 else float("inf")
            cands = [
                amt(m.group(1))
                for m in re.finditer(
                    r"(?:госпошлин\w*|государственн\w+\s+пошлин\w*)[^\d]{0,40}?" + amount_kw,
                    flat, re.IGNORECASE,
                )
                if 0 < amt(m.group(1)) < cap
            ]
            if cands:
                best = max(cands)
                fields["stateDuty16"] = fmt(best)
                fields["stateDuty"] = fmt(best)
                sd16 = best
            else:
                fields.pop("stateDuty16", None)
                fields.pop("stateDuty", None)
                sd16 = 0.0

        # Микро-значения (< 100 руб) — это не госпошлина (реальная всегда сотни+).
        if 0 < sd16 < 100:
            fields.pop("stateDuty16", None)
            fields.pop("stateDuty", None)
            sd16 = 0.0
        if 0 < sd17 < 100:
            fields.pop("loanStateDuty17", None)
            sd17 = 0.0
        # Одна и та же госпошлина не может быть и банкротной, и ссудной.
        if sd17 > 0 and sd16 > 0 and abs(sd16 - sd17) < 0.01:
            fields.pop("loanStateDuty17", None)
            sd17 = 0.0

        # --- Общая сумма долга: если итог явно меньше основного долга — пересобираем ---
        if total > 0 and principal > 0 and total < principal:
            forfeit_now = amt(fields.get("forfeit"))
            composite = principal + interest + forfeit_now
            if composite > 0:
                fields["totalDebt"] = fmt(composite)

    def _safe_amount_field(self, value: Optional[Union[str, float, int]]) -> float:
        """
        Безопасно приводит поле суммы к float.
        """
        if value is None:
            return 0.0
        try:
            if isinstance(value, (int, float)):
                return float(value)
            s = str(value).strip()
            if not s:
                return 0.0
            normalized = self.normalize_amount_value(s)
            return float(normalized.replace(" ", "").replace(",", "."))
        except Exception:
            return 0.0

    def _reconcile_debt_amounts(self, extracted_fields, text, document_type):
        """Согласование сумм долга: подстановка principalDebt/interest/forfeit из [13]/[14]/[15], коррекция totalDebt, госпошлина из ИТОГО, фолбэк loanDebt. Вынесено из extract_fields."""
        # Заменяем старые поля долгов на правильные суммы из блока "ПРОСИТ СУД"
        if 'principalDebt13' in extracted_fields:
            extracted_fields['principalDebt'] = extracted_fields['principalDebt13']
            logger.info(f"Заменено поле principalDebt на {extracted_fields['principalDebt13']}")

        if 'interest14' in extracted_fields:
            extracted_fields['interest'] = extracted_fields['interest14']
            logger.info(f"Заменено поле interest на {extracted_fields['interest14']}")

        if 'forfeit15' in extracted_fields:
            extracted_fields['forfeit'] = extracted_fields['forfeit15']
            logger.info(f"Заменено поле forfeit на {extracted_fields['forfeit15']}")

        # Если общая сумма долга похожа на сумму выдачи (значительно больше основной+проценты+неустойка),
        # подменяем на сумму principal+interest+forfeit
        try:
            principal_raw = extracted_fields.get("principalDebt")
            # Основной долг живёт в двух полях: principalDebt (из блока «ПРОСИТ СУД»)
            # и loanDebt («Ссудная задолженность» из таблицы расчёта). Раньше здесь
            # смотрели только на первое, и когда основной долг попадал во второе,
            # «сумма частей» сводилась к одним процентам — общий долг подменялся
            # процентами (заявление Манукян: [12] и [14] оба 2 438 262,70).
            if not str(principal_raw or "").strip():
                principal_raw = extracted_fields.get("loanDebt")
            principal_f = float(self.normalize_amount_value(str(principal_raw or "0")).replace(" ", "").replace(",", "."))
            interest_f = float(self.normalize_amount_value(str(extracted_fields.get("interest") or "0")).replace(" ", "").replace(",", "."))
            forfeit_f = float(self.normalize_amount_value(str(extracted_fields.get("forfeit") or "0")).replace(" ", "").replace(",", "."))
            sum_pif = principal_f + interest_f + forfeit_f
            if sum_pif > 0:
                total_str = (extracted_fields.get("totalDebt") or "").strip()
                if total_str:
                    total_f = float(self.normalize_amount_value(total_str).replace(" ", "").replace(",", "."))
                    # Когда известны и основной долг, и проценты, общая сумма обязана
                    # равняться их сумме: резолютивка пишет «в размере [12] руб., из
                    # них [13] основного долга, [14] процентов», и части не могут не
                    # сходиться с целым. Госпошлина в [12] не входит — она взыскивается
                    # отдельным пунктом ([16]), поэтому «ИТОГО» из таблицы расчёта,
                    # включающее пошлину, здесь не годится.
                    both_components_known = principal_f > 0 and interest_f > 0
                    mismatch = abs(total_f - sum_pif) > 0.01
                    if total_f > sum_pif * 1.15 or (both_components_known and mismatch):
                        formatted_sum = f"{sum_pif:,.2f}".replace(",", " ").replace(".", ",")
                        extracted_fields["totalDebt"] = formatted_sum
                        if extracted_fields.get("debtAmount") == extracted_fields.get("totalDebt") or not extracted_fields.get("debtAmount"):
                            extracted_fields["debtAmount"] = formatted_sum
                        logger.info(f"Общая сумма долга скорректирована на сумму основного долга+проценты+неустойка: {formatted_sum}")
        except (ValueError, TypeError) as e:
            logger.debug(f"Проверка суммы долга: {e}")


        try:
            if document_type == "rtk_application" and not extracted_fields.get("stateDuty"):
                lower_text = text.lower()
                if "госпошл" in lower_text or "государственной пошл" in lower_text:
                    principal = self._safe_amount_field(extracted_fields.get("principalDebt"))
                    interest = self._safe_amount_field(extracted_fields.get("interest"))
                    forfeit_val = self._safe_amount_field(extracted_fields.get("forfeit"))
                    composite = principal + interest + forfeit_val
                    if composite > 0:
                        itogo_match = re.search(
                            r"ИТОГО\s*[–—-]?\s*([0-9\s,]+)\s*(?:руб|рублей|₽|р\.?)",
                            text,
                            re.IGNORECASE,
                        )
                        if itogo_match:
                            itogo_val = self._safe_amount_field(itogo_match.group(1))
                            if itogo_val > composite:
                                duty = round(itogo_val - composite, 2)
                                formatted_duty = f"{duty:,.2f}".replace(",", " ").replace(".", ",")
                                extracted_fields["stateDuty"] = formatted_duty
                                formatted_total = f"{itogo_val:,.2f}".replace(",", " ").replace(".", ",")
                                extracted_fields["totalDebt"] = formatted_total
                                logger.info(
                                    f"Определена госпошлина из блока 'ИТОГО': {formatted_duty}, totalDebt={formatted_total}"
                                )
        except Exception as e:
            logger.debug(f"Ошибка при попытке выделить госпошлину из 'ИТОГО': {e}")

        # Если ссудная задолженность (loanDebt) не найдена явно — используем общую сумму долга/требований.
        # Копируем ТОЛЬКО то, что реально сумма: источник на этом шаге каскада может
        # ещё содержать мусор (напр. «Арбитражный суд Ростовской области»), а чистят его
        # ПОЗЖЕ — копия мусора пережила бы чистку источника и уехала в поле «Ссудная
        # задолженность». Проверка типа здесь дешевле, чем разбирательство на выходе.
        if not extracted_fields.get("loanDebt"):
            for source in ("debtAmount", "totalDebt"):
                value = extracted_fields.get(source)
                if not value or field_contract.check_value("loanDebt", value):
                    continue
                extracted_fields["loanDebt"] = value
                logger.info(f"loanDebt не найден явно, используем {source} как loanDebt: {value}")
                break

    def _reconcile_state_duty(self, extracted_fields, text, document_type):
        """Согласование госпошлины и сумм: синхронизация stateDuty/[16], выделение из ИТОГО, удаление penalties, приоритет requirementsSum для rtk. Вынесено из extract_fields."""
        if 'stateDuty16' in extracted_fields:
            state_duty_value = str(extracted_fields['stateDuty16']).strip()
            # Совпадение с forfeit15 обычно значит, что stateDuty16 извлечён ошибочно
            if 'forfeit15' in extracted_fields and str(extracted_fields['forfeit15']).strip() == state_duty_value:
                logger.warning(f"stateDuty16 совпадает с forfeit15 ({state_duty_value}), возможно неправильное извлечение")
                del extracted_fields['stateDuty16']
            else:
                existing_state_duty = self._safe_amount_field(extracted_fields.get("stateDuty"))
                incoming_state_duty16 = self._safe_amount_field(extracted_fields.get("stateDuty16"))

                # Синхронизация stateDuty/stateDuty16:
                # - если stateDuty16 ненулевая она приоритетнее
                # - если stateDuty16 нулевая НЕ перезатираем уже найденную ненулевую stateDuty
                if incoming_state_duty16 > 0:
                    extracted_fields["stateDuty"] = extracted_fields["stateDuty16"]
                    logger.info(f"Заменено поле stateDuty на {extracted_fields['stateDuty16']}")
                elif existing_state_duty > 0 and incoming_state_duty16 <= 0:
                    # Держим корректное ненулевое значение; подхватываем его в [16] для генератора.
                    extracted_fields["stateDuty16"] = extracted_fields.get("stateDuty")
                    logger.info(
                        f"stateDuty16=0,00, но stateDuty ненулевая ({extracted_fields.get('stateDuty')}); сохраняем ненулевую госпошлину"
                    )
                else:
                    extracted_fields["stateDuty"] = extracted_fields["stateDuty16"]
                    logger.info(f"Заменено поле stateDuty на {extracted_fields['stateDuty16']}")

        # Если есть totalDebt и debtAmount, но нет stateDuty, а в тексте явно упоминаются
        # расходы по оплате государственной пошлины, пробуем вычислить госпошлину как разницу.
        try:
            if not extracted_fields.get("stateDuty") and extracted_fields.get("totalDebt") and extracted_fields.get("debtAmount"):
                lower_text = text.lower()
                if "госпошл" in lower_text or "государственной пошл" in lower_text:
                    total_f = self._safe_amount_field(extracted_fields.get("totalDebt"))
                    debt_f = self._safe_amount_field(extracted_fields.get("debtAmount"))
                    diff = round(total_f - debt_f, 2)
                    if diff > 0:
                        formatted = f"{diff:,.2f}".replace(",", " ").replace(".", ",")
                        extracted_fields["stateDuty"] = formatted
                        logger.info(f"Рассчитана государственная пошлина как разница totalDebt - debtAmount: {formatted}")
        except Exception as e:
            logger.debug(f"Ошибка при попытке вывести госпошлину из разницы сумм: {e}")

        # Прямой поиск фразы "расходы по оплате госпошлины ..." если stateDuty всё ещё не найден
        if not extracted_fields.get("stateDuty"):
            try:
                m = re.search(
                    r"расход[аов]*\s+по\s+оплате\s+госпошл[иы][нны]*[^\d]{0,40}([0-9\s,]+)\s*(?:руб|рублей|₽|р\.?)",
                    text,
                    re.IGNORECASE | re.DOTALL,
                )
                if not m:
                    m = re.search(
                        r"([0-9\s,]+)\s*(?:руб|рублей|₽|р\.?)[^\n]{0,80}расход[аов]*\s+по\s+оплате\s+госпошл[иы][нны]*",
                        text,
                        re.IGNORECASE | re.DOTALL,
                    )
                if m:
                    extracted_fields["stateDuty"] = self.normalize_amount_value(m.group(1))
                    logger.info(f"Извлечена государственная пошлина из прямой фразы: {extracted_fields['stateDuty']}")
            except Exception as e:
                logger.debug(f"Ошибка при прямом поиске госпошлины: {e}")

        if 'penalties' in extracted_fields:
            del extracted_fields['penalties']
            logger.info("Удалено поле penalties - в заявлении нет штрафных санкций")

        amount_keys = [
            "debtAmount",
            "requirementsSum",
            "totalDebt",
            "principalDebt13",
            "interest14",
            "forfeit15",
            "stateDuty16",
            "loanStateDuty17",
            "principalDebt",
            "interest",
            "forfeit",
            "stateDuty",
            "bankCommission",
        ]
        for key in amount_keys:
            if key in extracted_fields and isinstance(extracted_fields[key], str):
                extracted_fields[key] = self.normalize_amount_value(extracted_fields[key])

        # Для rtk_application приоритет — requirementsSum, а не фраза "в размере …"
        # (та часто про госпошлину): если totalDebt = госпошлине или заметно меньше
        # requirementsSum, подменяем totalDebt/debtAmount.
        if document_type == "rtk_application":
            try:
                req_sum_val = self._safe_amount_field(extracted_fields.get("requirementsSum"))
                total_val = self._safe_amount_field(extracted_fields.get("totalDebt"))
                state_duty_val = self._safe_amount_field(
                    extracted_fields.get("stateDuty16") or extracted_fields.get("stateDuty")
                )

                if req_sum_val > 0:
                    should_override_total = False
                    if total_val == 0:
                        should_override_total = True
                    elif state_duty_val > 0 and abs(total_val - state_duty_val) < 0.01:
                        # totalDebt совпал с госпошлиной — это почти наверняка ошибка извлечения
                        should_override_total = True
                    elif total_val < req_sum_val * 0.5:
                        # totalDebt значительно меньше суммы требований — тоже подозрительно
                        should_override_total = True

                    if should_override_total:
                        formatted_req = f"{req_sum_val:,.2f}".replace(",", " ").replace(".", ",")
                        extracted_fields["totalDebt"] = formatted_req
                        extracted_fields["debtAmount"] = formatted_req
                        logger.info(
                            f"Для rtk_application totalDebt/debtAmount скорректированы по сумме требований: {formatted_req}"
                        )
            except Exception as e:
                logger.debug(f"Ошибка при коррекции totalDebt для rtk_application: {e}")

