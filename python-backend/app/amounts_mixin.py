# -*- coding: utf-8 -*-
import logging
import re
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class AmountsMixin:

    def normalize_amount_value(self, value: str) -> str:
        """
        Приводит строку с денежной суммой к виду '4 111 142,81'
        """
        if not value:
            return value

        # Убираем неразрывные пробелы и слова "руб.", "рублей", "₽", "р."
        cleaned = value.replace("\u202f", " ").replace("\xa0", " ")
        cleaned = re.sub(r'(?:руб(?:\.|лей)?|₽|р\.?)', "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        # Оставляем только цифры, пробелы и разделители
        cleaned = re.sub(r"[^0-9,.\s]", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)

        # Убираем ведущие разделители
        cleaned = re.sub(r"^[,.\s]+", "", cleaned)
        if not cleaned:
            return cleaned

        # Подготовка к парсингу числа
        tmp = cleaned.replace(" ", "")
        has_comma = "," in tmp
        has_dot = "." in tmp

        if has_comma and has_dot:
            # Если есть и запятая, и точка, считаем, что ЗАПЯТАЯ — разделитель копеек
            # Пример: '1.234.567,89' или иные артефакты PDF
            if tmp.rfind(",") > tmp.rfind("."):
                tmp = tmp.replace(".", "")
                tmp = tmp.replace(",", ".")
            else:
                # Редкий случай, когда точка стоит правее запятой — считаем точку десятичным
                tmp = tmp.replace(",", "")
        else:
            # Только запятая или только точка
            tmp = tmp.replace(",", ".")

        # Оставляем только одну десятичную точку
        tmp = re.sub(r"[^0-9.]", "", tmp)
        parts = tmp.split(".")
        if len(parts) > 2:
            tmp = parts[0] + "." + "".join(parts[1:])

        try:
            number = float(tmp)
        except Exception:
            # Если не смогли распарсить, возвращаем очищенную строку без изменения формата
            return cleaned

        # Форматируем как '1 234 567,89'
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

        # --- Основной долг [13] и проценты [14] по строкам из блока "ПРОСИТ СУД" ---
        # Линейный разбор надежнее широких regex по всему блоку и снижает риск,
        # когда проценты подменяются суммой основного долга.
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

        # --- Госпошлины/нотариальные тарифы из блока "ПРОСИТ СУД"/"ПРОШУ" ---
        # В заявлениях может быть две разные госпошлины (ссудная и банкротная),
        # поэтому мы их НЕ суммируем, а подставляем по отдельности в маркеры.
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

                money_matches = re.findall(money_pattern, line)
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

        # Убираем дубликаты, но сохраняем порядок
        unique_state_duty_values: List[str] = []
        for v in state_duty_values:
            if v not in unique_state_duty_values:
                unique_state_duty_values.append(v)
        state_duty_values = unique_state_duty_values

        # Если в блоке ПРОСИТ СУД нашли только нули, но ранее уже была
        # извлечена ненулевая госпошлина (например, из шапки "Госпошлина: ..."),
        # не перезаписываем корректное значение нулём.
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
                # Если ранее уже была извлечена крупная госпошлина (например 53 349),
                # а из блока "ПРОСИТ СУД" пришло подозрительно маленькое число (например 4,03),
                # не даём маленькому числу перезатереть корректное.
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
        # Санити-проверка кредитных параметров: иногда из-за шумных совпадений
        # в эти поля может попасть денежная сумма (например, госпошлина).
        term_raw = extracted_fields.get("creditTermMonths")
        if term_raw:
            term_digits = re.sub(r"\D", "", str(term_raw))
            term_value = int(term_digits) if term_digits else None
            # Реалистичный срок кредита в месяцах.
            if not term_value or term_value < 1 or term_value > 600:
                # В шаблонных документах между числом и единицей встречается
                # маркер вида [1001] ("на срок 36[1001] мес") — допускаем его,
                # иначе реальное значение терялось бы при перезахвате.
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

    def _apply_prayer_finances(self, fields: Dict[str, Any], text: str) -> None:
        """Финансы из ПРОСИТЕЛЬНОЙ части заявления («просим суд: …включить в реестр…»).

        По каждому обязательству (договору) в просительной части указана разбивка
        долга; обязательств может быть несколько. Суммируем по категориям:
          • основной долг  — «задолженность за просроченный кредит / ссудная / основной»;
          • проценты       — любые суммы со словом «процент»;
          • неустойка      — «неустойка / пени / штраф».
        Итог = сумма категорий. Подытоги обязательства («… в размере X, из которых:»)
        и госпошлина не классифицируются и в суммы не входят.

        Применяется ПОСЛЕ обычной нормализации и перекрывает её, только если в
        просительной части найдена хотя бы одна классифицируемая сумма.
        """
        if not text:
            return
        low = text.lower()
        start = -1
        # Приоритет — сама разбивка «…в размере TOTAL …, из которых:»: она может
        # стоять и в повествовании (ДО «ПРОСИТ СУД»), как в РТК-заявлениях.
        iz = low.find("из которых")
        if iz != -1:
            vm = low.rfind("в размере", max(0, iz - 120), iz)
            start = vm if vm != -1 else max(0, iz - 120)
        # Иначе — якорь по пунктам просительной части (для типа B).
        if start == -1:
            for anchor in ("включить в третью очередь", "включить в реестр требований",
                           "просим суд", "прошу суд", "просит суд"):
                i = low.find(anchor)
                if i != -1:
                    start = i
                    break
        if start == -1:
            return
        seg = text[start:]
        cut = re.search(r"\n\s*Приложени", seg, re.IGNORECASE)
        if cut:
            seg = seg[:cut.start()]

        # Убираем строки-номера страниц («…задолженность\n9\nпо процентам…»),
        # иначе они разрывают фразу-категорию и сумма теряет классификацию.
        seg = re.sub(r"\n[ \t]*\d{1,4}[ \t]*(?=\n)", "", seg)
        # Полная просительная часть (до возможной обрезки окна типа B) — нужна
        # для поиска банкротных госпошлин, которые стоят отдельными пунктами.
        prayer_full = seg

        # Применяем при одной из двух явных структур разбивки долга:
        #   A) «…в размере X, из которых: …» (итог заявлен) — с валидацией итога;
        #   B) «…X руб – основной долг, Y руб – неустойка …» (тире-категории, итога
        #      может не быть) — нужно ≥2 таких пунктов.
        # На простых заявлениях (плоский «ПРОСИТ СУД») финансы разбирает существующая
        # логика — туда не лезем, иначе категории «съезжают».
        has_iz = "из которых" in seg.lower()
        dash_cat_re = re.compile(
            r"\d[\d   ]*(?:,\d{2})?\s*руб[^–\-]{0,15}[–\-]\s*"
            r"(?:основн\w*\s+долг|ссудн\w*|процент\w*|неустойк\w*|штраф\w*|госпошлин\w*|пошлин\w*)",
            re.IGNORECASE,
        )
        dash_count = len(dash_cat_re.findall(seg))
        if not has_iz and dash_count < 2:
            return

        if not has_iz:
            # Тип B: окно разбора ограничиваем одним «долговым» пунктом — до
            # следующего пункта просительной части (Утвердить/Признать/Взыскать/
            # Установить/Ввести), иначе суммируются суммы из других пунктов/должников.
            b = re.search(
                r"\n\s*(?:\d+[.\)]\s*)?(?:Утвердить|Признать|Взыскать|Установить|Ввести)\b",
                seg[20:], re.IGNORECASE,
            )
            if b:
                seg = seg[: b.start() + 20]
            if len(dash_cat_re.findall(seg)) < 2:
                return

        amt_re = re.compile(
            r"(\d[\d   ]*(?:,\d{2})?)\s*руб(?:л\w*|\.)?\s*([^\d]{0,60})",
            re.IGNORECASE,
        )
        principal = interest = forfeit = loan_duty = 0.0
        hits = 0
        # Дедуп: одна и та же сумма в той же категории может встретиться дважды,
        # если разбивка продублирована (в повествовании И в «ПРОСИТ СУД»). Реальные
        # компоненты различаются до копеек, поэтому дубль по (категория,сумма) — это
        # повтор, а не второе обязательство.
        seen = set()
        for m in amt_re.finditer(seg):
            val = self._fin_amount(m.group(1))
            ph = m.group(2).lower()
            # Порядок важен: «неустойка за просроченные проценты» — это неустойка,
            # а не проценты; поэтому неустойку проверяем ПЕРВОЙ.
            if "неустой" in ph or "пени" in ph or "штраф" in ph:
                cat = "forfeit"
            elif "процент" in ph:
                cat = "interest"
            # Ссудная госпошлина — буллет ВНУТРИ разбивки («X руб – госпошлина»).
            elif "госпошл" in ph or "пошлин" in ph:
                cat = "loan_duty"
            # Осн. долг — только по явным формулировкам тела долга, НЕ по «кредитного
            # договора» (это отдельные обеспеченные требования «вытекающих из …»).
            elif ("основн" in ph or "ссудн" in ph or "просроченный кредит" in ph
                  or "просроченному кредиту" in ph):
                cat = "principal"
            else:
                continue
            key = (cat, round(val, 2))
            if key in seen:
                continue
            seen.add(key)
            if cat == "forfeit":
                forfeit += val
            elif cat == "interest":
                interest += val
            elif cat == "loan_duty":
                loan_duty += val
            else:
                principal += val
            hits += 1
        if hits == 0 or (principal + interest + forfeit) <= 0:
            return

        # Ссудная госпошлина входит в сумму долга (стоит в разбивке вместе с остальными).
        total = principal + interest + forfeit + loan_duty
        # Самоконтроль: применяем пересчёт ТОЛЬКО если итог реально заявлен в
        # документе как сумма (есть «…задолженность в размере <ИТОГ>…»). Иначе
        # структура разбивки нестандартная и сумма недостоверна — не трогаем.
        _strip_sp = lambda z: z.replace(" ", "").replace(" ", "").replace(" ", "")
        norm_text = _strip_sp(text)
        # Для типа A (есть «из которых» и заявленный итог) — самоконтроль: итог
        # должен присутствовать в тексте (целая часть; итог бывает прописью).
        # Для типа B (тире-категории) итог = сумма компонентов и в тексте может
        # не быть отдельной строкой — доверяем явной разбивке.
        if has_iz:
            int_part = str(int(total))
            if int_part not in norm_text:
                logger.info(f"💰 Просительная часть: итог {int_part} не подтверждён в тексте — пропуск")
                return

        if principal > 0:
            fields["principalDebt"] = self._fin_fmt(principal)
            fields["principalDebt13"] = fields["principalDebt"]
        fields["interest"] = self._fin_fmt(interest)
        fields["interest14"] = fields["interest"]
        fields["forfeit"] = self._fin_fmt(forfeit)
        fields["forfeit15"] = fields["forfeit"]
        fields["totalDebt"] = self._fin_fmt(total)
        fields["debtAmount"] = fields["totalDebt"]

        # Ссудная госпошлина: из разбивки (входит в долг). Если в разбивке её нет —
        # очищаем (она могла ошибочно прийти из общей логики).
        if loan_duty > 0:
            fields["loanStateDuty17"] = self._fin_fmt(loan_duty)
        else:
            fields.pop("loanStateDuty17", None)

        # Банкротная госпошлина — ОТДЕЛЬНЫЕ пункты «…расходы по уплате (государственной)
        # пошлины … в размере X…» (в сумму долга НЕ входят). Их может быть несколько
        # (напр. за рассмотрение заявления + за подачу) — СУММИРУЕМ все.
        bankr_duty = 0.0
        for bm in re.finditer(
            r"(?:гос)?пошлин\w*[^\d]{0,120}?в\s+размере\s+(\d[\d   ]*(?:,\d{2})?)\s*руб",
            prayer_full, re.IGNORECASE,
        ):
            bankr_duty += self._fin_amount(bm.group(1))
        if bankr_duty > 0:
            duty = self._fin_fmt(bankr_duty)
            fields["stateDuty16"] = duty
            fields["stateDuty"] = duty

        logger.info(
            f"💰 Финансы из просительной части: осн={fields.get('principalDebt')}, "
            f"проц={fields['interest']}, неуст={fields['forfeit']}, "
            f"ссуд.госп={fields.get('loanStateDuty17')}, банкр.госп={fields.get('stateDuty16')}, "
            f"итог={fields['totalDebt']}"
        )

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

        # --- Неустойка (forfeit / [15]) ---
        # Сумма привязана к слову «неустойка», метка между словом и числом
        # (≤55 симв.) задаёт тип: за осн. долг / за проценты / общая.
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
            # Госпошлина-мусор: совпадает с итогом/осн.долгом или это крупная доля
            # долга. Проверки «по доле» применяем только к КРУПНЫМ суммам (>100k):
            # реальная пошлина мала, а совпадение мелкой пошлины с (возможно неверным)
            # итогом — не повод её удалять (иначе теряем верные 4 000 / 2 000).
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
        # в ОБОИХ порядках (ключ→сумма и сумма→ключ) и классифицируем по контексту.
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
            # Есть явные формулировки → раскладываем типо-эксклюзивно.
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
            principal_f = float(self.normalize_amount_value(str(extracted_fields.get("principalDebt") or "0")).replace(" ", "").replace(",", "."))
            interest_f = float(self.normalize_amount_value(str(extracted_fields.get("interest") or "0")).replace(" ", "").replace(",", "."))
            forfeit_f = float(self.normalize_amount_value(str(extracted_fields.get("forfeit") or "0")).replace(" ", "").replace(",", "."))
            sum_pif = principal_f + interest_f + forfeit_f
            if sum_pif > 0:
                total_str = (extracted_fields.get("totalDebt") or "").strip()
                if total_str:
                    total_f = float(self.normalize_amount_value(total_str).replace(" ", "").replace(",", "."))
                    if total_f > sum_pif * 1.15:
                        formatted_sum = f"{sum_pif:,.2f}".replace(",", " ").replace(".", ",")
                        extracted_fields["totalDebt"] = formatted_sum
                        if extracted_fields.get("debtAmount") == extracted_fields.get("totalDebt") or not extracted_fields.get("debtAmount"):
                            extracted_fields["debtAmount"] = formatted_sum
                        logger.info(f"Общая сумма долга скорректирована на сумму основного долга+проценты+неустойка: {formatted_sum}")
        except (ValueError, TypeError) as e:
            logger.debug(f"Проверка суммы долга: {e}")

        # Для rtk_application с развернутым описанием сумм:
        # если в тексте есть "ИТОГО ... руб." и упоминание госпошлины,
        # пробуем выделить госпошлину как разницу между ИТОГО и (основной долг + проценты + просроченные проценты).
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
        if not extracted_fields.get("loanDebt"):
            if extracted_fields.get("debtAmount"):
                extracted_fields["loanDebt"] = extracted_fields["debtAmount"]
                logger.info(f"loanDebt не найден явно, используем debtAmount как loanDebt: {extracted_fields['loanDebt']}")
            elif extracted_fields.get("totalDebt"):
                extracted_fields["loanDebt"] = extracted_fields["totalDebt"]
                logger.info(f"loanDebt не найден явно, используем totalDebt как loanDebt: {extracted_fields['loanDebt']}")

    def _reconcile_state_duty(self, extracted_fields, text, document_type):
        """Согласование госпошлины и сумм: синхронизация stateDuty/[16], выделение из ИТОГО, удаление penalties, приоритет requirementsSum для rtk. Вынесено из extract_fields."""
        if 'stateDuty16' in extracted_fields:
            state_duty_value = str(extracted_fields['stateDuty16']).strip()
            # Проверяем, что это не неустойка (forfeit15 обычно имеет такое же значение)
            if 'forfeit15' in extracted_fields and str(extracted_fields['forfeit15']).strip() == state_duty_value:
                # Если stateDuty16 совпадает с forfeit15, это скорее всего ошибка извлечения
                logger.warning(f"stateDuty16 совпадает с forfeit15 ({state_duty_value}), возможно неправильное извлечение")
                # Удаляем неправильное значение
                del extracted_fields['stateDuty16']
            else:
                existing_state_duty = self._safe_amount_field(extracted_fields.get("stateDuty"))
                incoming_state_duty16 = self._safe_amount_field(extracted_fields.get("stateDuty16"))

                # Синхронизация stateDuty/stateDuty16:
                # - если stateDuty16 ненулевая → она приоритетнее
                # - если stateDuty16 нулевая → НЕ перезатираем уже найденную ненулевую stateDuty
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

        # Удаляем поле penalties, так как в заявлении нет штрафных санкций
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

        # Для rtk_application приоритетной является сумма требований (requirementsSum), а не общая фраза "в размере ...",
        # которая часто относится к госпошлине.
        # Если totalDebt совпадает с госпошлиной или заметно меньше суммы требований, подменяем totalDebt и debtAmount.
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

