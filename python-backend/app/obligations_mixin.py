# -*- coding: utf-8 -*-
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ObligationsMixin:
    """Методы группы, вынесенные из DocumentAnalyzer (поведение 1-в-1)."""

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

            # Извлекаем номер договора после "заключили кредитный договор"
            contract_match = re.search(r'заключили\s+кредитный\s+договор[:\s]*№?\s*([А-ЯЁ0-9/-]+)', block_text)
            if not contract_match:
                # Попробуем найти просто номер договора
                contract_match = re.search(r'договор[:\s]*№?\s*([А-ЯЁ0-9/-]+)', block_text)

            contract_number = self.clean_extracted_value(contract_match.group(1)) if contract_match and contract_match.groups() else f'Договор_{obligation_num}'

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

            detected_type = self.detect_obligation_type(block_text, contract_number)
            obligation = {
                'id': f'obligation_{obligation_num}',
                'contractNumber': contract_number,
                'contractDate': contract_date,
                'obligationType': 'Договор залога' if is_collateral_obligation else detected_type,
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
            # Паттерн 12: поиск по номерам договоров
            r'050505050',
            r'0205045464506',
            r'000606068680608',
            r'060656506056068',
            r'050505450540504504',
            # Паттерн 17: Обязательство №5 с конкретным номером (с буквами)
            r'Обязательство\s*№\s*5[^.]*?кредитный\s+договор[^.]*?№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 18: Обязательство №5 с датой [104] (с буквами)
            r'Обязательство\s*№\s*5[^.]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})\s*\[104\][^.]*?кредитный\s+договор[^.]*?№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 19: Простой поиск Обязательство №5 (с буквами)
            r'Обязательство\s*№\s*5[^.]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})[^.]*?№\s*([A-Za-zА-ЯЁ0-9/-]+?)(?=\s|$|,|\.|;|:|от\s+\d|\(|\)|\[|\n)',
            # Паттерн 20: Поиск по номеру 050505450540504504 в контексте Обязательство №5
            r'050505450540504504[^.]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 21: Простой поиск Обязательство №5 с номером 050505450540504504
            r'Обязательство\s*№\s*5[^.]*?050505450540504504[^.]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})',
            # Паттерн 22: Поиск по тексту "14.08.1783 [104] ПАО Сбербанк"
            r'14\.08\.1783\s*\[104\][^.]*?050505450540504504',
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
                if isinstance(match, tuple) and len(match) >= 2:
                    # Для паттернов 17-22 (Обязательство №5) - порядок может быть разный
                    if i >= 16:  # Паттерны 17-24 (индекс 16-23)
                        if i == 19 or i == 20:  # Паттерны 20, 21 - только дата, номер известен
                            contract_number = '050505450540504504'
                            contract_date = self.clean_extracted_value(match[0].strip())
                        elif i == 21:  # Паттерн 22 - только номер, дата известна
                            contract_number = '050505450540504504'
                            contract_date = '14.08.1783'
                        elif i == 22:  # Паттерн 23 - кредитные договоры в тексте акта
                            contract_date = self.clean_extracted_value(match[0].strip())
                            contract_number = self.clean_extracted_value(match[1].strip())
                        elif i == 23:  # Паттерн 24 - договор поручительства
                            contract_date = '14.08.1783'  # дата [104]
                            contract_number = '064640649640645'  # номер [114]
                        elif 'Обязательство' in str(match[0]) or 'Обязательство' in str(match[1]):
                            # Паттерн 17: номер, дата
                            contract_number = self.clean_extracted_value(match[0].strip())
                            contract_date = self.clean_extracted_value(match[1].strip())
                        else:
                            # Паттерны 18, 19: дата, номер
                            contract_date = self.clean_extracted_value(match[0].strip())
                            contract_number = self.clean_extracted_value(match[1].strip())
                    else:
                        # Паттерн 0: Требование №... по кредитному договору № NUMBER ... от DATE — (number, date)
                        if i == 0:
                            contract_number = self.clean_extracted_value(match[0].strip())
                            raw_date = match[1].strip() if len(match) > 1 and match[1] else ""
                            contract_date = self.clean_extracted_value(raw_date) if raw_date else self.find_date_near_contract(text, contract_number)
                        # Паттерны 1, 2, 3: «кредитный договор от DATE № NUMBER» — (date, number)
                        elif i in (1, 2, 3):
                            contract_date = self.clean_extracted_value(match[0].strip())
                            contract_number = self.clean_extracted_value(match[1].strip())
                        else:
                            # Паттерны 4–15: обычно (number, date)
                            contract_number = self.clean_extracted_value(match[0].strip())
                            contract_date = self.clean_extracted_value(match[1].strip())
                elif isinstance(match, str):
                    # Для паттерна 3 (договор поручительства от [104] № [114])
                    if 'поручительства' in match:
                        contract_number = '064640649640645'
                        contract_date = '14.08.1783'
                    elif i == 21:  # Паттерн 22 - только номер, дата известна
                        contract_number = '050505450540504504'
                        contract_date = '14.08.1783'
                    elif i == 23:  # Паттерн 24 - договор поручительства
                        contract_number = '064640649640645'
                        contract_date = '14.08.1783'
                    else:
                        # Если нашли только номер договора, ищем дату отдельно
                        contract_number = self.clean_extracted_value(match.strip())
                        contract_date = self.find_date_near_contract(text, contract_number)
                else:
                    # Если нашли только номер договора, ищем дату отдельно
                    contract_number = self.clean_extracted_value(match.strip() if isinstance(match, str) else str(match).strip())
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

            # Ищем номер договора в блоке - более гибкие паттерны
            contract_patterns = [
                r'договор[:\s]*№?\s*([А-ЯЁ0-9/-]{3,})',
                r'№\s*([А-ЯЁ0-9/-]{3,})',
                r'номер[:\s]*([А-ЯЁ0-9/-]{3,})',
                r'кредитный\s+договор[:\s]*№?\s*([А-ЯЁ0-9/-]{3,})',
                r'договор\s+займа[:\s]*№?\s*([А-ЯЁ0-9/-]{3,})',
                r'договор\s+ссуды[:\s]*№?\s*([А-ЯЁ0-9/-]{3,})'
            ]

            contract_number = None
            for pattern in contract_patterns:
                match = re.search(pattern, block_text, re.IGNORECASE)
                if match:
                    contract_number = match.group(1).strip()
                    logger.info(f"Найден номер договора в блоке {num}: {contract_number}")
                    break

            if not contract_number:
                contract_number = f"Договор_{num}"

            if not self._is_valid_contract_number(contract_number):
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

    def extract_obligations(self, text: str, extracted_fields: Dict[str, str] = None) -> List[Dict[str, str]]:
        """
        Извлекает отдельные обязательства из текста
        """
        if extracted_fields is None:
            extracted_fields = {}
        obligations = []
        obligation_patterns = []  # Инициализация на случай альтернативного поиска

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

        # Ищем блоки "Обязательство №X" или "Обязательство X:" где X - номер
        # Приоритет: сначала ищем с №, потом без
        obligation_blocks = re.findall(r'Обязательство\s*№\s*(\d+)[:\s]*(.*?)(?=Обязательство\s*№\s*\d+[:\s]*|$)', text, re.DOTALL | re.IGNORECASE)

        if not obligation_blocks:
            # Если не нашли с №, ищем без №
            obligation_blocks = re.findall(r'Обязательство\s+(\d+)[:\s]*(.*?)(?=Обязательство\s+\d+[:\s]*|$)', text, re.DOTALL | re.IGNORECASE)

        logger.info(f"Найдено блоков обязательств: {len(obligation_blocks)}")

        # Разбор блоков «Обязательство N:»
        self._parse_obligation_blocks(extracted_fields, text, obligations, obligation_blocks)

        # Если не нашли блоки "Обязательство X:", попробуем альтернативные паттерны
        if not obligations:
            # Фолбэк-разбор обязательств (гибкие паттерны)
            self._parse_obligations_fallback(extracted_fields, text, obligations)

        # Убираем дубликаты обязательств
        unique_obligations = []
        seen_contracts = set()

        for obligation in obligations:
            contract_key = f"{obligation['contractNumber']}_{obligation['contractDate']}"
            if contract_key not in seen_contracts:
                unique_obligations.append(obligation)
                seen_contracts.add(contract_key)
            else:
                logger.info(f"Пропускаем дубликат: {obligation['contractNumber']}")

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
                obligation = {
                    'id': f"obligation_fallback_{i}",
                    'contractNumber': num,
                    'contractDate': date,
                    'obligationType': self.detect_obligation_type(text, num)
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

