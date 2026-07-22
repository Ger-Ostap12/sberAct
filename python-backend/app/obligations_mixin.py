# -*- coding: utf-8 -*-
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ObligationsMixin:

    def _parse_obligation_blocks(self, extracted_fields, text, obligations, obligation_blocks):
        """Разбор блоков «Обязательство N:»: номер/дата договора, суммы, тип. Аппендит в obligations (по ссылке). Вынесено из extract_obligations."""
        for i, obligation_data in enumerate(obligation_blocks):
            # Проверяем формат данных
            if not isinstance(obligation_data, tuple) or len(obligation_data) < 2:
                logger.warning(f"Некорректный формат данных обязательства: {obligation_data}")
                continue

            obligation_num = obligation_data[0] if obligation_data[0] else str(i + 1)
            block_text = obligation_data[1] if len(obligation_data) > 1 and obligation_data[1] else ""

            if not block_text:
                logger.warning(f"Пустой блок текста для обязательства {obligation_num}")
                continue

            logger.info(f"Обрабатываем блок обязательства {obligation_num}: {block_text[:100] if len(block_text) > 100 else block_text}...")

            # Извлекаем дату из начала блока (первая дата в формате ДД.ММ.ГГГГ)
            date_match = re.search(r'(\d{1,2}[.,]\d{1,2}[.,]\d{4})', block_text)
            contract_date = date_match.group(1) if date_match and date_match.groups() else 'Не указана'

            # Извлекаем номер договора после "заключили кредитный договор".
            # Класс номера включает ЗАГЛАВНУЮ латиницу (номера вида
            # «5221L85XS2TR2Q0QG2UW3F»), иначе номер обрезается на первой латинской
            # букве. Строчные НЕ включаем — они срезают приклеенный предлог «о»
            # («…-2о предоставлении…» «…-2») сами по себе.
            contract_match = re.search(r'заключили\s+кредитный\s+договор[:\s]*№?\s*([A-ZА-ЯЁ0-9/-]+)', block_text)
            if not contract_match:
                # Эмиссионный контракт (возобновляемая кредитная линия кредитная
                # карта): «подписания эмиссионного контракт №99ТКПР…». Берём ДО
                # общего «договор №…», иначе на хвосте последнего блока (он тянется
                # до конца текста) ловится мусор вроде «договоромипотеки».
                contract_match = re.search(
                    r'эмиссионн\w*\s+контракт\w*\s*№?\s*([А-ЯЁ0-9/-]+)',
                    block_text, re.IGNORECASE)
            # Номер, разбитый ПРОБЕЛАМИ (Сбербанк, лимит кредитной линии): «договор
            # №6142027489 24 1 от …» = 6142027489-24-1. Склеиваем группы дефисом.
            # Проверяем ДО общего «договор №…», иначе тот возьмёт лишь базовую часть,
            # и все блоки с одинаковой базой схлопнутся в одно обязательство.
            space_num_raw = None
            if not contract_match:
                sm = re.search(r'договор\w*\s*№\s*(\d{6,}(?:\s+\d{1,4}){1,3})(?=\s+от\s+\d|[\s,;.]|$)', block_text)
                if sm:
                    space_num_raw = sm.group(1).strip()
            if not contract_match and not space_num_raw:
                # Просто номер договора (с ЗАГЛАВНОЙ латиницей, без строчных).
                contract_match = re.search(r'договор[:\s]*№?\s*([A-ZА-ЯЁ0-9/-]+)', block_text)

            if space_num_raw:
                contract_number = re.sub(r'\s+', '-', space_num_raw)
                num_for_type = space_num_raw  # в тексте номер с пробелами — по нему ищем тип
            else:
                contract_number = self.clean_extracted_value(contract_match.group(1)) if contract_match and contract_match.groups() else f'Договор_{obligation_num}'
                num_for_type = contract_number

            # Извлекаем сумму после "образовалась задолженность в размере"
            amount_match = re.search(r'образовалась\s+задолженность\s+в\s+размере[:\s]*([0-9\s,]+)\s*(?:руб|рублей|₽|р\.?)', block_text)
            if not amount_match:
                amount_match = re.search(r'образовалась\s+задолженность\s+в\s+размере[:\s]*([0-9\s,]+)', block_text)

            raw_amount = amount_match.group(1) if amount_match and amount_match.groups() else '0'
            normalized_amount_str = self.normalize_amount_value(raw_amount)
            obligation_amount_value = 0.0
            try:
                obligation_amount_value = float(normalized_amount_str.replace(' ', '').replace(',', '.'))
            except (ValueError, AttributeError):
                obligation_amount_value = 0.0
            # Сохраняем строковое значение, чтобы не потерять копейки
            obligation_amount = normalized_amount_str or '0'

            # Извлекаем сумму выдачи кредита из фразы "в сумме X рублей"
            issued_amount_match = re.search(r'в\s+сумме\s+([0-9\s,]+(?:[.,][0-9]+)?)\s*руб', block_text, re.IGNORECASE)
            issued_amount_value = 0.0
            issued_amount = None
            if issued_amount_match:
                issued_raw = issued_amount_match.group(1)
                issued_norm = self.normalize_amount_value(issued_raw)
                try:
                    issued_amount_value = float(issued_norm.replace(' ', '').replace(',', '.'))
                    issued_amount = issued_norm
                except (ValueError, AttributeError):
                    issued_amount_value = 0.0

            # Проверяем, является ли обязательство залоговым
            # Ищем упоминания залога в блоке обязательства
            is_collateral_obligation = False
            collateral_keywords = [
                r"залог",
                r"договор\s+залога",
                r"подтверждается\s+договором\s+залога",
                r"предоставил\s+в\s+залог",
                r"предоставляет\s+в\s+залог"
            ]
            for keyword in collateral_keywords:
                if re.search(keyword, block_text, re.IGNORECASE):
                    is_collateral_obligation = True
                    logger.info(f"Обязательство {obligation_num} определено как залоговое")
                    break

            # Если обязательство залоговое, извлекаем и суммируем неустойки
            penalty0071 = None
            penalty0071_value = 0.0
            if is_collateral_obligation:
                # Ищем все неустойки в блоке обязательства по слову "неустойка"
                # Гибкие паттерны для поиска любых неустоек:
                # - X руб. – неустойка ...
                # - неустойка ... X руб.
                # - неустойка ... в размере X руб.
                penalty_patterns = [
                    # Паттерн 1: сумма перед "– неустойка" или "— неустойка" или "- неустойка"
                    r"([0-9\s,]+(?:[.,][0-9]+)?)\s*руб\.?\s*[–—-]\s*неустойка",
                    # Паттерн 2: сумма после "неустойка" и перед "руб."
                    r"неустойка[^0-9]*?([0-9\s,]+(?:[.,][0-9]+)?)\s*руб\.?",
                    # Паттерн 3: "неустойка" и "в размере" X руб.
                    r"неустойка[^0-9]*?в\s+размере[:\s]*([0-9\s,]+(?:[.,][0-9]+)?)\s*руб\.?",
                    # Паттерн 4: неустойка ... X руб. (более общий)
                    r"неустойка[^.]*?([0-9\s,]+(?:[.,][0-9]+)?)\s*руб\.?",
                ]

                penalties = []
                found_matches = set()  # Для избежания дубликатов

                for pattern in penalty_patterns:
                    matches = re.finditer(pattern, block_text, re.IGNORECASE)
                    for match in matches:
                        if match.groups():
                            penalty_str = match.group(1).strip()
                            # Проверяем, не добавляли ли мы уже эту сумму
                            if penalty_str not in found_matches:
                                found_matches.add(penalty_str)
                                # Нормализуем сумму (убираем пробелы, заменяем запятую на точку)
                                normalized = penalty_str.replace(' ', '').replace(',', '.')
                                try:
                                    penalty_value = float(normalized)
                                    penalties.append(penalty_value)
                                    logger.info(f"Найдена неустойка в обязательстве {obligation_num}: {penalty_str} ({penalty_value})")
                                except ValueError:
                                    logger.warning(f"Не удалось преобразовать неустойку в число: {penalty_str}")

                # Суммируем все неустойки
                if penalties:
                    total_penalty = sum(penalties)
                    # Форматируем сумму: 1499.11 -> "1 499,11"
                    formatted_penalty = f"{total_penalty:,.2f}".replace(',', ' ').replace('.', ',')
                    penalty0071 = formatted_penalty
                    penalty0071_value = total_penalty
                    logger.info(f"Сумма неустоек в залоговом обязательстве {obligation_num}: {penalty0071} руб.")

            detected_type = self.detect_obligation_type(block_text, num_for_type)
            obligation = {
                'id': f'obligation_{obligation_num}',
                'contractNumber': contract_number,
                'contractDate': contract_date,
                'obligationType': detected_type,
                'amount': obligation_amount,
                'amountValue': obligation_amount_value,
                'issuedAmount': issued_amount if issued_amount else None,
                'issuedAmountValue': issued_amount_value,
                'isCollateral': is_collateral_obligation,
                'penalty0071': penalty0071,
                'penalty0071Value': penalty0071_value
            }

            obligations.append(obligation)
            logger.info(f"Создано обязательство {obligation_num}: {obligation}")

    def _parse_obligations_fallback(self, extracted_fields, text, obligations):
        """Фолбэк-разбор обязательств гибкими паттернами, когда блоки «Обязательство N:» не найдены. Аппендит в obligations (по ссылке). Вынесено из extract_obligations."""
        logger.info("Блоки 'Обязательство X:' не найдены, используем альтернативные паттерны")

        # Ищем паттерны для обязательств - более гибкие
        obligation_patterns = [
            # Паттерн 0: "Требование № 1 по кредитному договору №XXXXX ... от DD.MM.YYYY"
            r'Требовани[ея]\s*№\s*\d+\s+по\s+кредитному\s+договору\s+№\s*([A-Za-zА-ЯЁ0-9./-]+)(?:[^\n]{0,200}?\s+от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4}))?',
            # Паттерн 0: «кредитный договор от DATE № NOMER» и «договор поручительства от DATE № NOMER» (приоритет)
            r'кредитный\s+договор\s+от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})\s+№\s*([0-9А-ЯЁa-z/\-]+?)(?=\s|,|$|\.)',
            r'договор\s+поручительства\s+от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})\s+№\s*([0-9А-ЯЁa-z/\-]+?)(?=\s|,|$|\.)',
            # Паттерн 0.1: эмиссионный контракт №
            r'эмиссионный\s+контракт[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            r'эмисионного\s+контракта[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 0.2: Договор займа № / Договоров займа №
            r'Договор\s+займа[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            r'Договоров\s+займа[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 0.3: договор потребительского кредита №
            r'договор\s+потребительского\s+кредита[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 1: общий паттерн для кредитных договоров (с буквами)
            r'кредитный\s+договор[:\s]*от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 2: общий паттерн для кредитных договоров без даты (с буквами)
            r'кредитный\s+договор[:\s]*от\s+Не\s+указана[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 3: договор поручительства от [104] № [114]
            r'договор\s+поручительства[:\s]*от\s+\[104\]\s*№\s*\[114\]',
            # Паттерн 4: договор №123 от 01.01.2024 (с буквами)
            r'договор[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 5: кредитный договор №123 от 01.01.2024 (с буквами)
            r'кредитный\s+договор[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 6: договор займа №123 от 01.01.2024 (с буквами)
            r'договор\s+займа[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 8: Обязательство 1: договор №123 от 01.01.2024 (с буквами)
            r'обязательство\s+\d+[:\s]*[^.]*?договор[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 9: Обязательство 1: кредитный договор №123 от 01.01.2024 (с буквами)
            r'обязательство\s+\d+[:\s]*[^.]*?кредитный\s+договор[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 10: Обязательство 1: договор займа №123 от 01.01.2024 (с буквами)
            r'обязательство\s+\d+[:\s]*[^.]*?договор\s+займа[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 11: Обязательство 1: займ №123 от 01.01.2024 (с буквами)
            r'обязательство\s+\d+[:\s]*[^.]*?займ[:\s]*№?\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 11.1: "Банк и ФИО заключили Соглашение ... номер № XXXXX"
            r'(\d{1,2}[.,]\d{1,2}[.,]\d{4})\s+г\.\s+[^.\n]{0,200}?заключили\s+Соглашение[^.\n]{0,300}?номер\s+№\s*([A-Za-zА-ЯЁ0-9/-]+)',
            # Паттерн 11.2: общий вариант "заключили .* (договор|соглашение) ... номер № XXXXX"
            r'(\d{1,2}[.,]\d{1,2}[.,]\d{4})\s+г\.[^.\n]{0,200}?заключили[^.\n]{0,200}?(?:договор|соглашение)[^.\n]{0,200}?номер\s+№\s*([A-Za-zА-ЯЁ0-9/-]+)',
            # Паттерн 11.3: "Между ООО МФК ... и должником заключен договор займа № 107977878 от 2024-08-10 года"
            r'между\s+[^.\n]{0,200}?и\s+[^.\n]{0,200}?заключен\s+договор\s+займа\s+№\s*([A-Za-zА-ЯЁ0-9/-]+)[^.\n]{0,100}?от\s+(\d{4}-\d{2}-\d{2})',
            # Паттерн 17: Обязательство №5 с конкретным номером (с буквами)
            r'Обязательство\s*№\s*5[^.]*?кредитный\s+договор[^.]*?№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 18: Обязательство №5 с датой [104] (с буквами)
            r'Обязательство\s*№\s*5[^.]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})\s*\[104\][^.]*?кредитный\s+договор[^.]*?№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 19: Простой поиск Обязательство №5 (с буквами)
            r'Обязательство\s*№\s*5[^.]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})[^.]*?№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 23: поиск всех кредитных договоров в тексте акта (с буквами)
            r'кредитный\s+договор[:\s]*от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})[:\s]*№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 24: поиск договоров поручительства
            r'договор\s+поручительства[:\s]*от\s+\[104\]\s*№\s*\[114\]'
        ]

        logger.info(f"Ищем обязательства в тексте: {text[:500]}...")

        for i, pattern in enumerate(obligation_patterns):
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            logger.info(f"Паттерн {i+1} найден {len(matches)} совпадений")

            for j, match in enumerate(matches):
                # Обобщённо: что похоже на дату -> contract_date, остальное -> contract_number
                # (без привязки к индексам паттернов).
                if isinstance(match, (tuple, list)):
                    parts = [p for p in match if p and str(p).strip()]
                elif isinstance(match, str) and match.strip():
                    parts = [match]
                else:
                    parts = []
                contract_number = None
                contract_date = None
                for _p in parts:
                    _p = str(_p).strip()
                    if re.match(r'^\d{1,2}[.,]\d{1,2}[.,]\d{4}$|^\d{4}-\d{2}-\d{2}$', _p):
                        if not contract_date:
                            contract_date = self.clean_extracted_value(_p)
                    elif not contract_number:
                        contract_number = self.clean_extracted_value(_p)
                if contract_number and not contract_date:
                    contract_date = self.find_date_near_contract(text, contract_number)

                if self._is_valid_contract_number(contract_number):
                    obligation = {
                        'id': f"obligation_{i}_{j}",
                        'contractNumber': contract_number.strip(),
                        'contractDate': (contract_date or 'Не указана').strip(),
                        'obligationType': self.detect_obligation_type(text, contract_number)
                    }
                    obligations.append(obligation)
                    logger.info(f"Найдено обязательство: {obligation}")

    def _regenerate_obligations_from_blocks(self, extracted_fields, text, obligations):
        """Доп. поиск обязательств по блокам «Обязательство N:» гибкими паттернами, когда их мало (<5). Аппендит в obligations (по ссылке). Вынесено из extract_obligations."""
        # Ищем блоки "Обязательство X:" в тексте - более гибкий паттерн
        obligation_blocks = re.findall(r'обязательство\s+(\d+)[:\s]*(.*?)(?=обязательство\s+\d+|$)', text, re.IGNORECASE | re.DOTALL)
        logger.info(f"Найдено блоков обязательств (паттерн 1): {len(obligation_blocks)}")

        # Если не нашли, пробуем другой паттерн
        if not obligation_blocks:
            obligation_blocks = re.findall(r'обязательство\s+(\d+)[:\s]*(.*?)(?=\n\n|\nобязательство|\n[А-Я]|$)', text, re.IGNORECASE | re.DOTALL)
            logger.info(f"Найдено блоков обязательств (паттерн 2): {len(obligation_blocks)}")

        # Если все еще не нашли, пробуем найти по номерам
        if not obligation_blocks:
            # Ищем все вхождения "Обязательство" в тексте
            obligation_matches = re.findall(r'обязательство\s+(\d+)', text, re.IGNORECASE)
            logger.info(f"Найдено упоминаний 'Обязательство': {obligation_matches}")

            # Создаем блоки вручную
            for i, num in enumerate(obligation_matches):
                # Ищем текст после "Обязательство X:"
                pattern = rf'обязательство\s+{num}[:\s]*(.*?)(?=обязательство\s+\d+|$)'
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    obligation_blocks.append((num, match.group(1)))
                    logger.info(f"Создан блок обязательства {num}: {match.group(1)[:100]}...")

        logger.info(f"Итого найдено блоков обязательств: {len(obligation_blocks)}")

        for i, (num, block_text) in enumerate(obligation_blocks):
            logger.info(f"Обрабатываем блок обязательства {num}: {block_text[:200]}...")

            # Ищем номер договора в блоке. Ключевые слова — регистронезависимо
            # (scoped (?i:…)), а КЛАСС НОМЕРА — только заглавные (латиница+кириллица)
            # без глобального IGNORECASE, чтобы не приклеить строчный предлог «о»
            # («№…-2о предоставлении…» «…-2») и при этом ловить латиницу.
            contract_patterns = [
                r'(?i:договор)[:\s]*№?\s*([A-ZА-ЯЁ0-9/-]{3,})',
                r'№\s*([A-ZА-ЯЁ0-9/-]{3,})',
                r'(?i:номер)[:\s]*([A-ZА-ЯЁ0-9/-]{3,})',
                r'(?i:кредитный\s+договор)[:\s]*№?\s*([A-ZА-ЯЁ0-9/-]{3,})',
                r'(?i:договор\s+займа)[:\s]*№?\s*([A-ZА-ЯЁ0-9/-]{3,})',
                r'(?i:договор\s+ссуды)[:\s]*№?\s*([A-ZА-ЯЁ0-9/-]{3,})'
            ]

            contract_number = None
            for pattern in contract_patterns:
                match = re.search(pattern, block_text)
                if match:
                    contract_number = match.group(1).strip()
                    logger.info(f"Найден номер договора в блоке {num}: {contract_number}")
                    break

            if not contract_number:
                contract_number = f"Договор_{num}"

            if not self._is_valid_contract_number(contract_number):
                continue

            # Не добавляем повтор уже найденного договора. Этот проход из-за
            # IGNORECASE ловит «грязный» вариант «…-2о» (потерянный пробел приклеил
            # предлог «о» к «…-2»). Сравниваем по номеру без хвостовой строчной
            # буквы — тогда «…-2о» опознаётся как дубль «…-2».
            def _obl_key(s):
                return re.sub(r"[а-яё]$", "", (s or "").strip().lower())
            if any(_obl_key(contract_number) == _obl_key(o.get("contractNumber"))
                   for o in obligations):
                continue

            # Ищем дату в блоке - более гибкие паттерны
            date_patterns = [
                r'от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
                r'дата[:\s]*(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
                r'(\d{1,2}[.,]\d{1,2}[.,]\d{4})'
            ]

            contract_date = 'Не указана'
            for pattern in date_patterns:
                match = re.search(pattern, block_text, re.IGNORECASE)
                if match:
                    contract_date = match.group(1).strip()
                    logger.info(f"Найдена дата в блоке {num}: {contract_date}")
                    break

            # Определяем тип обязательства
            obligation_type = 'Кредитный договор'
            if 'залог' in block_text.lower():
                obligation_type = 'Договор залога'
            elif 'займ' in block_text.lower():
                obligation_type = 'Договор займа'
            elif 'ссуд' in block_text.lower():
                obligation_type = 'Договор ссуды'
            elif 'кредит' in block_text.lower():
                obligation_type = 'Кредитный договор'

            obligation = {
                'id': f"obligation_block_{num}",
                'contractNumber': contract_number,
                'contractDate': contract_date,
                'obligationType': obligation_type
            }
            obligations.append(obligation)
            logger.info(f"Найдено обязательство из блока {num}: {obligation}")

    _RU_MONTHS = {
        "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
        "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
    }

    def _normalize_obl_date(self, s):
        """«21 сентября 2023 г.» / «17.02.2023» «17.02.2023» (или None)."""
        if not s:
            return None
        s = s.strip()
        m = re.match(r"(\d{1,2})[.,](\d{1,2})[.,](\d{4})", s)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100:
                return f"{d:02d}.{mo:02d}.{y}"
            return None
        m = re.match(r'[«"“]?\s*(\d{1,2})\s*[»"”]?\s+([а-яё]+)\s+(\d{4})', s, re.IGNORECASE)
        if m:
            d, word, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            mo = next((v for k, v in self._RU_MONTHS.items() if word.startswith(k)), None)
            if mo and 1 <= d <= 31 and 1900 <= y <= 2100:
                return f"{d:02d}.{mo:02d}.{y}"
        return None

    @staticmethod
    def _entity_words(name):
        """Значимые слова наименования (без орг-формы/кавычек) для сравнения сторон."""
        s = (name or "").lower()
        s = re.sub(r"[«»\"'(),.]", " ", s)
        s = re.sub(
            r"\b(ооо|оао|зао|пао|ао|общество|с|ограниченной|ответственностью|"
            r"гмбх|gmbh|публичное|акционерное|компания|фирма|имени)\b", " ", s)
        return [w for w in s.split() if len(w) >= 3]

    @staticmethod
    def _stem_match(a, b):
        """Совпадение слов по основе (первые 5 букв) — устойчиво к падежам
        («БАЗОВ» «БАЗОВЫМ», «ГЕОРГИЙ» «ГЕОРГИЕМ»)."""
        return len(a) >= 4 and len(b) >= 4 and a[:5] == b[:5]

    def _debtor_is_borrower(self, text, debtor_words):
        """True, если должник = ЗАЁМЩИК документа (или «(далее – Заёмщик)» нет).
        False — если заёмщик ОТЛИЧАЕТСЯ от должника (должник — поручитель)."""
        if not debtor_words:
            return True
        m = re.search(r"\(\s*далее[^)]{0,40}?за[ёе]мщик", text, re.IGNORECASE)
        if not m:
            return True
        seg = re.sub(r"\s+", " ", text[max(0, m.start() - 70): m.start()])
        bw = self._entity_words(seg)
        if not bw:
            return True
        matched = sum(1 for d in debtor_words
                      if any(self._stem_match(d, b) for b in bw))
        return matched >= max(1, len(debtor_words) - 1)

    def _is_surety_bankruptcy(self, text, debtor_name):
        """True, если должник — ПОРУЧИТЕЛЬ (заёмщик документа ≠ должник)."""
        return not self._debtor_is_borrower(text, self._entity_words(debtor_name))

    def _declared_debtor_words(self, text):
        """Слова наименования должника из ОБЪЯВЛЕНИЯ в тексте: «<Наименование> …
        (далее – …Должник/Заёмщик/Поручитель…)». Надёжнее переданного debtorName
        (тот на момент разбора обязательств бывает мусорным/обрезанным). Нужно для
        пер-договорной проверки заёмщика. None — если объявления нет."""
        # Требуем в объявлении именно «Должник» (не просто «Заёмщик»): иначе поймаем
        # объявление стороннего заёмщика («…«Форте Хоум» (далее – Заемщик)…») вместо
        # должника. Наименование должника — последнее «…» перед этим «(далее …Должник)».
        m = re.search(
            r"«([^»]{2,70})»[^«»]{0,90}?\(\s*далее[^)]{0,60}?должник",
            text, re.IGNORECASE)
        if not m:
            return None
        return self._entity_words(m.group(1)) or None

    def _extract_obligations_primary(self, text, debtor_name=None, debtor_is_borrower=None,
                                     creditor_name=None):
        """Чистое извлечение обязательств по канону «<тип договора> … №NUM … от DATE».
        Поддерживает: слова между типом и №, номера с буквами, даты прописью.
        Отсекает «объявление о банкротстве»/«судебный приказ».

        ВАЖНО (заявления о банкротстве поручителя): кредитный договор/соглашение
        берём в обязательства, только если ЗАЁМЩИК = должник; если заёмщик другой
        (напр. кредит на иное ЮЛ, а должник лишь поручитель) — кредитный пропускаем.
        Договоры поручительства (они на должника) берём всегда. Признак
        debtor_is_borrower считается на ПОЛНОМ тексте (передаётся снаружи)."""
        debtor_words = self._entity_words(debtor_name)
        # СТРУКТУРНЫЙ режим (правило: у обязательства только договор берём его; договор
        # + договор поручительства берём поручительство) включаем ТОЛЬКО для интра-
        # групповых заявлений, где должник объявлен И ЗАЁМЩИКОМ, И ПОРУЧИТЕЛЕМ
        # («(далее – Заемщик, Поручитель, Должник)» — Перспектива/Форте): там у части
        # кредитов заёмщик — другая компания группы (должник по ним лишь поручитель), и
        # такие кредиты идут В ПАРЕ с договором поручительства. В обычных заявлениях
        # (потреб-кредит, один должник) этого нет — режим прежний, типы/номера не трогаем.
        _declared = self._declared_debtor_words(text)
        gate_strict = _declared is not None and bool(re.search(
            r"\(\s*далее[^)]*поручител[^)]*должник|\(\s*далее[^)]*должник[^)]*поручител",
            text, re.IGNORECASE))
        covered_credits = set()  # номера кредитов, покрытых договором поручительства (липко)
        # Если должник — ПОРУЧИТЕЛЬ (заёмщик документа ≠ должник), кредитные (на
        # заёмщика) исключаем, оставляем поручительства (на должника).
        if debtor_is_borrower is None:
            debtor_is_borrower = self._debtor_is_borrower(text, debtor_words)
        _date = r'[0-3]?\d[.,][01]?\d[.,]\d{4}|[«"“]?\s*[0-3]?\d\s*[»"”]?\s+[а-яё]+\s+\d{4}'
        rx = re.compile(
            r"((?:договор\w*\s+)?кредитн\w+\s+карт\w*|кредитн\w+\s+договор\w*|"
            r"договор\w*\s+потребительск\w+\s+кредит\w*|"
            r"потребительск\w+\s+кредит\w*|договор\w*\s+займа?|займ\w*|"
            r"договор\w*\s*поручительств\w*|эмиссионн\w+\s+контракт\w*|"
            r"договор\w*\s+ипотек\w*|кредитн\w+\s+соглашени\w*|"
            # Кредитные линии/рамочные (Т-Банк и др.): «Рамочный договор о предоставлении
            # кредитов», «Договор (невозобновляемой) кредитной линии». Тип «Кредитный
            # договор». Требуем «договор/рамочный» перед «кредитн… лини…», чтобы не ловить
            # описательные «предоставить кредитную линию» без номера. Берутся только если
            # ЗАЁМЩИК = должник (пер-договорная проверка стороны для интра-групповых).
            r"рамочн\w+\s+договор\w*\s+о\s+предоставлени\w+\s+кредит\w*|"
            r"договор\w*\s+невозобновляем\w+\s+кредитн\w+\s+лини\w*)"
            r"[^№\n]{0,80}?№\s*([A-Za-zА-ЯЁ0-9/.\-]{3,40}?)(?=\s*от\s+\d|[\s,;.)\]]|$)"
            r"(?:[^.\n]{0,40}?от\s+(" + _date + r"))?",
            re.IGNORECASE,
        )
        res, by_num = [], {}
        for m in rx.finditer(text):
            kind = m.group(1).lower()
            num = (m.group(2) or "").strip(" .,;")
            # Номер, разорванный пробелами/табами (pdf2docx): «№616100070855-24-
            # <таб>3П01» — хвост уходит в межномерный зазор, и все поручительства
            # схлопываются в один усечённый «…-24-». Если номер кончается на «-»/«/»,
            # дотягиваем продолжение (сегмент буквы+цифры) сразу за ним.
            if num.endswith(("-", "/")):
                cont = re.match(r"\s+([0-9]*[A-Za-zА-ЯЁ][0-9A-Za-zА-ЯЁ]*)",
                                text[m.end(2):m.end(2) + 20])
                if cont:
                    num += cont.group(1)
            # «№…-2о предоставлении…»: потерянный пробел (pdf2docx) приклеил предлог
            # «о» к номеру. Если номер кончается на «о», а дальше пробел+слово — это
            # предлог, отсекаем (реальные номера так не оканчиваются). После отсечки
            # «…-2о» схлопывается в уже найденный «…-2».
            if num.endswith("о") and re.match(r"\s+[а-яё]{3,}", text[m.end(2):m.end(2) + 10]):
                num = num[:-1]
            ctx = text[max(0, m.start() - 30):m.start()].lower()
            if "объявлен" in ctx or ("судебн" in ctx and "приказ" in ctx):
                continue
            # Договор цессии/уступки прав (требований) — не обязательство должника
            # (по нему банк лишь приобрёл право требования). Отсев по контексту
            # вокруг номера: «уступк»/«цесси»/суффикс «…/Ц-NN».
            wnd = text[max(0, m.start() - 40):m.end() + 110].lower()
            if "уступк" in wnd or "цесси" in wnd:
                continue
            if not self._is_valid_contract_number(num):
                continue
            # Отсев плейсхолдеров-болванок («5221RRRR241R») — 3+ одинаковых БУКВ
            # подряд. «XX» (2) допускаем: «03XX7P006» — реальный номер Альфы.
            # Цифровые повторы («500000000») тоже допускаем — это реальные номера.
            if re.search(r"([A-Za-zА-Яа-яЁё])\1{2,}", num):
                continue
            is_surety = "поручит" in kind
            # Правило (общее): договор поручителя берём всегда; кредит берём, ТОЛЬКО если
            # его заёмщик = должник. Заёмщик конкретного договора указан явно перед
            # «…заключ…»: «между Банком и <заёмщик> заключен <кредит> №…» / «<заёмщик>
            # (далее – Заемщик) заключено <кредит> №…». Если заёмщик — иное лицо (кредит
            # на другую компанию группы, а должник лишь поручитель) — кредит пропускаем,
            # берём отдельный договор поручительства. Так: Перспектива её Договор-1
            # (заёмщик=Перспектива, без поручителя) берём + 7 поручительств; Альфа/Форте
            # кредиты на «Форте Хоум/Металс» (заёмщик≠должник) отсекаем, остаются
            # поручительства. Имя должника — из объявления (надёжно), сравнение строгое
            # (полное совпадение наименования, а не общее «Форте»).
            if not is_surety:
                if gate_strict:
                    # Правило (по структуре обязательства): если в блоке ЭТОГО кредита
                    # (до следующего кредита с №) есть договор поручительства — обязательство
                    # покрыто поручителем, берём поручительство, кредит пропускаем; если
                    # поручителя в блоке нет — это кредит на самого должника, берём.
                    # Имя должника НЕ используем (устойчиво к похожим наименованиям группы).
                    tail = text[m.end(): m.end() + 1500]
                    nxt = re.search(
                        r"(?:кредитн\w+\s+договор|кредитн\w+\s+соглашени|"
                        r"рамочн\w+\s+договор\w*\s+о\s+предоставлени\w+\s+кредит|"
                        r"договор\w*\s+невозобновляем\w+\s+кредитн\w+\s+лини)[^№\n]{0,80}№",
                        tail, re.IGNORECASE)
                    block = tail[:nxt.start()] if nxt else tail
                    if re.search(r"договор\w*\s+поручительств\w*[^№\n]{0,60}№", block, re.IGNORECASE):
                        covered_credits.add(num)
                        continue
                    # Липкое покрытие: этот номер уже был покрыт поручителем в другом своём
                    # вхождении (договорная часть идёт раньше сжатого списка приложений).
                    if num in covered_credits:
                        continue
                elif debtor_words and not debtor_is_borrower:
                    # Прежнее поведение (не интра-групповое): должник — поручитель
                    # чужие кредиты не берём, поручительства берём.
                    continue
            date = self._normalize_obl_date(m.group(3))
            if not date:
                # Номер мог встречаться дважды (тело без даты + просительная с датой) —
                # ищем «<num> … от DATE» по ВСЕМУ тексту.
                dm = re.search(
                    re.escape(num) + r"[^.\n]{0,40}?от\s+(" + _date + r")",
                    text, re.IGNORECASE,
                )
                if dm:
                    date = self._normalize_obl_date(dm.group(1))
            if not date:
                # Формат «<DATE> <стороны> заключили <тип> №NUM» — дата стоит ПЕРЕД
                # типом (напр. поручительства Сбербанка по ИП: «…по Договору
                # 24.04.2024 ПАО … заключили договор поручительства №…»). Берём
                # ближайшую дату слева, но только если сегмент кончается «заключил…»
                # — это надёжный якорь даты заключения, а не случайной даты в тексте.
                pre = text[max(0, m.start() - 200):m.start()]
                if re.search(r"заключ\w*\s*$", pre):
                    bm = re.findall(r"(" + _date + r")", pre)
                    if bm:
                        date = self._normalize_obl_date(bm[-1])
            if not date:
                # Дата непосредственно ПЕРЕД номером: «… от DATE №NUM» (форма
                # Сбербанка: «…с АО САРМАТ" от 25.12.2024№052…»). Ищем строго рядом
                # с ЭТИМ номером, чтобы не подхватить чужую дату из окружения.
                dm2 = re.search(
                    r"от\s+(" + _date + r")\s*№?\s*" + re.escape(num),
                    text, re.IGNORECASE,
                )
                if dm2:
                    date = self._normalize_obl_date(dm2.group(1))
            typ = ("Кредитная карта" if "карт" in kind
                   else "Кредитный договор" if "кредит" in kind
                   else "Договор займа" if "займ" in kind
                   else "Договор поручительства" if "поручит" in kind
                   else "Кредитная карта" if "эмиссион" in kind
                   else "Договор ипотеки" if "ипотек" in kind
                   else "Договор")
            if num in by_num:
                if date and by_num[num]["contractDate"] == "Не указана":
                    by_num[num]["contractDate"] = date
                continue
            obj = {
                "id": f"obligation_p_{len(res)}",
                "contractNumber": num,
                "contractDate": date or "Не указана",
                "obligationType": typ,
            }
            by_num[num] = obj
            res.append(obj)
        return res

    def _extract_obligations_table(self, text, debtor_is_borrower=True):
        """Табличный формат (МТС-Банк и т.п.): столбец «Номер договора» со
        строками «<НОМЕР> от <ДАТА>». Номер не предварён словом-типом и содержит
        слэши (0004491788/13/06/24), поэтому ни канонический экстрактор, ни старый
        fallback (берёт только чисто цифровые) его не видят. Гейт — заголовок
        таблицы «Номер договора». Тип берём на уровне документа (фраза «кредитным
        договорам» Кредитный договор). Кредитные берём, только если должник —
        заёмщик (этот формат и есть кредит на должника)."""
        if not text or not re.search(r"номер\s+договора", text, re.IGNORECASE):
            return []
        if not debtor_is_borrower:
            return []
        typ = ("Кредитная карта" if re.search(r"кредитн\w+\s+карт", text, re.I)
               else "Кредитный договор" if re.search(r"кредитн\w+\s+договор", text, re.I)
               else "Договор займа" if re.search(r"договор\w*\s+займа|\bзайм", text, re.I)
               else "Договор")
        _date = r"[0-3]?\d[.,][01]?\d[.,]\d{4}"
        res, by_num = [], {}
        for m in re.finditer(
            r"(?:№\s*)?([0-9A-ZА-ЯЁ][0-9A-ZА-ЯЁ/.\-]{4,39})\s+от\s*\n?\s*(" + _date + r")",
            text, re.IGNORECASE,
        ):
            num = m.group(1).strip(" .,;/")
            # Номер договора всегда содержит цифру (отсекает слова-ложные срабат.
            # «закона от 26.10.2002» из-за IGNORECASE по буквенному классу).
            if not re.search(r"\d", num):
                continue
            if not self._is_valid_contract_number(num):
                continue
            if num.isdigit() and len(num) >= 15:  # расчётный/корр. счёт, не договор
                continue
            ctx = text[max(0, m.start() - 40):m.start()].lower()
            if any(w in ctx for w in ("дело", "закон", "приказ", "пошлин",
                                      "поручени", "счет", "счёт")):
                continue
            date = self._normalize_obl_date(m.group(2))
            if num in by_num:
                if date and by_num[num]["contractDate"] == "Не указана":
                    by_num[num]["contractDate"] = date
                continue
            obj = {
                "id": f"obligation_t_{len(res)}",
                "contractNumber": num,
                "contractDate": date or "Не указана",
                "obligationType": typ,
            }
            by_num[num] = obj
            res.append(obj)
        return res

    def extract_obligations(self, text: str, extracted_fields: Dict[str, str] = None) -> List[Dict[str, str]]:
        """
        Извлекает отдельные обязательства из текста
        """
        if extracted_fields is None:
            extracted_fields = {}
        obligations = []
        obligation_patterns = []  # Инициализация на случай альтернативного поиска

        # Признак «должник = заёмщик» считаем на ПОЛНОМ тексте (до обрезки ниже):
        # обрезка по «Заявление» может удалить объявление «(далее – Заёмщик)».
        # ДОЛЖНИК — это debtorName (в «Заявление <Банк> о признании банкротом …»
        # applicantName = заявитель-кредитор, НЕ должник). Берём debtorName первым.
        _debtor0 = (extracted_fields.get("debtorName")
                    or extracted_fields.get("applicantName"))
        _debtor_is_borrower = self._debtor_is_borrower(text, self._entity_words(_debtor0))

        # Находим позицию начала заявления (после "Заявление", "Исковое заявление" и т.п.)
        # Обязательства должны извлекаться только после этого места
        statement_keywords = [
            r'заявление',
            r'исковое\s+заявление',
            r'заявление\s+о',
            r'исковое\s+заявление\s+о',
            r'заявление\s+в\s+суд',
            r'исковое\s+заявление\s+в\s+суд'
        ]

        statement_start_pos = 0
        for keyword in statement_keywords:
            match = re.search(keyword, text, re.IGNORECASE)
            if match:
                statement_start_pos = match.end()
                logger.info(f"Найдено начало заявления после '{match.group(0)}' на позиции {statement_start_pos}")
                break

        # Если нашли начало заявления, обрезаем текст до этой позиции
        if statement_start_pos > 0:
            text = text[statement_start_pos:]
            logger.info(f"Текст обрезан до позиции {statement_start_pos}, длина нового текста: {len(text)}")

        # Банкротство ПОРУЧИТЕЛЯ: обязательства должника — договоры поручительства
        # (на него), а не кредитные (на заёмщика). Берём их чистым экстрактором,
        # минуя блок-парсер (он вытащил бы кредитный договор заёмщика).
        _creditor0 = extracted_fields.get("creditorName")
        if not _debtor_is_borrower:
            primary = self._extract_obligations_primary(
                text, _debtor0, debtor_is_borrower=False, creditor_name=_creditor0)
            if primary:
                return self._dedupe_obligations(primary)

        # Ищем блоки "Обязательство №X" или "Обязательство X:" где X - номер
        # Приоритет: сначала ищем с №, потом без
        obligation_blocks = re.findall(r'Обязательство\s*№\s*(\d+)[:\s]*(.*?)(?=Обязательство\s*№\s*\d+[:\s]*|$)', text, re.DOTALL | re.IGNORECASE)

        if not obligation_blocks:
            # Если не нашли с №, ищем без №
            obligation_blocks = re.findall(r'Обязательство\s+(\d+)[:\s]*(.*?)(?=Обязательство\s+\d+[:\s]*|$)', text, re.DOTALL | re.IGNORECASE)

        logger.info(f"Найдено блоков обязательств: {len(obligation_blocks)}")

        # Разбор блоков «Обязательство N:»
        self._parse_obligation_blocks(extracted_fields, text, obligations, obligation_blocks)

        # Если не нашли блоки "Обязательство X:", сначала чистый канонический
        # экстрактор («<тип договора> №NUM от DATE»), и лишь если он пуст —
        # старые гибкие паттерны.
        if not obligations:
            primary = self._extract_obligations_primary(
                text, _debtor0, debtor_is_borrower=_debtor_is_borrower, creditor_name=_creditor0)
            if primary:
                obligations.extend(primary)
            else:
                # Табличный формат «Номер договора | … | RUR» (МТС-Банк и т.п.) —
                # номер голый, без слова-типа; обычные паттерны его не видят.
                table = self._extract_obligations_table(text, _debtor_is_borrower)
                if table:
                    obligations.extend(table)
                else:
                    self._parse_obligations_fallback(extracted_fields, text, obligations)

        # Убираем дубликаты обязательств. Один номер часто встречается с разными
        # разделителями (OCR грязных выписок: «У625/0055-0143478» и «У625/00550143478»)
        # — дедупим по номеру БЕЗ разделителей, оставляя первое (более каноничное,
        # с дефисами) представление и дотягивая дату, если у первого её не было.
        unique_obligations = []
        seen_norm: Dict[str, Dict[str, str]] = {}

        for obligation in obligations:
            key = re.sub(r"[\s/\-.]", "", obligation.get("contractNumber", "")).lower()
            if key not in seen_norm:
                seen_norm[key] = obligation
                unique_obligations.append(obligation)
            else:
                prev = seen_norm[key]
                if (prev.get("contractDate") in (None, "", "Не указана")
                        and obligation.get("contractDate") not in (None, "", "Не указана")):
                    prev["contractDate"] = obligation["contractDate"]
                logger.info(f"Пропускаем дубль-вариант: {obligation['contractNumber']}")

        obligations = unique_obligations

        # Договоры поручительства НЕ удаляем: если они присутствуют в заявлении, должны отображаться и подставляться в акты.

        # Если не нашли обязательства, создаем из найденных данных
        if not obligations:
            # Ищем номера договоров и даты в тексте
            contract_number_patterns = [
                r'задолженности?\s+по\s+договор[ау]\s+займа?\s+№\s*([А-ЯЁ0-9/\s-]{3,})',
                r'договор[:\s]*№?\s*([А-ЯЁ0-9/-]{3,})',
                r'номер договора[:\s]*([А-ЯЁ0-9/-]{3,})',
                r'№\s*([А-ЯЁ0-9/-]{3,})',
            ]

            contract_date_patterns = [
                r'от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
                r'дата[:\s]*(\d{1,2}[.,]\d{1,2}[.,]\d{4})'
            ]

            # Дату берём из ЛОКАЛЬНОГО контекста номера («№NUM от ДАТА» /
            # «№NUM, заключённому ДАТА»), а не из общего списка дат — иначе номеру
            # могла привязаться чужая дата (например, дата платёжного поручения).
            num_to_date = {}
            num_order = []
            for pattern in contract_number_patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    num = match.group(1).strip()
                    if not num or len(num) < 3:
                        continue
                    # Отфильтровываем номера судебных приказов: "судебный приказ № ..."
                    start = match.start(1)
                    context = text[max(0, start - 40):start].lower()
                    if "судебный" in context and "приказ" in context:
                        continue
                    # Исключаем платёжные поручения и госпошлину — это не договоры.
                    if any(w in context for w in ("поручение", "пошлин", "платёжн", "платежн", "квитанц")):
                        continue
                    # Документы-удостоверения: «Паспорт: серия 6018 № 402670»,
                    # «Свидетельством о браке/рождении/установлении отцовства серии
                    # I-АН №671711», актовые записи — их номера не обязательства
                    # (самобанкротные заявления, где паспорт должника в шапке).
                    # Окно шире 40: «Свидетельством о установлении отцовства серии …».
                    id_context = text[max(0, start - 75):start].lower()
                    if any(w in id_context for w in (
                            "паспорт", "свидетельств", "серия", "серии",
                            "снилс", "актовая запись", "удостоверени")):
                        continue
                    local = text[match.end(1): match.end(1) + 90]
                    dm = re.search(r'(?:от|заключ\w+)\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})', local, re.IGNORECASE)
                    date = dm.group(1).strip() if dm else None
                    if num not in num_to_date:
                        num_order.append(num)
                        num_to_date[num] = date
                    elif date and not num_to_date[num]:
                        num_to_date[num] = date

            # Создаем обязательства из найденных данных - фильтруем мусор
            valid_contracts = []
            for num in num_order:
                num_clean = (num or '').strip()
                # Отбрасываем явно мусорные и технические номера (счета, корр.счета и т.п.)
                if not self._is_valid_contract_number(num_clean):
                    continue
                # Игнорируем очень длинные чисто цифровые номера (расчетные/корр. счета)
                if num_clean.isdigit() and len(num_clean.replace(' ', '')) >= 15:
                    continue
                if num_clean.isdigit():
                    date = num_to_date.get(num) or 'Не указана'
                    valid_contracts.append((num_clean, date))
                    logger.info(f"Валидный номер договора: {num_clean} (дата: {date})")

            # Ограничиваем до 5 обязательств
            for i, (num, date) in enumerate(valid_contracts[:5]):
                obl_type = self.detect_obligation_type(text, num)
                # Правило Андрея: голый тип «Договор» в fallback-пути — мусор
                # (номера удостоверений/справок без кредитного контекста).
                # Настоящее обязательство здесь всегда даёт конкретный тип
                # (кредитный договор/карта/заём/поручительство/«Вид обязательства»).
                if obl_type == "Договор":
                    logger.info(f"Отсев fallback-обязательства №{num}: тип «Договор» без кредитного контекста")
                    continue
                obligation = {
                    'id': f"obligation_fallback_{i}",
                    'contractNumber': num,
                    'contractDate': date,
                    'obligationType': obl_type
                }
                obligations.append(obligation)
                logger.info(f"Создано обязательство из полей: {obligation}")

        # Дополнительно ищем обязательства по блокам "Обязательство X:"
        if not obligations or len(obligations) < 5:
            # Доп. поиск обязательств по блокам
            self._regenerate_obligations_from_blocks(extracted_fields, text, obligations)
        obligations = self._dedupe_obligations(obligations)
        logger.info(f"Всего найдено обязательств: {len(obligations)}")
        return obligations

    def _is_valid_contract_number(self, num: Optional[str]) -> bool:
        if not num:
            return False
        num_clean = str(num).strip()
        if len(num_clean) < 3:
            return False
        lower = num_clean.lower()
        if lower in {"путем", "подписания", "далее", "договор"}:
            return False
        if any(word in lower for word in ["считается", "поручительства", "фз", "а99", "0008008"]):
            return False
        digits_only = re.sub(r"\D", "", num_clean)
        # Номер договора ВСЕГДА содержит хотя бы одну цифру. Чисто буквенное
        # («Погашение», «Договор») — это не номер (OCR грязных выписок: «…договору
        # № Погашение обязательств по…»).
        if not digits_only:
            return False
        has_letters = bool(re.search(r"[A-Za-zА-Яа-яЁё]", num_clean))
        # Для чисто цифровых номеров ужесточаем критерий: короткие значения
        # (например, "168") чаще всего не являются номером договора.
        if not has_letters and digits_only == num_clean:
            if len(digits_only) < 5:
                return False
        return True

    def _dedupe_obligations(self, items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        deduped: List[Dict[str, str]] = []
        seen: set[str] = set()
        for item in items:
            number = (item.get("contractNumber") or "").strip()
            date = (item.get("contractDate") or "").strip()
            if not self._is_valid_contract_number(number):
                continue
            # Убираем дубли по номеру договора (дата может дублироваться/шуметь).
            key = number.lower()
            if key in seen:
                continue
            seen.add(key)
            if not date:
                item["contractDate"] = "Не указана"
            deduped.append(item)
        return deduped

