# -*- coding: utf-8 -*-
"""Рендер обязательств в документ (вынос без изменения поведения).

Заполнение блока обязательств: одиночное/множественное, таблицы, формат строки,
очистка неиспользованных маркеров. Внешние зависимости через self: docx-примитивы
(_collect_placeholders/_replace_*/_format_amount_value из DocxOpsMixin) и
clean_extracted_value (DocumentGenerator). Поведение 1-в-1 под gen-golden.
"""
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Union, cast

from docx.document import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

logger = logging.getLogger(__name__)


class ObligationsRenderMixin:
    if TYPE_CHECKING:
        def _collect_placeholders(self, doc: Document) -> Set[str]: ...
        def _replace_placeholder_in_doc(self, doc: Document, placeholder: str, value: str) -> bool: ...
        def _replace_regex_in_doc(
            self, doc: Document, pattern: str, replacement: Union[str, Callable[[re.Match], str]]
        ) -> bool: ...
        def _format_amount_value(self, value: float) -> str: ...
        def clean_extracted_value(self, value: str) -> str: ...

    def _cleanup_unused_obligation_placeholders(self, doc: Document, obligations: list):
        """
        Удаляет плейсхолдеры для обязательств, для которых нет данных.
        """
        obligations_count = len(obligations) if isinstance(obligations, list) else 0
        placeholders_in_doc = self._collect_placeholders(doc)
        unused_placeholders = []

        for placeholder in placeholders_in_doc:
            match = re.match(r"\[(\d+)\]", placeholder)
            if not match:
                continue

            number = int(match.group(1))
            slot_index: Optional[int] = None

            if 100 <= number < 110:
                slot_index = number - 100
            elif 110 <= number < 120:
                slot_index = number - 110
            elif 120 <= number < 130:
                slot_index = number - 120

            if slot_index is not None and slot_index >= obligations_count:
                unused_placeholders.append(placeholder)

        for placeholder in unused_placeholders:
            self._replace_placeholder_in_doc(doc, placeholder, "")

    def replace_obligations_data(self, doc: Document, data: Dict[str, Any]):
        """
        Заменяет данные об обязательствах (договорах) в документе

        Args:
            doc: Документ
            data: Данные с обязательствами
        """
        logger.info("Заменяем данные об обязательствах")

        obligations = data.get('obligations', [])
        if not obligations or not isinstance(obligations, list):
            logger.warning("Нет данных об обязательствах для замены")
            return

        logger.info(f"Найдено {len(obligations)} обязательств")
        credit_obligations = []
        for ob in obligations:
            if not isinstance(ob, dict):
                continue
            ob_type = str(ob.get("obligationType") or ob.get("type") or "").lower()
            if "залог" in ob_type:
                continue
            credit_obligations.append(ob)
        obligations = credit_obligations
        logger.info(f"Кредитных обязательств для шаблонного перечня: {len(obligations)}")

        # Номера полей для обязательств (динамические):
        # [100], [101], [102], [103], [104], [105], ... - даты договоров
        # [110], [111], [112], [113], [114], [115], ... - номера договоров

        # Для ипотеки проверяем, нужно ли поменять местами
        is_mortgage = (data.get("sourceDocumentType") or "").lower() == "mortgage_claim"
        obligations_count = len(obligations)

        # Считаем сумму выдачи по всем обязательствам (если есть issuedAmountValue)
        total_issued = 0.0
        for ob in obligations:
            try:
                total_issued += float(ob.get("issuedAmountValue", 0) or 0)
            except (TypeError, ValueError):
                continue

        # Собираем информацию о плейсхолдерах обязательств, реально присутствующих в шаблоне
        placeholders_in_doc = self._collect_placeholders(doc)
        available_slots: Set[int] = set()
        for placeholder in placeholders_in_doc:
            match = re.match(r"\[(\d+)\]", placeholder)
            if not match:
                continue
            number = int(match.group(1))
            slot_index: Optional[int] = None
            if 100 <= number < 110:
                slot_index = number - 100
            elif 110 <= number < 120:
                slot_index = number - 110
            elif 120 <= number < 130:
                slot_index = number - 120
            if slot_index is not None:
                available_slots.add(slot_index)

        max_slots = (max(available_slots) + 1) if available_slots else 0
        summary_placeholder = "[992]"
        has_summary_placeholder = summary_placeholder in placeholders_in_doc

        use_summary_mode = (
            has_summary_placeholder
            and obligations_count > 5
            and not max_slots
        )

        if use_summary_mode:
            # Заменяем длинный список договоров на единый маркер [992]
            intro_phrase = "В обоснование заявленных требований кредитор указал, что"

            def collapse_paragraphs(paragraphs):
                for paragraph in paragraphs:
                    text = paragraph.text
                    if intro_phrase in text and any(
                        marker in text
                        for marker in [
                            "[100]",
                            "[101]",
                            "[102]",
                            "[103]",
                            "[104]",
                            "[110]",
                            "[111]",
                            "[112]",
                            "[113]",
                            "[114]",
                        ]
                    ):
                        paragraph.text = summary_placeholder

            collapse_paragraphs(doc.paragraphs)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        collapse_paragraphs(cell.paragraphs)

            genitive_name = (
                data.get("applicantNameInstrumental")  # творительный падеж для [2.3]
                or data.get("applicantNameGenitive")
                or data.get("applicantName")
                or data.get("debtorName")
                or ""
            )
            summary_text = (
                "В обоснование заявленных требований кредитор указал, что между ПАО "
                f"Сбербанк и {genitive_name} (далее – должник) заключено "
                f"{obligations_count} обязательств на общую сумму "
                f"{self._format_amount_value(total_issued)}."
            )
            # Заполняем сводный маркер
            self._replace_placeholder_in_doc(doc, summary_placeholder, summary_text)
            # Чистим маркеры для индивидуальных обязательств (до 5)
            for idx in range(5):
                self._replace_placeholder_in_doc(doc, f"[{100 + idx}]", "")
                self._replace_placeholder_in_doc(doc, f"[{110 + idx}]", "")
        else:
            # Если сводный режим не используется, всегда очищаем [992], если он вдруг встречается
            self._replace_placeholder_in_doc(doc, summary_placeholder, "")

            if not is_mortgage and max_slots and obligations_count > max_slots:
                extra_entries = []
                for extra_obligation in obligations[max_slots:]:
                    if not isinstance(extra_obligation, dict):
                        continue
                    extra_number = (extra_obligation.get('contractNumber') or '').strip()
                    if extra_number.lower() in ('путем', 'подписания', 'далее', '') or len(extra_number) < 2:
                        continue
                    extra_date = (extra_obligation.get('contractDate') or '').strip()
                    extra_type = str(extra_obligation.get('obligationType') or extra_obligation.get('type') or '').lower()
                    if "поручитель" in extra_type:
                        extra_label = "договор поручительства"
                    elif "залог" in extra_type:
                        extra_label = "договор залога"
                    else:
                        extra_label = "кредитный договор"
                    entry = (
                        f"{extra_label} от {extra_date} № {extra_number}"
                        if extra_date else f"{extra_label} № {extra_number}"
                    )
                    extra_entries.append(entry)

                if extra_entries:
                    last_number_placeholder = f"[{110 + max_slots - 1}]"
                    extra_suffix = ", " + ", ".join(extra_entries)

                    def _append_after_marker(paragraphs):
                        for paragraph in paragraphs:
                            if last_number_placeholder in paragraph.text:
                                paragraph.text = paragraph.text.replace(
                                    last_number_placeholder, last_number_placeholder + extra_suffix
                                )

                    _append_after_marker(doc.paragraphs)
                    for table in doc.tables:
                        for row in table.rows:
                            for cell in row.cells:
                                _append_after_marker(cell.paragraphs)

        for i, obligation in enumerate(obligations):
            if not isinstance(obligation, dict):
                continue

            contract_date = (obligation.get('contractDate') or '').strip()
            contract_number = (obligation.get('contractNumber') or '').strip()
            # Не подставлять мусор вместо номера договора — тогда маркер останется и будет удалён с контекстом
            if contract_number.lower() in ('путем', 'подписания', 'далее', '') or len(contract_number) < 2:
                contract_number = ''
            obligation_type = obligation.get('obligationType') or obligation.get('type') or ''
            obligation_type_lower = obligation_type.lower()
            if "поручитель" in obligation_type_lower:
                type_label = "договор поручительства"
            elif "залог" in obligation_type_lower:
                type_label = "договор залога"
            else:
                type_label = "кредитный договор"

            if is_mortgage:
                # Для ипотеки: [100] - номер договора, [110] - дата договора
                if contract_number:
                    number_number = 100 + i  # 100, 101, 102, 103, 104, 105, ...
                    placeholder = f"[{number_number}]"
                    if self._replace_placeholder_in_doc(doc, placeholder, str(contract_number)):
                        logger.info(f"Заменено {placeholder} на {contract_number}")

                if contract_date:
                    date_number = 110 + i  # 110, 111, 112, 113, 114, 115, ...
                    placeholder = f"[{date_number}]"
                    if self._replace_placeholder_in_doc(doc, placeholder, str(contract_date)):
                        logger.info(f"Заменено {placeholder} на {contract_date}")
            else:
                # Для остальных: [100] - дата договора, [110] - номер договора
                if contract_date:
                    date_number = 100 + i  # 100, 101, 102, 103, 104, 105, ...
                    placeholder = f"[{date_number}]"
                    if self._replace_placeholder_in_doc(doc, placeholder, str(contract_date)):
                        logger.info(f"Заменено {placeholder} на {contract_date}")

                if contract_number:
                    number_number = 110 + i  # 110, 111, 112, 113, 114, 115, ...
                    placeholder = f"[{number_number}]"
                    value_to_put = str(contract_number)
                    # Если это договор поручительства, добавляем тип к номеру
                    if type_label == "договор поручительства":
                        value_to_put = f"{type_label} № {contract_number}"
                    if self._replace_placeholder_in_doc(doc, placeholder, value_to_put):
                        logger.info(f"Заменено {placeholder} на {value_to_put}")

                # Если в шаблоне явно указан «кредитный договор» перед маркером, подменяем на правильный тип
                if type_label != "кредитный договор":
                    type_pattern = f"{type_label}"
                    # заменяем текст «кредитный договор от [{date}] № [{number}]» на корректный тип
                    date_number = 100 + i
                    number_number = 110 + i
                    pattern = fr"кредитный\s+договор\s+от\s+\[{date_number}\]\s+№\s+\[{number_number}\]"
                    replacement = f"{type_label} от [{date_number}] № [{number_number}]"
                    self._replace_regex_in_doc(doc, pattern, replacement)

        # Обновляем текстовые блоки с перечислением обязательств, чтобы отразить все элементы
        skip_obligations = bool(data.get("_skip_obligation_blocks"))
        source_document_type_local = (data.get("sourceDocumentType") or "").lower()
        if not skip_obligations and source_document_type_local not in ["initiation_physical", "initiation_legal"]:
            self._update_obligation_paragraphs(doc, obligations)
        if not skip_obligations:
            self._cleanup_unused_obligation_placeholders(doc, obligations)

        slot_count = max_slots if max_slots else 5
        if not is_mortgage and obligations_count < slot_count:
            # Сначала удаляем текстовые куски для несуществующих обязательств
            for idx in range(obligations_count, slot_count):
                date_num = 100 + idx
                number_num = 110 + idx
                # Удаляем фразу "кредитный договор от [10X] № [11X]" вместе с возможной запятой и пробелами
                credit_pattern = rf"(?:,\s*)?кредитный\s+договор\s+от\s+\[{date_num}\]\s+№\s+\[{number_num}\]"
                self._replace_regex_in_doc(doc, credit_pattern, "")

            # Затем на всякий случай обнуляем сами маркеры
            for idx in range(obligations_count, slot_count):
                date_placeholder = f"[{100 + idx}]"
                number_placeholder = f"[{110 + idx}]"
                self._replace_placeholder_in_doc(doc, date_placeholder, "")
                self._replace_placeholder_in_doc(doc, number_placeholder, "")

            self._replace_regex_in_doc(
                doc,
                r"(?:,\s*)?кредитный\s+договор\s+от\s+№\s*(?!\d)(?:(?!основн|процент|неустой|госпошл|руб)[^,\.\n]){0,40}",
                ""
            )
            self._replace_regex_in_doc(
                doc,
                r"(?:,\s*)?договор\s+поручительства\s+от\s+№\s*(?!\d)(?:(?!основн|процент|неустой|госпошл|руб)[^,\.\n]){0,40}",
                ""
            )
            # Очистка фраз "по договору № от ," (пустые номера/даты договоров, не заполненные из заявления и интерфейса)
            for _ in range(10):  # несколько проходов для цепочек "по договору № от , по договору № от , ..."
                self._replace_regex_in_doc(doc, r",\s*по\s+договору\s+№\s*от\s*\s*,", ",")
                self._replace_regex_in_doc(doc, r"по\s+договору\s+№\s*от\s*\s*,", "")
                self._replace_regex_in_doc(doc, r",\s*по\s+договору\s+№\s*\-?\s*", ",")
                self._replace_regex_in_doc(doc, r"по\s+договору\s+№\s*\-?\s*", "")

            # Дополнительная зачистка: запятая перед точкой и лишние пробелы
            self._replace_regex_in_doc(doc, r",\s*\.", ".")
            self._replace_regex_in_doc(doc, r"\s{2,}", " ")

        # Голые остаточные слоты незаполненных договоров — БЕЗ гейта is_mortgage, т.к.
        # у ипотеки порядок маркеров обратный ([100]=№, [110]=дата "№ [100] от [110]"),
        # и после обнуления остаётся хвост "№ от", а у обычных актов — "от № ". Чистим ОБА
        # порядка. Пустые = после № и после "от" нет цифры реальные "№ 123 от 12.03.2024"
        # не трогаем. Пропускаем, если пустых слотов нет (obligations покрывают все).
        if not skip_obligations and obligations_count < (max_slots if max_slots else 6):
            for _ in range(8):
                self._replace_regex_in_doc(doc, r"(?:,\s*)?от\s+№\s*(?=,|\.|\)|;|$)", "")
                self._replace_regex_in_doc(doc, r"(?:,\s*)?№\s*от\s*(?=,|\.|\)|;|$)", "")
            self._replace_regex_in_doc(doc, r",\s*,", ",")
            self._replace_regex_in_doc(doc, r",\s*\.", ".")
            self._replace_regex_in_doc(doc, r"\s{2,}", " ")

    def _format_obligation_entry(self, obligation: Dict[str, Any]) -> str:
        """Формирует человекочитаемое описание обязательства для текста документа."""
        if not isinstance(obligation, dict):
            return ""

        number = self.clean_extracted_value(obligation.get('contractNumber', '')).strip()
        date = self.clean_extracted_value(obligation.get('contractDate', '')).strip()
        obligation_type = self.clean_extracted_value(obligation.get('obligationType', '')).strip()

        parts = []
        if number:
            parts.append(f"договор № {number}")
        if date:
            if parts:
                parts[-1] = f"{parts[-1]} от {date}"
            else:
                parts.append(f"договор от {date}")
        if obligation_type:
            parts.append(obligation_type.lower())

        if not parts:
            return ""

        if len(parts) > 1 and parts[-1] and 'догов' not in parts[-1]:
            return f"{', '.join(parts[:-1])} ({parts[-1]})"
        return ', '.join(parts)

    def _update_obligation_paragraphs(self, doc: Document, obligations: list):
        """
        Обновляет параграфы, где перечислены обязательства.

        ВАЖНО: Не создаем список договоров, а используем шаблон "кредитный договор от [100] № [110]"
        для каждого обязательства отдельно. Если в шаблоне есть только один набор маркеров [100] и [110],
        они будут заменены данными первого обязательства.
        """
        if not obligations:
            return

        logger.debug("Пропускаем обновление параграфов с обязательствами - используем только замену маркеров [100], [110] и т.д.")
        return

    def add_obligations_to_document(self, doc: Document, obligations: list):
        """
        Добавляет информацию об обязательствах в документ

        Args:
            doc: Документ
            obligations: Список обязательств
        """
        logger.info(f"Добавляем {len(obligations)} обязательств в документ")
        logger.info(f"Тип obligations: {type(obligations)}")
        logger.info(f"Содержимое obligations: {obligations}")

        # Проверяем, что obligations - это список
        if not isinstance(obligations, list):
            logger.warning(f"obligations не является списком: {type(obligations)}")
            return

        # Ищем место для вставки обязательств (после текста "Обязательства:")
        for paragraph in doc.paragraphs:
            if "обязательства" in paragraph.text.lower() or "договор" in paragraph.text.lower():
                # Добавляем таблицу с обязательствами
                table = doc.add_table(rows=1, cols=3)
                table.style = cast(Any, 'Table Grid')

                # Заголовки таблицы
                hdr_cells = cast(Any, table.rows[0].cells)
                hdr_cells[0].text = 'Номер договора'
                hdr_cells[1].text = 'Дата договора'
                hdr_cells[2].text = 'Тип обязательства'

                # Добавляем строки с обязательствами
                for obligation in obligations:
                    if isinstance(obligation, dict):
                        row_cells = cast(Any, table.add_row().cells)
                        row_cells[0].text = obligation.get('contractNumber', '')
                        row_cells[1].text = obligation.get('contractDate', '')
                        row_cells[2].text = obligation.get('obligationType', '')
                        logger.info(f"Добавлено обязательство: {obligation}")
                    else:
                        logger.warning(f"obligation не является словарем: {type(obligation)}")

                break

    def generate_single_obligation_document(self, doc: Document, data: Dict[str, Any], template_info: Dict[str, Any]):
        """
        Генерирует документ для одного обязательства
        """
        # Заголовок
        title = doc.add_heading('РЕШЕНИЕ', level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Подзаголовок
        subtitle = doc.add_heading('о включении в реестр требований кредиторов', level=2)
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Дата и номер дела
        doc.add_paragraph()
        case_info = doc.add_paragraph()
        case_info.add_run(f"Дело № {data.get('caseNumber', 'НЕ УКАЗАНО')}")

        date_para = doc.add_paragraph()
        date_para.add_run(f"Дата: {data.get('applicationDate', 'НЕ УКАЗАНО')}")

        # Основной текст
        doc.add_paragraph()
        main_text = doc.add_paragraph()
        main_text.add_run("Арбитражный суд ")
        main_text.add_run(data.get('courtName', 'НЕ УКАЗАНО')).bold = True
        main_text.add_run(" рассмотрев заявление ")
        main_text.add_run(data.get('applicantName', 'НЕ УКАЗАНО')).bold = True
        main_text.add_run(" о включении в реестр требований кредиторов, установил:")

        # Информация о заявителе
        doc.add_paragraph()
        applicant_info = doc.add_paragraph()
        applicant_info.add_run("Заявитель: ").bold = True
        applicant_info.add_run(data.get('applicantName', 'НЕ УКАЗАНО'))

        address_info = doc.add_paragraph()
        address_info.add_run("Адрес: ").bold = True
        address_info.add_run(data.get('applicantAddress', 'НЕ УКАЗАНО'))

        # Информация об обязательстве
        doc.add_paragraph()
        obligation_info = doc.add_paragraph()
        obligation_info.add_run("Основание: ").bold = True
        obligation_info.add_run(data.get('obligationType', 'НЕ УКАЗАНО'))

        if data.get('contractNumber'):
            contract_info = doc.add_paragraph()
            contract_info.add_run("Номер договора: ").bold = True
            contract_info.add_run(data.get('contractNumber'))

        if data.get('contractDate'):
            contract_date_info = doc.add_paragraph()
            contract_date_info.add_run("Дата договора: ").bold = True
            contract_date_info.add_run(data.get('contractDate'))

        # Сумма долга
        doc.add_paragraph()
        amount_info = doc.add_paragraph()
        amount_info.add_run("Сумма долга: ").bold = True
        amount_info.add_run(f"{data.get('debtAmount', 'НЕ УКАЗАНО')} рублей")

        # Кредитор и должник
        doc.add_paragraph()
        creditor_info = doc.add_paragraph()
        creditor_info.add_run("Кредитор: ").bold = True
        creditor_info.add_run(data.get('creditorName', 'НЕ УКАЗАНО'))

        debtor_info = doc.add_paragraph()
        debtor_info.add_run("Должник: ").bold = True
        debtor_info.add_run(data.get('debtorName', 'НЕ УКАЗАНО'))

        # Решение
        doc.add_paragraph()
        decision_title = doc.add_heading('РЕШИЛ:', level=2)
        decision_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        decision_text = doc.add_paragraph()
        decision_text.add_run("Включить в реестр требований кредиторов требование ")
        decision_text.add_run(data.get('applicantName', 'НЕ УКАЗАНО')).bold = True
        decision_text.add_run(" в размере ")
        decision_text.add_run(f"{data.get('debtAmount', 'НЕ УКАЗАНО')} рублей").bold = True

        # Подпись
        doc.add_paragraph()
        doc.add_paragraph()
        signature_line = doc.add_paragraph("_________________")
        signature_line.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        signature_label = doc.add_paragraph("(подпись)")
        signature_label.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    def generate_multiple_obligations_document(self, doc: Document, data: Dict[str, Any], template_info: Dict[str, Any]):
        """
        Генерирует документ для нескольких обязательств
        """
        # Заголовок
        title = doc.add_heading('РЕШЕНИЕ', level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Подзаголовок
        subtitle = doc.add_heading('о включении в реестр требований кредиторов', level=2)
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Дата и номер дела
        doc.add_paragraph()
        case_info = doc.add_paragraph()
        case_info.add_run(f"Дело № {data.get('caseNumber', 'НЕ УКАЗАНО')}")

        date_para = doc.add_paragraph()
        date_para.add_run(f"Дата: {data.get('applicationDate', 'НЕ УКАЗАНО')}")

        # Основной текст
        doc.add_paragraph()
        main_text = doc.add_paragraph()
        main_text.add_run("Арбитражный суд ")
        main_text.add_run(data.get('courtName', 'НЕ УКАЗАНО')).bold = True
        main_text.add_run(" рассмотрев заявление ")
        main_text.add_run(data.get('applicantName', 'НЕ УКАЗАНО')).bold = True
        main_text.add_run(" о включении в реестр требований кредиторов по нескольким обязательствам, установил:")

        # Информация о заявителе
        doc.add_paragraph()
        applicant_info = doc.add_paragraph()
        applicant_info.add_run("Заявитель: ").bold = True
        applicant_info.add_run(data.get('applicantName', 'НЕ УКАЗАНО'))

        address_info = doc.add_paragraph()
        address_info.add_run("Адрес: ").bold = True
        address_info.add_run(data.get('applicantAddress', 'НЕ УКАЗАНО'))

        # Таблица обязательств
        doc.add_paragraph()
        table_title = doc.add_heading('Перечень обязательств:', level=3)

        # Создаем таблицу
        table = doc.add_table(rows=1, cols=4)
        table.style = cast(Any, 'Table Grid')
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Заголовки таблицы
        header_cells = cast(Any, table.rows[0].cells)
        header_cells[0].text = '№'
        header_cells[1].text = 'Основание'
        header_cells[2].text = 'Сумма'
        header_cells[3].text = 'Примечание'

        # Применяем стили к заголовкам
        for cell in header_cells:
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Добавляем строки с данными (пример)
        row = cast(Any, table.add_row().cells)
        row[0].text = '1'
        row[1].text = data.get('obligationType', 'НЕ УКАЗАНО')
        row[2].text = f"{data.get('debtAmount', 'НЕ УКАЗАНО')} руб."
        row[3].text = 'Основное обязательство'

        # Общая сумма
        doc.add_paragraph()
        total_amount = doc.add_paragraph()
        total_amount.add_run("Общая сумма требований: ").bold = True
        total_amount.add_run(f"{data.get('debtAmount', 'НЕ УКАЗАНО')} рублей").bold = True

        # Решение
        doc.add_paragraph()
        decision_title = doc.add_heading('РЕШИЛ:', level=2)
        decision_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        decision_text = doc.add_paragraph()
        decision_text.add_run("Включить в реестр требований кредиторов требования ")
        decision_text.add_run(data.get('applicantName', 'НЕ УКАЗАНО')).bold = True
        decision_text.add_run(" по всем указанным обязательствам в общей сумме ")
        decision_text.add_run(f"{data.get('debtAmount', 'НЕ УКАЗАНО')} рублей").bold = True

        # Подпись
        doc.add_paragraph()
        doc.add_paragraph()
        signature_line = doc.add_paragraph("_________________")
        signature_line.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        signature_label = doc.add_paragraph("(подпись)")
        signature_label.alignment = WD_ALIGN_PARAGRAPH.RIGHT

