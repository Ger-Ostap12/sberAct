import os
import uuid
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Set
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.shared import OxmlElement, qn
# Локальный импорт анализатора без package-префикса, чтобы работать при запуске из app/
from document_analyzer import DocumentAnalyzer

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentGenerator:
    def __init__(self):
        """
        Инициализация генератора документов
        """
        self.generated_dir = Path("generated")
        self.generated_dir.mkdir(exist_ok=True)

        # Словарь для отслеживания сгенерированных документов
        self.documents = {}

        # Загружаем шаблоны
        self.templates = self.load_templates()

    def load_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Загружает шаблоны документов
        """
        return {
            "rtk_single_obligation": {
                "name": "Решение о включении в РТК (одно обязательство)",
                "type": "single_obligation",
                "fields": [
                    "applicantName", "applicantAddress", "applicationDate",
                    "courtName", "caseNumber", "debtAmount",
                    "creditorName", "debtorName", "contractNumber", "contractDate"
                ]
            },
            "rtk_multiple_obligations": {
                "name": "Решение о включении в РТК (несколько обязательств)",
                "type": "multiple_obligations",
                "fields": [
                    "applicantName", "applicantAddress", "applicationDate",
                    "courtName", "caseNumber", "debtAmount",
                    "creditorName", "debtorName"
                ]
            }
        }

    def clean_extracted_value(self, value: str) -> str:
        """Очищает извлеченное значение от звездочек и других маскирующих символов"""
        if not value:
            return value

        # Удаляем звездочки и другие маскирующие символы
        cleaned = re.sub(r'\*+', '', value)

        # Удаляем множественные пробелы
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Удаляем пробелы в начале и конце
        cleaned = cleaned.strip()

        return cleaned

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

    def replace_document_data(self, doc: Document, data: Dict[str, Any]):
        """
        Заменяет данные в существующем документе, используя нумерацию [1], [2], [3] и т.д.

        Args:
            doc: Документ для замены
            data: Данные для замены
        """
        logger.info("Заменяем данные в документе")
        logger.info(f"Данные для замены: {data}")

        # Очищаем все данные от звездочек перед заменой
        cleaned_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned_data[key] = self.clean_extracted_value(value)
            elif isinstance(value, list):
                # Очищаем элементы списка (например, obligations)
                cleaned_list = []
                for item in value:
                    if isinstance(item, dict):
                        cleaned_item = {}
                        for item_key, item_value in item.items():
                            if isinstance(item_value, str):
                                cleaned_item[item_key] = self.clean_extracted_value(item_value)
                            else:
                                cleaned_item[item_key] = item_value
                        cleaned_list.append(cleaned_item)
                    elif isinstance(item, str):
                        cleaned_list.append(self.clean_extracted_value(item))
                    else:
                        cleaned_list.append(item)
                cleaned_data[key] = cleaned_list
            else:
                cleaned_data[key] = value

        logger.info(f"Очищенные данные: {cleaned_data}")

        # Гарантируем наличие даты публикации ЕФРСБ для плейсхолдера [11]
        if not cleaned_data.get("efirsbPublicationDate"):
            fallback_field_name = None
            fallback_publication_date = None
            for field in ("messageDate", "publicationDate"):
                value = cleaned_data.get(field)
                if value:
                    fallback_field_name = field
                    fallback_publication_date = value
                    break
            if fallback_publication_date:
                cleaned_data["efirsbPublicationDate"] = fallback_publication_date
                logger.info(
                    "ℹ️ Используем %s как efirsbPublicationDate для плейсхолдера [11]",
                    fallback_field_name,
                )

        entity_type = (cleaned_data.get("entityType") or "").lower()
        source_doc_type = (cleaned_data.get("sourceDocumentType") or "").lower()
        is_ip = "ip_enforcement" in source_doc_type
        is_kfh = bool(cleaned_data.get("isKfh"))

        # Очистка имени для КФХ: убираем "ГЛАВА КФХ ИП" и оставляем только ФИО
        if is_kfh:
            # Приоритет: используем kfhHeadName если оно есть, иначе очищаем applicantName
            kfh_head_name = cleaned_data.get("kfhHeadName", "")
            if kfh_head_name:
                cleaned_data["applicantName"] = kfh_head_name
                logger.info(f"✅ Используем kfhHeadName для КФХ: '{kfh_head_name}'")
            else:
                applicant_name = cleaned_data.get("applicantName", "")
                if applicant_name:
                    # Убираем префиксы "ГЛАВА КФХ ИП", "ГЛАВА КФХ", "КФХ ИП" и т.д.
                    cleaned_name = re.sub(
                        r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                        '',
                        applicant_name,
                        flags=re.IGNORECASE
                    ).strip()
                    if cleaned_name:
                        cleaned_data["applicantName"] = cleaned_name
                        logger.info(f"🧹 Очищено имя КФХ: '{applicant_name}' -> '{cleaned_name}'")

                # Также очищаем debtorName если оно есть
                debtor_name = cleaned_data.get("debtorName", "")
                if debtor_name:
                    cleaned_debtor_name = re.sub(
                        r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                        '',
                        debtor_name,
                        flags=re.IGNORECASE
                    ).strip()
                    if cleaned_debtor_name:
                        cleaned_data["debtorName"] = cleaned_debtor_name
                        logger.info(f"🧹 Очищено debtorName КФХ: '{debtor_name}' -> '{cleaned_debtor_name}'")

            # Для КФХ пересоздаем падежные формы из kfhHeadName (без префиксов)
            kfh_head_name = cleaned_data.get("kfhHeadName", "")
            if kfh_head_name:
                analyzer = DocumentAnalyzer()

                # Пересоздаем падежные формы из чистого ФИО
                genitive = analyzer._convert_name_to_genitive(kfh_head_name)
                if genitive:
                    cleaned_data["applicantNameGenitive"] = genitive
                    logger.info(f"🔧 КФХ: пересоздан applicantNameGenitive из kfhHeadName: '{genitive}'")

                instrumental = analyzer._convert_name_to_instrumental(kfh_head_name)
                if instrumental:
                    cleaned_data["applicantNameInstrumental"] = instrumental
                    logger.info(f"🔧 КФХ: пересоздан applicantNameInstrumental из kfhHeadName: '{instrumental}'")

                accusative = analyzer._convert_name_to_accusative(kfh_head_name)
                if accusative:
                    cleaned_data["applicantNameAccusative"] = accusative
                    logger.info(f"🔧 КФХ: пересоздан applicantNameAccusative из kfhHeadName: '{accusative}'")
            else:
                # Если kfhHeadName нет, просто очищаем префиксы
                for field_name in ["applicantNameGenitive", "applicantNameInstrumental", "applicantNameAccusative"]:
                    field_value = cleaned_data.get(field_name, "")
                    if field_value:
                        cleaned_field_value = re.sub(
                            r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                            '',
                            field_value,
                            flags=re.IGNORECASE
                        ).strip()
                        if cleaned_field_value:
                            cleaned_data[field_name] = cleaned_field_value
                            logger.info(f"🧹 Очищено {field_name} КФХ: '{field_value}' -> '{cleaned_field_value}'")

        if entity_type == "legal" and not is_ip:
            ogrn_value = re.sub(r"\D", "", str(cleaned_data.get("ogrn") or ""))
            inn_value = re.sub(r"\D", "", str(cleaned_data.get("companyInn") or cleaned_data.get("inn") or ""))

            if ogrn_value:
                cleaned_data["ogrn"] = ogrn_value
                cleaned_data["birthDate"] = ogrn_value

            if inn_value:
                cleaned_data["inn"] = inn_value
                cleaned_data["companyInn"] = inn_value

            cleaned_data.pop("snils", None)

        # Для ИП сохраняем все поля, включая birthDate, snils, ipCollateralContractNumber
        if is_ip:
            logger.info(f"🔍 Проверка полей для ИП: birthDate={cleaned_data.get('birthDate')}, snils={cleaned_data.get('snils')}, ipCollateralContractNumber={cleaned_data.get('ipCollateralContractNumber')}")

        # Проверяем наличие новых полей
        new_fields = ['principalDebt13', 'interest14', 'forfeit15', 'stateDuty16']
        for field in new_fields:
            if field in cleaned_data:
                logger.info(f"✅ Найдено поле {field}: {cleaned_data[field]}")
            else:
                logger.info(f"❌ Поле {field} НЕ НАЙДЕНО в cleaned_data")

        # Проверяем наличие полей для ИП
        ip_fields = ['birthDate', 'snils', 'ipCollateralContractNumber', 'ipCollateralContractDate', 'ipCollateralClaimAmount']
        for field in ip_fields:
            if field in cleaned_data:
                logger.info(f"✅ Найдено поле ИП {field}: {cleaned_data[field]}")
            else:
                logger.info(f"❌ Поле ИП {field} НЕ НАЙДЕНО в cleaned_data")

        # Очистка адреса от маркера [6] для процедуры "умерший"
        procedure_type = (cleaned_data.get('procedureType') or '').lower()
        procedure_type_raw = (cleaned_data.get('procedureTypeRaw') or '').lower()
        if procedure_type == "deceased" or any(keyword in procedure_type_raw for keyword in ["умер", "умерший", "смерть", "смерти"]):
            applicant_address = cleaned_data.get("applicantAddress", "")
            if applicant_address:
                # Удаляем маркер [6] из адреса
                cleaned_address = re.sub(r'\s*\[6\]\s*', ' ', applicant_address, flags=re.IGNORECASE).strip()
                if cleaned_address != applicant_address:
                    cleaned_data["applicantAddress"] = cleaned_address
                    logger.info(f"🧹 Очищен адрес для умершего: '{applicant_address}' -> '{cleaned_address}'")

        # Добавляем текущую дату формирования акта
        current_date = datetime.now().strftime("%d.%m.%Y")
        cleaned_data["currentDate"] = current_date
        logger.info(f"📅 Текущая дата формирования акта: {current_date}")

        placeholders_in_doc = self._collect_placeholders(doc)

        # Дополнительная подготовка данных для заявлений к ИП
        source_document_type = (data.get("sourceDocumentType") or "").lower()
        if source_document_type:
            cleaned_data.setdefault("sourceDocumentType", source_document_type)
        if source_document_type in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                    "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                    "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"]:
            applicant_name = cleaned_data.get("applicantName")
            if applicant_name and not applicant_name.upper().startswith("ИП"):
                cleaned_data["applicantNameRaw"] = applicant_name
                cleaned_data["applicantName"] = f"ИП {applicant_name}"

            # Дублируем ключевые суммы при необходимости
            if "totalDebt" not in cleaned_data and cleaned_data.get("debtAmount"):
                cleaned_data["totalDebt"] = cleaned_data["debtAmount"]

            if "debtAmount" not in cleaned_data and cleaned_data.get("totalDebt"):
                cleaned_data["debtAmount"] = cleaned_data["totalDebt"]

        # Для шаблонов с несколькими обязательствами используем данные первого договора в базовых плейсхолдерах
        # НО для ипотеки не делаем этого, так как там обязательства обрабатываются отдельно
        is_mortgage_doc = (cleaned_data.get("sourceDocumentType") or "").lower() == "mortgage_claim"
        if not is_mortgage_doc:
            has_contract_date_placeholder = "[100]" in placeholders_in_doc
            has_contract_number_placeholder = "[110]" in placeholders_in_doc

            obligations_list = cleaned_data.get("obligations")
            if obligations_list and isinstance(obligations_list, list):
                primary_obligation = next((item for item in obligations_list if isinstance(item, dict)), None)
                if primary_obligation:
                    primary_date = primary_obligation.get("contractDate")
                    primary_number = primary_obligation.get("contractNumber")

                    if primary_date and has_contract_date_placeholder:
                        original_dates = cleaned_data.get("contractDate")
                        if original_dates and original_dates != primary_date:
                            cleaned_data.setdefault("contractDateList", original_dates)
                        cleaned_data["contractDate"] = primary_date

                    if primary_number and has_contract_number_placeholder:
                        original_numbers = cleaned_data.get("contractNumber")
                        if original_numbers and original_numbers != primary_number:
                            cleaned_data.setdefault("contractNumberList", original_numbers)
                        cleaned_data["contractNumber"] = primary_number

        # Маппинг полей из извлеченных данных на номера в шаблоне
        field_mapping = {
            "caseNumber": "1",           # [1] - Номер дела
            "mortgageCourtAddress001": "001",  # [001] - Адрес суда (ипотека)
            "mortgageCourtName002": "002",     # [002] - Наименование суда (ипотека)
            "applicantName": "2",        # [2] - ФИО должника
            "applicantNameGenitive": "2.1",  # [2.1] - ФИО должника в родительном падеже
            "applicantNameInstrumental": "2.3",  # [2.3] - ФИО должника в творительном падеже
            "applicantNameAccusative": "2.4",  # [2.4] - ФИО должника в винительном падеже
            "mortgageRepresentative22": "2.2",  # [2.2] - Представитель истца (ипотека)
            "birthDate": "3",            # [3] - Дата рождения
            "inn": "4",                  # [4] - ИНН
            "ogrnip": "4.1",             # [4.1] - ОГРНИП индивидуального предпринимателя
            "snils": "5",                # [5] - СНИЛС
            "applicantAddress": "6",     # [6] - Адрес регистрации
            "courtDecisionDate": "7",    # [7] - Дата решения суда
            "managerName": "8",          # [8] - ФИО финансового управляющего
            "messageNumber": "9",        # [9] - Номер сообщения
            "mortgagePeriodAmount10": "10",  # [10] - Сумма за период (ипотека)
            "efirsbPublicationDate": "11",  # [11] - Дата публикации на сайте ЕФРСБ
            "mortgagePrincipalAmount11": "11",  # [11] - Просроченный основной долг (ипотека)
            "cpCaseDate": "554",         # [554] - Дата из номера CP-Case
            "debtSnapshotDate88": "88",  # [88] - Дата состояния задолженности (для инициирования ЮЛ)
            "totalDebt": "12",           # [12] - Общая сумма долга
            "mortgageInterestAmount12": "12",  # [12] - Просроченные проценты (ипотека)
            "sroName": "987",            # [987] - Название СРО (саморегулируемая организация)
            # Исключаем старые поля, чтобы не конфликтовать с новыми
            # "principalDebt": "13",     # [13] - Основной долг (старое поле)
            # "interest": "14",          # [14] - Проценты (старое поле)
            # "forfeit": "15",           # [15] - Неустойка (старое поле)
            # "stateDuty": "16",         # [16] - Госпошлина (старое поле)
            "principalDebt13": "13",     # [13] - Основной долг из блока "ПРОСИТ СУД"
            "interest14": "14",          # [14] - Проценты из блока "ПРОСИТ СУД"
            "forfeit15": "15",           # [15] - Неустойка из блока "ПРОСИТ СУД"
            "stateDuty16": "16",         # [16] - Госпошлина из блока "ПРОСИТ СУД"
            "mortgageCreditAmount111": "111",  # [111] - Сумма кредита (ипотека)
            "mortgageCreditTerm112": "112",    # [112] - Срок кредита (ипотека)
            "mortgageInterestRate113": "113",  # [113] - Процентная ставка (ипотека)
            "mortgagePenaltyRate114": "114",   # [114] - Ставка неустойки (ипотека)
            "mortgagePeriodStart120": "120",   # [120] - Начало расчетного периода (ипотека)
            "mortgagePeriodEnd121": "121",     # [121] - Конец расчетного периода (ипотека)
            "mortgageCollateralDescription1221": "1221",  # [1221] - Описание предмета залога
            # Специальная дата для юр. инициирования конкурсного (ликвидируемый) — маркер [5555]
            "liquidationRecordDate5555": "5555",
            "mortgageStartPriceDecision1222": "1222",     # [1222] - Цена продажи из резолютивной части
            "mortgageAppraisalReport1223": "1223",        # [1223] - Отчет об оценке
            "mortgageCollateralValue1224": "1224",        # [1224] - Рыночная стоимость залога
            "mortgageStartingPrice1225": "1225",          # [1225] - Начальная цена продажи
            "contractDate": "100",       # [100] - Дата кредитного договора
            "contractNumber": "110",     # [110] - Номер кредитного договора
            "creditAmount": "1000",      # [1000] - Сумма кредита
            "creditTermMonths": "1001",  # [1001] - Срок кредита (в месяцах)
            "creditInterestRate": "1002",  # [1002] - Процентная ставка по кредиту
            "creditPenaltyRate": "1003",   # [1003] - Ставка неустойки
            "debtSnapshotDate": "1004",    # [1004] - Дата расчета задолженности
            "currentDate": "777",        # [777] - Текущая дата формирования акта
            # Поля залога для ИП
            "ipCollateralContractNumber": "0005",  # [0005] - Номер договора залога (ИП)
            "ipCollateralContractDate": "0006",   # [0006] - Дата договора залога (ИП)
            "ipCollateralClaimAmount": "0007",    # [0007] - Сумма требований в реестре (ИП)
            "penalty0071": "0071",                # [0071] - Неустойка в обязательстве по залогу
        }

        is_mortgage_document = (cleaned_data.get("sourceDocumentType") or "").lower() == "mortgage_claim"
        is_ip_collateral = (cleaned_data.get("sourceDocumentType") or "").lower() == "ip_enforcement_statement_collateral"
        is_physical_collateral = (cleaned_data.get("sourceDocumentType") or "").lower() in ["physical_realization_collateral", "physical_restructuring_collateral", "observation_collateral", "competition_collateral"]
        if is_mortgage_document:
            field_mapping = dict(field_mapping)
            field_mapping.pop("totalDebt", None)
            field_mapping["stateDuty16"] = "15"
            field_mapping["stateDuty"] = "15"
            field_mapping.pop("forfeit15", None)
            field_mapping["pretrialExpenses16"] = "16"
            # Добавляем mortgageDebtorName в маппинг для [2]
            field_mapping["mortgageDebtorName"] = "2"
            # Для ипотеки убираем contractDate и contractNumber из маппинга
            # Они будут заменены из обязательств в replace_obligations_data
            field_mapping.pop("contractDate", None)
            field_mapping.pop("contractNumber", None)
            # Для ипотеки используем mortgageDebtorName или debtorName вместо applicantName для [2]
            def strip_ooo(name: str) -> str:
                """Remove ООО/Общество с ограниченной ответственностью prefix to leave only the org name."""
                if not name:
                    return name
                # Trim quotes/spaces first
                trimmed = name.strip(' «»"')
                match = re.match(
                    r'^(?:ООО|Общество\s+с\s+ограниченной\s+ответственностью)\s*[«"]?(.+?)[»"]?$',
                    trimmed,
                    re.IGNORECASE,
                )
                if match:
                    return match.group(1).strip(' «»"')
                return trimmed

            mortgage_debtor_name = strip_ooo(cleaned_data.get("mortgageDebtorName", ""))
            debtor_name = strip_ooo(cleaned_data.get("debtorName", ""))
            # Обновляем очищенные значения в данных, чтобы маркер [2] всегда был без приставки ООО
            if mortgage_debtor_name:
                cleaned_data["mortgageDebtorName"] = mortgage_debtor_name
            if debtor_name:
                cleaned_data["debtorName"] = debtor_name
            current_applicant_name = cleaned_data.get("applicantName", "")

            # Приоритет: mortgageDebtorName > debtorName (если он короткий и не содержит "суд")
            # НИКОГДА не используем applicantName если оно содержит "суд"
            # Убираем applicantName из маппинга, чтобы использовать только mortgageDebtorName или debtorName
            field_mapping.pop("applicantName", None)

            # Также убираем applicantNameGenitive если оно содержит "суд"
            applicant_name_genitive = cleaned_data.get("applicantNameGenitive", "")
            if applicant_name_genitive and "суд" in applicant_name_genitive.lower():
                field_mapping.pop("applicantNameGenitive", None)
                logger.warning(f"applicantNameGenitive содержит 'суд' ({applicant_name_genitive}), не используем для [2.1]")

            if mortgage_debtor_name and "суд" not in mortgage_debtor_name.lower():
                logger.info(f"Используем mortgageDebtorName для [2]: {mortgage_debtor_name}")
                # Используем pymorphy для преобразования в разные падежи
                try:
                    from pymorphy3 import MorphAnalyzer
                    morph = MorphAnalyzer()
                    words = mortgage_debtor_name.split()

                    # Преобразуем в родительный падеж для [2.1]
                    if applicant_name_genitive and "суд" in applicant_name_genitive.lower():
                        genitive_words = []
                        for word in words:
                            parsed = morph.parse(word)[0]
                            genitive = parsed.inflect({'gent'})
                            if genitive:
                                genitive_words.append(genitive.word)
                            else:
                                genitive_words.append(word)
                        genitive_name = " ".join(genitive_words)
                        cleaned_data["applicantNameGenitive"] = genitive_name
                        field_mapping["applicantNameGenitive"] = "2.1"
                        logger.info(f"Преобразовано mortgageDebtorName в родительный падеж для [2.1]: {genitive_name}")

                    # Преобразуем в дательный падеж для [2.2]
                    dative_words = []
                    for word in words:
                        parsed = morph.parse(word)[0]
                        dative = parsed.inflect({'datv'})
                        if dative:
                            dative_words.append(dative.word)
                        else:
                            dative_words.append(word)
                    dative_name = self._capitalize_full_name(" ".join(dative_words))
                    cleaned_data["mortgageDebtorNameDative"] = dative_name
                    field_mapping["mortgageDebtorNameDative"] = "2.2"
                    # Убираем старое поле mortgageRepresentative22 из маппинга для ипотеки
                    field_mapping.pop("mortgageRepresentative22", None)
                    logger.info(f"Преобразовано mortgageDebtorName в дательный падеж для [2.2]: {dative_name}")
                except Exception as e:
                    logger.warning(f"Не удалось преобразовать mortgageDebtorName в падежи: {e}")
            elif debtor_name and "суд" not in debtor_name.lower() and len(debtor_name) < 100:
                # Если mortgageDebtorName не найден, но есть подходящий debtorName, используем его
                cleaned_data["mortgageDebtorName"] = debtor_name
                logger.info(f"Используем debtorName для [2]: {debtor_name}")
                # Преобразуем в разные падежи
                try:
                    from pymorphy3 import MorphAnalyzer
                    morph = MorphAnalyzer()
                    words = debtor_name.split()

                    # Преобразуем в родительный падеж для [2.1]
                    if applicant_name_genitive and "суд" in applicant_name_genitive.lower():
                        genitive_words = []
                        for word in words:
                            parsed = morph.parse(word)[0]
                            genitive = parsed.inflect({'gent'})
                            if genitive:
                                genitive_words.append(genitive.word)
                            else:
                                genitive_words.append(word)
                        genitive_name = " ".join(genitive_words)
                        cleaned_data["applicantNameGenitive"] = genitive_name
                        field_mapping["applicantNameGenitive"] = "2.1"
                        logger.info(f"Преобразовано debtorName в родительный падеж для [2.1]: {genitive_name}")

                    # Преобразуем в дательный падеж для [2.2]
                    dative_words = []
                    for word in words:
                        parsed = morph.parse(word)[0]
                        dative = parsed.inflect({'datv'})
                        if dative:
                            dative_words.append(dative.word)
                        else:
                            dative_words.append(word)
                    dative_name = self._capitalize_full_name(" ".join(dative_words))
                    cleaned_data["mortgageDebtorNameDative"] = dative_name
                    field_mapping["mortgageDebtorNameDative"] = "2.2"
                    field_mapping.pop("mortgageRepresentative22", None)
                    logger.info(f"Преобразовано debtorName в дательный падеж для [2.2]: {dative_name}")
                except Exception as e:
                    logger.warning(f"Не удалось преобразовать debtorName в падежи: {e}")
            elif current_applicant_name and "суд" in current_applicant_name.lower():
                logger.warning(f"applicantName содержит 'суд' ({current_applicant_name}), не используем для [2]. mortgageDebtorName: {mortgage_debtor_name}, debtorName: {debtor_name[:100] if debtor_name else 'None'}")
            else:
                logger.warning(f"Не удалось найти правильное ФИО ответчика. mortgageDebtorName: {mortgage_debtor_name}, debtorName: {debtor_name[:100] if debtor_name else 'None'}, applicantName: {current_applicant_name[:100] if current_applicant_name else 'None'}")

        # Заменяем данные в параграфах
        logger.info("🔍 Начинаем замену данных в документе...")

        # Для ипотеки сначала заменяем приоритетные поля, чтобы избежать конфликтов
        if is_mortgage_document:
            # Приоритетные поля для ипотеки (заменяются первыми)
            priority_fields = ["mortgageDebtorName", "mortgageDebtorNameDative", "applicantNameGenitive",
                             "mortgagePeriodEnd121", "mortgagePeriodStart120",
                             "mortgageInterestAmount12", "mortgagePrincipalAmount11", "mortgagePeriodAmount10"]

            # Сначала заменяем приоритетные поля
            for field_key in priority_fields:
                if field_key in cleaned_data and field_key in field_mapping and cleaned_data[field_key]:
                    field_value = cleaned_data[field_key]
                    field_number = field_mapping[field_key]
                    placeholder = f"[{field_number}]"

                    # Защита от неправильной замены [121] - только даты, не суммы
                    if field_number == "121":
                        value_str = str(field_value).strip()
                        if not re.match(r'^\d{1,2}[.,]\d{1,2}[.,]\d{4}', value_str):
                            logger.warning(f"⚠️ Пропускаем замену [121] - значение '{value_str}' не похоже на дату (поле: {field_key})")
                            continue

                    formatted_value = str(field_value)
                    if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                        logger.info(f"🔄 Заменено {placeholder} на {formatted_value} (поле: {field_key})")

            # Затем заменяем остальные поля, но пропускаем те, которые уже были заменены приоритетными
            replaced_placeholders = set()
            for field_key in priority_fields:
                if field_key in field_mapping:
                    replaced_placeholders.add(field_mapping[field_key])

            for field_key, field_value in cleaned_data.items():
                if field_key not in field_mapping or not field_value:
                    continue

                # Пропускаем приоритетные поля (уже заменены)
                if field_key in priority_fields:
                    continue

                field_number = field_mapping[field_key]
                placeholder = f"[{field_number}]"

                # Пропускаем плейсхолдеры, которые уже были заменены приоритетными полями
                if field_number in replaced_placeholders:
                    logger.debug(f"⏭️ Пропускаем {placeholder} - уже заменен приоритетным полем")
                    continue

                # Форматируем суммы с "руб" для ипотеки и залога
                if field_number in ["15", "16", "1222", "1225", "0071"]:
                    value_str = str(field_value).strip()
                    if "руб" not in value_str.lower() and value_str:
                        formatted_value = f"{value_str} руб."
                    else:
                        formatted_value = value_str
                else:
                    formatted_value = str(field_value)

                if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                    logger.info(f"🔄 Заменено {placeholder} на {formatted_value} (поле: {field_key})")
        else:
            # Для не-ипотечных документов - обычная замена
            # Сначала принудительно заменяем важные поля для ИП и ФЛ с залогом
            if is_ip or is_physical_collateral:
                priority_fields = {
                    "birthDate": "3",
                    "snils": "5",
                    "ipCollateralContractNumber": "0005",
                    "ipCollateralContractDate": "0006",
                    "ipCollateralClaimAmount": "0007",
                    "mortgageCollateralDescription1221": "1221",  # [1221] - Описание предмета залога
                    "penalty0071": "0071",  # [0071] - Неустойка в обязательстве по залогу
                    "stateDuty16": "16"  # [16] - Госпошлина
                }
                entity_type_label = "ИП" if is_ip else "ФЛ"
                for field_key, field_number in priority_fields.items():
                    if field_key in cleaned_data and cleaned_data[field_key]:
                        value_str = str(cleaned_data[field_key]).strip()
                        # Пропускаем некорректные значения
                        if value_str.lower() in ["от", "none", "null", ""]:
                            logger.warning(f"⚠️ Поле {entity_type_label} {field_key} имеет некорректное значение: {value_str}")
                            continue
                        placeholder = f"[{field_number}]"
                        formatted_value = value_str
                        if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                            logger.info(f"🔄 Заменено {placeholder} на {formatted_value[:100]}... (поле {entity_type_label}: {field_key})")
                    else:
                        logger.warning(f"⚠️ Поле {entity_type_label} {field_key} отсутствует или пустое в cleaned_data")

            for field_key, field_value in cleaned_data.items():
                if field_key not in field_mapping or not field_value:
                    continue

                field_number = field_mapping[field_key]
                placeholder = f"[{field_number}]"
                formatted_value = str(field_value)

                if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                    logger.info(f"🔄 Заменено {placeholder} на {formatted_value} (поле: {field_key})")

        # Обрабатываем обязательства (договоры) - номера 100-113
        self.replace_obligations_data(doc, cleaned_data)

        # Обрабатываем поля без нумерации (по контексту)
        self.replace_contextual_fields(doc, cleaned_data)

    def _collect_placeholders(self, doc: Document) -> Set[str]:
        """
        Собирает все плейсхолдеры вида [123] из параграфов и таблиц документа.
        """
        pattern = re.compile(r'\[[^\]]+\]')
        placeholders: Set[str] = set()

        for paragraph in doc.paragraphs:
            placeholders.update(pattern.findall(paragraph.text))

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    placeholders.update(pattern.findall(cell.text))

        return placeholders

    def _replace_placeholder_in_doc(self, doc: Document, placeholder: str, value: str) -> bool:
        """
        Заменяет указанный плейсхолдер во всём документе, включая колонтитулы.

        Returns:
            bool: True, если были выполнены замены.
        """
        replaced = False

        def replace_in_paragraphs(paragraphs):
            nonlocal replaced
            for paragraph in paragraphs:
                if placeholder in paragraph.text:
                    paragraph.text = paragraph.text.replace(placeholder, value)
                    replaced = True

        def replace_in_tables(tables):
            for table in tables:
                for row in table.rows:
                    for cell in row.cells:
                        replace_in_paragraphs(cell.paragraphs)

        replace_in_paragraphs(doc.paragraphs)
        replace_in_tables(doc.tables)

        for section in doc.sections:
            replace_in_paragraphs(section.header.paragraphs)
            replace_in_tables(section.header.tables)
            replace_in_paragraphs(section.footer.paragraphs)
            replace_in_tables(section.footer.tables)

        return replaced

    def _replace_regex_in_doc(self, doc: Document, pattern: str, replacement: str) -> bool:
        """
        Заменяет текст по регулярному выражению во всём документе, включая колонтитулы.
        """
        replaced = False
        regex = re.compile(pattern, re.IGNORECASE)

        def replace_in_paragraphs(paragraphs):
            nonlocal replaced
            for paragraph in paragraphs:
                if regex.search(paragraph.text):
                    paragraph.text = regex.sub(replacement, paragraph.text)
                    replaced = True

        def replace_in_tables(tables):
            for table in tables:
                for row in table.rows:
                    for cell in row.cells:
                        replace_in_paragraphs(cell.paragraphs)

        replace_in_paragraphs(doc.paragraphs)
        replace_in_tables(doc.tables)

        for section in doc.sections:
            replace_in_paragraphs(section.header.paragraphs)
            replace_in_tables(section.header.tables)
            replace_in_paragraphs(section.footer.paragraphs)
            replace_in_tables(section.footer.tables)

        return replaced

    def _format_amount_value(self, value: float) -> str:
        """
        Форматирует число как денежную сумму: 1234567.8 -> '1 234 567,80'
        """
        try:
            return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
        except Exception:
            return str(value)

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

        # Суммарная фраза для >5 обязательств
        summary_placeholder = "[992]"
        if obligations_count > 5:
            # Заменяем длинный список договоров на единый маркер [992]
            intro_phrase = "В обоснование заявленных требований кредитор указал, что"

            def collapse_paragraphs(paragraphs):
                for paragraph in paragraphs:
                    text = paragraph.text
                    if intro_phrase in text and any(
                        marker in text for marker in ["[100]", "[101]", "[102]", "[103]", "[104]", "[110]", "[111]", "[112]", "[113]", "[114]"]
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
                f"В обоснование заявленных требований кредитор указал, что между ПАО Сбербанк и {genitive_name} "
                f"(далее – должник) заключено {obligations_count} обязательств на общую сумму "
                f"{self._format_amount_value(total_issued)}."
            )
            # Заполняем сводный маркер
            self._replace_placeholder_in_doc(doc, summary_placeholder, summary_text)
            # Чистим маркеры для индивидуальных обязательств (до 5)
            for idx in range(5):
                self._replace_placeholder_in_doc(doc, f"[{100 + idx}]", "")
                self._replace_placeholder_in_doc(doc, f"[{110 + idx}]", "")
        else:
            # Если обязательств <=5, очищаем сводный маркер
            self._replace_placeholder_in_doc(doc, summary_placeholder, "")

        for i, obligation in enumerate(obligations):
            if not isinstance(obligation, dict):
                continue

            contract_date = obligation.get('contractDate', '')
            contract_number = obligation.get('contractNumber', '')
            obligation_type = obligation.get('obligationType') or obligation.get('type') or ''
            obligation_type_lower = obligation_type.lower()
            if "поручитель" in obligation_type_lower:
                type_label = "договор поручительства"
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

        # Очищаем неиспользованные фрагменты и маркеры для обязательств, если их меньше 5
        if not is_mortgage and obligations_count < 5:
            # Сначала удаляем текстовые куски для несуществующих обязательств (3, 4, 5 и т.п.)
            for idx in range(obligations_count, 5):
                date_num = 100 + idx
                number_num = 110 + idx
                # Удаляем фразу "кредитный договор от [10X] № [11X]" вместе с возможной запятой и пробелами
                credit_pattern = rf"(?:,\s*)?кредитный\s+договор\s+от\s+\[{date_num}\]\s+№\s+\[{number_num}\]"
                self._replace_regex_in_doc(doc, credit_pattern, "")
                # Удаляем фразу "договор поручительства от [10X] № [11X]"
                surety_pattern = rf"(?:,\s*)?договор\s+поручительства\s+от\s+\[{date_num}\]\s+№\s+\[{number_num}\]"
                self._replace_regex_in_doc(doc, surety_pattern, "")

            # Затем на всякий случай обнуляем сами маркеры
            for idx in range(obligations_count, 5):
                date_placeholder = f"[{100 + idx}]"
                number_placeholder = f"[{110 + idx}]"
                self._replace_placeholder_in_doc(doc, date_placeholder, "")
                self._replace_placeholder_in_doc(doc, number_placeholder, "")

            # Грубая зачистка испорченных хвостов без маркеров:
            # "кредитный договор от № ," и "договор поручительства от № .]"
            # Важно: удаляем только случаи, где после "№" НЕТ цифр (испорченные хвосты).
            self._replace_regex_in_doc(
                doc,
                r"(?:,\s*)?кредитный\s+договор\s+от\s+№\s*(?!\d)[^,\.]*",
                ""
            )
            self._replace_regex_in_doc(
                doc,
                r"(?:,\s*)?договор\s+поручительства\s+от\s+№\s*(?!\d)[^,\.]*",
                ""
            )

            # Дополнительная зачистка: запятая перед точкой и лишние пробелы
            self._replace_regex_in_doc(doc, r",\s*\.", ".")
            self._replace_regex_in_doc(doc, r"\s{2,}", " ")

    def replace_contextual_fields(self, doc: Document, data: Dict[str, Any]):
        """
        Заменяет поля без нумерации по контексту

        Args:
            doc: Документ
            data: Данные для замены
        """
        logger.info("Заменяем поля без нумерации по контексту")

        # Контекстные замены для финансового управляющего
        manager_fields = {
            'managerBirthDate': 'финансовый управляющий',
            'managerAddress': 'финансовый управляющий',
            'managerInn': 'финансовый управляющий',
            'managerSnils': 'финансовый управляющий'
        }

        # Контекстные замены для третьих лиц
        third_party_fields = {
            'thirdPartyName': 'поручитель',
            'thirdPartyBirthDate': 'поручитель',
            'thirdPartyAddress': 'поручитель',
            'thirdPartyInn': 'поручитель',
            'thirdPartySnils': 'поручитель'
        }

        # Заменяем в параграфах
        for paragraph in doc.paragraphs:
            text = paragraph.text

            # Специальная замена для даты сообщения в контексте "ЕФРСБ сообщение"
            message_date = data.get('messageDate', '')
            if message_date and 'ЕФРСБ' in text and 'сообщение' in text:
                # Ищем паттерн "ЕФРСБ сообщение" и заменяем дату после него
                pattern = r'ЕФРСБ\s+сообщение[^0-9]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})'
                if re.search(pattern, text):
                    paragraph.text = re.sub(pattern, f'ЕФРСБ сообщение {message_date}', text)
                    logger.info(f"Заменена дата сообщения в контексте ЕФРСБ: {message_date}")
                else:
                    # Если нет даты после "ЕФРСБ сообщение", просто добавляем дату
                    if 'ЕФРСБ сообщение' in text and not re.search(r'ЕФРСБ\s+сообщение\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}', text):
                        paragraph.text = text.replace('ЕФРСБ сообщение', f'ЕФРСБ сообщение {message_date}')
                        logger.info(f"Добавлена дата сообщения после ЕФРСБ: {message_date}")

            # Финансовый управляющий
            for field_key, context in manager_fields.items():
                field_value = data.get(field_key, '')
                if field_value and context in text.lower():
                    # Ищем паттерны для замены
                    if field_key == 'managerBirthDate':
                        # Заменяем дату рождения в контексте финансового управляющего
                        pattern = r'(\d{1,2}[.,]\d{1,2}[.,]\d{4})[^,]*?финансовый\s+управляющий'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'{field_value} финансовый управляющий', text)
                            logger.info(f"Заменена дата рождения финансового управляющего: {field_value}")
                    elif field_key == 'managerAddress':
                        # Заменяем адрес в контексте финансового управляющего
                        pattern = r'финансовый\s+управляющий[^,]*?адрес[:\s]+([^,\n]+)'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'финансовый управляющий адрес: {field_value}', text)
                            logger.info(f"Заменен адрес финансового управляющего: {field_value}")
                    elif field_key == 'managerInn':
                        # Заменяем ИНН в контексте финансового управляющего
                        pattern = r'финансовый\s+управляющий[^,]*?ИНН[:\s]*([0-9]{10,12})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'финансовый управляющий ИНН: {field_value}', text)
                            logger.info(f"Заменен ИНН финансового управляющего: {field_value}")
                    elif field_key == 'managerSnils':
                        # Заменяем СНИЛС в контексте финансового управляющего
                        pattern = r'финансовый\s+управляющий[^,]*?СНИЛС[:\s]*([0-9-]{11,14})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'финансовый управляющий СНИЛС: {field_value}', text)
                            logger.info(f"Заменен СНИЛС финансового управляющего: {field_value}")

            # Третьи лица
            for field_key, context in third_party_fields.items():
                field_value = data.get(field_key, '')
                if field_value and context in text.lower():
                    # Ищем паттерны для замены
                    if field_key == 'thirdPartyName':
                        # Заменяем ФИО поручителя
                        pattern = r'поручитель[:\s]+([А-ЯЁ][а-яё\s]+)'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель: {field_value}', text)
                            logger.info(f"Заменено ФИО поручителя: {field_value}")
                    elif field_key == 'thirdPartyBirthDate':
                        # Заменяем дату рождения поручителя
                        pattern = r'поручитель[^,]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель {field_value}', text)
                            logger.info(f"Заменена дата рождения поручителя: {field_value}")
                    elif field_key == 'thirdPartyAddress':
                        # Заменяем адрес поручителя
                        pattern = r'поручитель[^,]*?адрес[:\s]+([^,\n]+)'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель адрес: {field_value}', text)
                            logger.info(f"Заменен адрес поручителя: {field_value}")
                    elif field_key == 'thirdPartyInn':
                        # Заменяем ИНН поручителя
                        pattern = r'поручитель[^,]*?ИНН[:\s]*([0-9]{10,12})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель ИНН: {field_value}', text)
                            logger.info(f"Заменен ИНН поручителя: {field_value}")
                    elif field_key == 'thirdPartySnils':
                        # Заменяем СНИЛС поручителя
                        pattern = r'поручитель[^,]*?СНИЛС[:\s]*([0-9-]{11,14})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель СНИЛС: {field_value}', text)
                            logger.info(f"Заменен СНИЛС поручителя: {field_value}")

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

        # НЕ создаем список договоров - это нарушает шаблон акта
        # Вместо этого просто пропускаем обновление, так как маркеры [100], [110] и т.д.
        # уже заменяются в методе replace_obligations_data для каждого обязательства отдельно
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
                table.style = 'Table Grid'

                # Заголовки таблицы
                hdr_cells = table.rows[0].cells
                hdr_cells[0].text = 'Номер договора'
                hdr_cells[1].text = 'Дата договора'
                hdr_cells[2].text = 'Тип обязательства'

                # Добавляем строки с обязательствами
                for obligation in obligations:
                    if isinstance(obligation, dict):
                        row_cells = table.add_row().cells
                        row_cells[0].text = obligation.get('contractNumber', '')
                        row_cells[1].text = obligation.get('contractDate', '')
                        row_cells[2].text = obligation.get('obligationType', '')
                        logger.info(f"Добавлено обязательство: {obligation}")
                    else:
                        logger.warning(f"obligation не является словарем: {type(obligation)}")

                break

    def _get_templates_for_procedure(self, procedure_type: str) -> Dict[str, Dict[str, Any]]:
        """Возвращает набор шаблонов для указанного типа процедуры (ВКЛ в РТК без залога)."""
        templates_dir = Path(__file__).parent.parent / "templates"
        root_dir = Path(__file__).resolve().parents[2]
        # Новая база для шаблонов без залогов
        base_dir = root_dir / "шаблоны актов без залогов"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            return {"name": name, "path": path, "order": order}

        # Физлица, реструктуризация ВКЛ в РТК
        if procedure_type == "restructuring":
            restructuring_dir = base_dir / "физ реструк ВКЛ в РТК"

            templates = {
                "main": entry(
                    "Реструктуризация ВКЛ",
                    restructuring_dir / "Реструктуризация ВКЛ.docx",
                    1
                ),
                "resolution": entry(
                    "Резолютивка ВКЛ реструктуризация",
                    restructuring_dir / "Резолютивка ВКЛ реструктуризация.docx",
                    2
                ),
                "acceptance": entry(
                    "Реструктуризация принятие РТК",
                    restructuring_dir / "Реструктуризация принятие РТК.docx",
                    3
                ),
            }

            missing_paths = [info for info in templates.values() if not info["path"].exists()]
            if missing_paths:
                for info in missing_paths:
                    logger.error(f"Шаблон не найден: {info['path'].absolute()}")
                logger.warning("Не удалось найти шаблоны реструктуризации ВКЛ без залогов, используем шаблоны реализации из каталога templates")
            else:
                return templates

        # Юрлица, наблюдение ВКЛ в РТК без залога
        if procedure_type == "observation":
            observation_dir = base_dir / "юр ВКЛ в РТК наблюдение"

            observation_templates = {
                "main": entry(
                    "Наблюдение ВКЛ в РТК",
                    observation_dir / "Наблюдение ВКЛ в РТК.docx",
                    1
                ),
                "resolution": entry(
                    "Наблюдение ВКЛ в РТК (Резолютивка)",
                    observation_dir / "Наблюдение ВКЛ в РТК (Резолютивка).docx",
                    2
                ),
                "acceptance": entry(
                    "Принятие РТК наблюдение",
                    observation_dir / "Принятие РТК наблюдение.docx",
                    3
                ),
            }

            for info in observation_templates.values():
                logger.info(f"📁 Шаблон наблюдения: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

            return observation_templates

        if procedure_type == "observation_collateral":
            # Шаблоны для наблюдения с залогом
            observation_collateral_dir = root_dir / "Залог" / "Наблюдение"
            observation_collateral_templates = {
                "acceptance": entry(
                    "Принятие РТК наблюдение",
                    observation_collateral_dir / "Принятие РТК наблюдение.docx",
                    1
                ),
                "main": entry(
                    "Наблюдение ВКЛ в РТК Залог",
                    observation_collateral_dir / "Наблюдение ВКЛ в РТК  Залог.docx",
                    2
                ),
            }
            logger.info("⚖️ Используются шаблоны для наблюдения с залогом.")

            for info in observation_collateral_templates.values():
                logger.info(f"📁 Шаблон наблюдения с залогом: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

            return observation_collateral_templates

        if procedure_type == "competition_collateral":
            # Шаблоны для конкурсного производства с залогом
            competition_collateral_dir = root_dir / "Залог" / "Конкурсное"
            competition_collateral_templates = {
                "main": entry(
                    "Конкурсное ВКЛ в РТК Залог",
                    competition_collateral_dir / "Конкурсное ВКЛ в РТК Залог.docx",
                    1
                ),
                "acceptance": entry(
                    "Принятие РТК конкурсное",
                    competition_collateral_dir / "Принятие РТК конкурсное (Копия).docx",
                    2
                ),
            }
            logger.info("⚖️ Используются шаблоны для конкурсного производства с залогом.")

            for info in competition_collateral_templates.values():
                logger.info(f"📁 Шаблон конкурсное с залогом: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

            return competition_collateral_templates

        # Процедура "умерший"
        if procedure_type == "deceased":
            deceased_dir = root_dir / "умерший"
            deceased_templates = {
                "acceptance": entry(
                    "Принятие заявления о признании должника банкротом умерший",
                    deceased_dir / "Принятие заявления о призании должника банкротом умерший.docx",
                    1
                ),
                "main": entry(
                    "Решение Умерший",
                    deceased_dir / "Решение Умерший.docx",
                    2
                ),
            }
            logger.info("⚖️ Используются шаблоны для процедуры 'умерший'.")

            for info in deceased_templates.values():
                logger.info(f"📁 Шаблон умерший: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

            return deceased_templates

        # По умолчанию используем шаблоны для реализации ВКЛ в РТК (физлица, без залогов)
        realization_dir = base_dir / "физ реализация ВКЛ в РТК"
        return {
            "main": entry(
                "Реализация ВКЛ несколько договоров",
                realization_dir / "Реализация ВКЛ несколько договоров.docx",
                1
            ),
            "resolution": entry(
                "Резолютивка ВКЛ реализация",
                realization_dir / "Резолютивка ВКЛ реализация.docx",
                2
            ),
            "acceptance": entry(
                "Реализация принятие РТК",
                realization_dir / "Реализация принятие РТК.docx",
                3
            ),
            "corrected": entry(
                "Реализация ВКЛ",
                realization_dir / "Реализация ВКЛ.docx",
                4
            ),
        }

    def _get_ip_enforcement_templates(self, has_collateral: bool, procedure_type: str = "realization") -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для исков к индивидуальным предпринимателям.

        Args:
            has_collateral: Наличие залога
            procedure_type: Тип процедуры - "realization" (реализация) или "restructuring" (реструктуризация)
        """
        root_dir = Path(__file__).resolve().parents[2]

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            return {"name": name, "path": path, "order": order}

        if has_collateral:
            # Шаблоны для ИП с залогом
            if procedure_type == "restructuring":
                collateral_dir = root_dir / "Залог" / "Реструктуризация"
                templates = {
                    "acceptance": entry(
                        "Реструктуризация принятие РТК Залог",
                        collateral_dir / "Реструктуризация принятие РТК Залог.docx",
                        1
                    ),
                    "decision": entry(
                        "Реструктуризация ВКЛ Залог",
                        collateral_dir / "Реструктуризация ВКЛ Залог.docx",
                        2
                    ),
                    "resolution": entry(
                        "Резолютивка ВКЛ реструктуризация Залог",
                        collateral_dir / "Резолютивка ВКЛ реструктуризация Залог.docx",
                        3
                    )
                }
                logger.info("⚖️ Используются шаблоны для ИП реструктуризация с залогом.")
            else:  # realization по умолчанию
                collateral_dir = root_dir / "Залог" / "Реализация"
                templates = {
                    "acceptance": entry(
                        "Реализация принятие РТК Залог",
                        collateral_dir / "Реализация принятие РТК Залог.docx",
                        1
                    ),
                    "decision": entry(
                        "Реализация ВКЛ Залог",
                        collateral_dir / "Реализация ВКЛ Залог.docx",
                        2
                    ),
                    "resolution": entry(
                        "Резолютивка ВКЛ реализация Залог",
                        collateral_dir / "Резолютивка ВКЛ реализация Залог.docx",
                        3
                    )
                }
                logger.info("⚖️ Используются шаблоны для ИП реализация с залогом.")
        else:
            # Базовые шаблоны для ИП без залога (одинаковые для реализации и реструктуризации)
            base_dir = root_dir / "СУдебные акты физики" / "Взыскание"
            templates = {
                "acceptance": entry(
                    "Принятие иска о взыскании с ИП",
                    base_dir / "Принятие иска о взыскании с ИП.docx",
                    1
                ),
                "decision": entry(
                    "Решение взыскание с ИП",
                    base_dir / "Решение взыскание с ИП.docx",
                    2
                )
            }
            procedure_label = "реструктуризация" if procedure_type == "restructuring" else "реализация"
            logger.info(f"ℹ️ Используются базовые шаблоны для взыскания с ИП {procedure_label} (без залога).")

        for info in templates.values():
            logger.info(f"📁 Шаблон: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

        return templates

    def _get_physical_collateral_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для ФЛ с залогом в реализации.
        Использует те же шаблоны, что и для ИП с залогом.
        """
        root_dir = Path(__file__).resolve().parents[2]

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            return {"name": name, "path": path, "order": order}

        # Шаблоны для ФЛ с залогом (те же, что и для ИП с залогом)
        collateral_dir = root_dir / "Залог" / "Реализация"
        templates = {
            "acceptance": entry(
                "Реализация принятие РТК Залог",
                collateral_dir / "Реализация принятие РТК Залог.docx",
                1
            ),
            "decision": entry(
                "Реализация ВКЛ Залог",
                collateral_dir / "Реализация ВКЛ Залог.docx",
                2
            ),
            "resolution": entry(
                "Резолютивка ВКЛ реализация Залог",
                collateral_dir / "Резолютивка ВКЛ реализация Залог.docx",
                3
            )
        }
        logger.info("⚖️ Используются шаблоны для ФЛ с залогом в реализации.")

        for info in templates.values():
            logger.info(f"📁 Шаблон: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

        return templates

    def _get_physical_restructuring_collateral_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для ФЛ с залогом в реструктуризации.
        """
        root_dir = Path(__file__).resolve().parents[2]

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            return {"name": name, "path": path, "order": order}

        # Шаблоны для ФЛ с залогом в реструктуризации
        collateral_dir = root_dir / "Залог" / "Реструктуризация"
        templates = {
            "acceptance": entry(
                "Реструктуризация принятие РТК Залог",
                collateral_dir / "Реструктуризация принятие РТК Залог.docx",
                1
            ),
            "decision": entry(
                "Реструктуризация ВКЛ Залог",
                collateral_dir / "Реструктуризация ВКЛ Залог.docx",
                2
            ),
            "resolution": entry(
                "Резолютивка ВКЛ реструктуризация Залог",
                collateral_dir / "Резолютивка ВКЛ реструктуризация Залог.docx",
                3
            )
        }
        logger.info("⚖️ Используются шаблоны для ФЛ с залогом в реструктуризации.")

        for info in templates.values():
            logger.info(f"📁 Шаблон: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

        return templates

    def _get_initiation_physical_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для инициирования банкротства физического лица.
        """
        root_dir = Path(__file__).resolve().parents[2]
        # Новое расположение шаблонов инициирования ФЛ (без залогов)
        base_dir = root_dir / "шаблоны актов без залогов" / "физ иниц рестр + реал"

        def entry(name: str, filename: str, order: int) -> Dict[str, Any]:
            path = base_dir / filename
            logger.info(f"📁 Шаблон инициирования (физ лицо): {name} -> {path} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        return {
            "acceptance": entry(
                "Принятие заявления о признании должника банкротом",
                "Принятие заявления о призании должника банкротом.docx",
                1
            ),
            "restructuring": entry(
                "Определение о введении реструктуризации долгов (заемщик)",
                "Определение о введении реструктуризации ЗАЕМЩИК.docx",
                2
            ),
            "realization": entry(
                "Определение о введении реализации имущества (заемщик)",
                "Определение о введении реализации ЗАЕМЩИК.docx",
                3
            )
        }

    def _get_initiation_legal_templates(self, contest_type: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для инициирования банкротства юридического лица.
        """
        root_dir = Path(__file__).resolve().parents[2]
        # Новое расположение шаблонов инициирования ЮЛ (без залогов)
        base_dir = root_dir / "шаблоны актов без залогов" / "юр инициир набл + конкурс"

        def entry(name: str, filename: str, order: int) -> Dict[str, Any]:
            path = base_dir / filename
            logger.info(f"📁 Шаблон инициирования (юр лицо): {name} -> {path} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        # Базовый шаблон: принятие заявления — есть всегда
        templates: Dict[str, Dict[str, Any]] = {
            "acceptance": entry(
                "О принятии заявления",
                "О принятии заявления.docx",
                1
            ),
        }

        # Если это обычное инициирование (без конкурсного), добавляем акт о введении наблюдения
        if contest_type is None:
            templates["observation"] = entry(
                "О введении наблюдения",
                "О введении наблюдения.docx",
                2
            )
        # Для конкурсного (ликвидируемый / отсутствующий) акта наблюдения быть НЕ должно —
        # только "О принятии заявления" и "О введении конкурсное"
        elif contest_type == "absent":
            templates["competition"] = entry(
                "О введении конкурсное (отсутствующий)",
                "О введении конкурсное отсутствующий .docx",
                2
            )
        elif contest_type == "liquidation":
            templates["competition"] = entry(
                "О введении конкурсное (ликвидируемый)",
                "О введении конкурсное ликвидируемый.docx",
                2
            )

        return templates

    def _get_kfh_observation_templates(self, has_collateral: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для КФХ (наблюдение / ВКЛ в РТК), с залогом или без.
        """
        root_dir = Path(__file__).resolve().parents[2]
        kfh_dir = root_dir / "КФХ"

        def entry(name: str, filename: str, order: int) -> Dict[str, Any]:
            path = kfh_dir / filename
            logger.info(f"📁 Шаблон КФХ: {name} -> {path} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        if has_collateral:
            templates = {
                "acceptance": entry(
                    "Принятие и инициирование КФХ (залог)",
                    "Принятие иницирование КФХ.docx",
                    1,
                ),
                "main": entry(
                    "Наблюдение КФХ Залог",
                    "Наблюдение КФХ Залог.docx",
                    2,
                ),
            }
        else:
            templates = {
                "acceptance": entry(
                    "Принятие и инициирование КФХ",
                    "Принятие иницирование КФХ.docx",
                    1,
                ),
                "main": entry(
                    "Наблюдение КФХ",
                    "Наблюдение КФХ.docx",
                    2,
                ),
            }

        return templates

    def _get_mortgage_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблон решения суда по ипотечному иску.
        """
        root_dir = Path(__file__).resolve().parents[2]
        base_dir = root_dir / "Проект Никите" / "ипотека"

        def entry(name: str, filename: str, order: int) -> Dict[str, Any]:
            path = base_dir / filename
            logger.info(f"📁 Шаблон ипотека: {name} -> {path} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        return {
            "mortgage_decision": entry(
                "Шаблон решения суда по ипотеке",
                "Шаблон решения суда.docx",
                1
            )
        }

    def generate(self, template_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Генерирует комплект документов (реализация или реструктуризация) на основе извлеченных данных.

        Args:
            template_type: Тип шаблона (для совместимости с API)
            data: Извлеченные данные

        Returns:
            Словарь с результатом генерации
        """
        try:
            normalized_template = (template_type or "").lower()
            source_document_type = (data.get("sourceDocumentType") or "").lower()
            is_kfh = bool(data.get("isKfh"))

            if normalized_template in {"observation_single", "observation_multiple"}:
                normalized_template = "observation"

            # ПРИОРИТЕТ: Проверяем на процедуру "умерший" в первую очередь
            if normalized_template == "deceased" or source_document_type == "deceased" or (data.get('procedureType') or '').lower() == "deceased" or any(keyword in (data.get('procedureTypeRaw') or '').lower() for keyword in ["умер", "умерший", "смерть", "смерти"]):
                # Шаблоны для процедуры "умерший" - ПРИОРИТЕТ перед всеми остальными
                templates = self._get_templates_for_procedure("deceased")
                procedure_type = "deceased"
                logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: умерший")
            elif normalized_template == "physical_restructuring_collateral" or source_document_type == "physical_restructuring_collateral":
                # Шаблоны для ФЛ с залогом в реструктуризации
                templates = self._get_physical_restructuring_collateral_templates()
                procedure_type = "physical_restructuring_collateral"
                logger.info(
                    f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ФЛ с залогом в реструктуризации"
                )
            elif normalized_template == "physical_realization_collateral" or source_document_type == "physical_realization_collateral":
                # Шаблоны для ФЛ с залогом в реализации
                templates = self._get_physical_collateral_templates()
                procedure_type = "physical_realization_collateral"
                logger.info(
                    f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ФЛ с залогом в реализации"
                )
            elif normalized_template in ["kfh_observation", "kfh_observation_collateral"] or \
                 (is_kfh and (normalized_template in ["observation", "observation_single", "observation_multiple"] or
                              source_document_type == "observation_collateral" or
                              source_document_type in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                                       "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                                       "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"])):
                # ПРИОРИТЕТ: КФХ шаблоны должны обрабатываться ПЕРЕД ИП шаблонами
                # ПРИОРИТЕТ: выбранный шаблон имеет приоритет над данными документа
                if normalized_template == "kfh_observation_collateral":
                    # Пользователь явно выбрал шаблон с залогом
                    has_collateral = True
                elif normalized_template == "kfh_observation":
                    # Пользователь явно выбрал шаблон без залога
                    has_collateral = False
                elif source_document_type == "observation_collateral":
                    # Тип документа указывает на залог
                    has_collateral = True
                else:
                    # Определяем по данным документа только если шаблон не был явно выбран
                    has_collateral = (
                        bool(data.get("ipCollateralContractNumber")) or
                        bool(data.get("mortgageCollateralDescription1221"))
                    )
                templates = self._get_kfh_observation_templates(has_collateral=has_collateral)
                procedure_type = "kfh_observation_collateral" if has_collateral else "kfh_observation"
                logger.info(
                    f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для КФХ "
                    f"({'наблюдение с залогом' if has_collateral else 'наблюдение, без залога'})"
                )
            elif normalized_template in ["ip_enforcement", "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                         "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"] or \
                 source_document_type in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                         "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                         "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"]:
                # Определяем наличие залога
                if source_document_type in ["ip_enforcement_statement_collateral", "ip_enforcement_realization_collateral",
                                            "ip_enforcement_restructuring_collateral"]:
                    has_collateral_flag = True
                else:
                    has_collateral_flag = str(data.get("ipHasCollateral", "")).strip().lower() in {"true", "1", "yes", "да"}

                # Определяем тип процедуры
                if "restructuring" in source_document_type or normalized_template == "ip_enforcement_restructuring":
                    ip_procedure_type = "restructuring"
                else:
                    ip_procedure_type = "realization"  # По умолчанию реализация

                templates = self._get_ip_enforcement_templates(has_collateral_flag, ip_procedure_type)
                procedure_type = source_document_type or normalized_template or "ip_enforcement"
                logger.info(
                    f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ИП "
                    f"({ip_procedure_type}, залог: {'есть' if has_collateral_flag else 'нет'})"
                )
            elif normalized_template == "initiation_physical" or source_document_type == "initiation_physical":
                templates = self._get_initiation_physical_templates()
                procedure_type = "initiation_physical"
                data["_skip_obligation_blocks"] = True
                logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 3 ДОКУМЕНТОВ для инициирования банкротства физического лица")
            elif normalized_template == "initiation_legal" or source_document_type == "initiation_legal":
                templates = self._get_initiation_legal_templates()
                procedure_type = "initiation_legal"
                logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 2 ДОКУМЕНТОВ для инициирования банкротства юридического лица")
            elif normalized_template == "initiation_legal_competition_absent":
                templates = self._get_initiation_legal_templates(contest_type="absent")
                procedure_type = "initiation_legal_competition_absent"
                logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 2 ДОКУМЕНТОВ для инициирования ЮЛ (конкурсное, отсутствующий должник)")
            elif normalized_template == "initiation_legal_competition_liquidation":
                templates = self._get_initiation_legal_templates(contest_type="liquidation")
                procedure_type = "initiation_legal_competition_liquidation"
                logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 2 ДОКУМЕНТОВ для инициирования ЮЛ (конкурсное, ликвидируемый должник)")
            elif normalized_template == "mortgage" or source_document_type == "mortgage_claim":
                templates = self._get_mortgage_templates()
                procedure_type = "mortgage"
                data["_skip_obligation_blocks"] = True
                logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 1 ДОКУМЕНТА для ипотечного иска")
            elif normalized_template == "observation_collateral" or source_document_type == "observation_collateral":
                # Шаблоны для наблюдения с залогом
                if is_kfh:
                    templates = self._get_kfh_observation_templates(has_collateral=True)
                    procedure_type = "kfh_observation_collateral"
                    logger.info(
                        f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для КФХ (наблюдение с залогом)"
                    )
                else:
                    templates = self._get_templates_for_procedure("observation_collateral")
                    procedure_type = "observation_collateral"
                    logger.info(
                        f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для наблюдения с залогом"
                    )
            elif normalized_template == "competition_collateral" or source_document_type == "competition_collateral":
                # Шаблоны для конкурсного производства с залогом
                templates = self._get_templates_for_procedure("competition_collateral")
                procedure_type = "competition_collateral"
                logger.info(
                    f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для конкурсного производства с залогом"
                )
            else:
                procedure_type = (data.get('procedureType') or '').lower()
                entity_type = str(data.get("entityType") or "").lower()
                raw = (data.get('procedureTypeRaw') or '').lower()

                # ПРИОРИТЕТ: Проверяем на процедуру "умерший" в первую очередь
                if procedure_type == "deceased" or any(keyword in raw for keyword in ["умер", "умерший", "смерть", "смерти"]):
                    procedure_type = 'deceased'
                    templates = self._get_templates_for_procedure("deceased")
                    logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: умерший")
                else:
                    if entity_type in {"legal", "юридическое лицо", "юрлицо"} or is_kfh:
                        # Для КФХ процедуры такие же, как у юрлица (наблюдение),
                        # но сам должник остаётся физлицом.
                        procedure_type = "observation"

                    if procedure_type not in {"restructuring", "realization", "observation"}:
                        # Пытаемся определить по необработанному тексту, если доступен
                        if 'реструктур' in raw:
                            procedure_type = 'restructuring'
                        elif 'реализац' in raw:
                            procedure_type = 'realization'
                        elif 'наблюден' in raw or entity_type in {"legal", "юридическое лицо", "юрлицо"} or is_kfh:
                            procedure_type = 'observation'
                        else:
                            procedure_type = 'realization' if entity_type not in {"legal", "юридическое лицо", "юрлицо"} else 'observation'

                    if is_kfh and procedure_type == "observation":
                        templates = self._get_kfh_observation_templates(has_collateral=False)
                        logger.info(
                            f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для КФХ (наблюдение, без залога)"
                        )
                        procedure_type = "kfh_observation"
                    else:
                        templates = self._get_templates_for_procedure(procedure_type)
                        logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: {procedure_type}")
            logger.info(f"📊 Полученные данные: {data}")

            generated_documents = {}
            document_ids = []

            # Генерируем каждый документ
            for doc_type, template_info in templates.items():
                logger.info(f"📄 Генерируем документ: {template_info['name']}")

                template_path = template_info['path']
                logger.info(f"Путь к шаблону: {template_path.absolute()}")
                logger.info(f"Шаблон существует: {template_path.exists()}")

                if not template_path.exists():
                    logger.error(f"Шаблон не найден: {template_path.absolute()}")
                    continue

                # Загружаем документ
                doc = Document(template_path)
                logger.info(f"Загружен шаблон: {template_path}")

                # Устанавливаем шрифт Times New Roman 11 для всего документа
                self.set_times_new_roman_11(doc)

                # Заменяем данные в документе
                self.replace_document_data(doc, data)

                # Генерируем уникальный ID для документа
                document_id = str(uuid.uuid4())
                document_ids.append(document_id)

                # Сохраняем документ
                file_path = self.generated_dir / f"{document_id}.docx"
                doc.save(str(file_path))

                # Сохраняем информацию о документе
                self.documents[document_id] = {
                    "template_type": template_type,
                    "document_type": doc_type,
                    "document_name": template_info['name'],
                    "file_path": str(file_path),
                    "generation_date": datetime.now().isoformat(),
                    "data": data,
                    "procedure_type": procedure_type,
                }

                generated_documents[doc_type] = {
                    "document_id": document_id,
                    "file_path": str(file_path),
                    "name": template_info['name'],
                    "order": template_info['order']
                }

                logger.info(f"✅ Документ '{template_info['name']}' успешно сгенерирован: {file_path}")

            logger.info(f"🎉 Сгенерировано документов: {len(generated_documents)}")

            return {
                "success": True,
                "documents": generated_documents,
                "document_ids": document_ids,
                "count": len(generated_documents)
            }

        except Exception as e:
            logger.error(f"Ошибка при генерации документов: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def set_times_new_roman_11(self, doc: Document):
        """
        Устанавливает шрифт Times New Roman 11 для всего документа
        """
        logger.info("🔤 Устанавливаем шрифт Times New Roman 11 для всего документа")

        # Устанавливаем шрифт для всех стилей
        for style in doc.styles:
            if hasattr(style, 'font'):
                style.font.name = 'Times New Roman'
                style.font.size = Pt(11)
                logger.info(f"Установлен шрифт для стиля: {style.name}")

        # Устанавливаем шрифт для всех параграфов
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                run.font.name = 'Times New Roman'
                run.font.size = Pt(11)

        # Устанавливаем шрифт для всех таблиц
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.name = 'Times New Roman'
                            run.font.size = Pt(11)

        logger.info("✅ Шрифт Times New Roman 11 установлен для всего документа")

    def apply_document_styles(self, doc: Document):
        """
        Применяет базовые стили к документу
        """
        # Настройка стилей параграфов
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Times New Roman'
        font.size = Pt(11)

        # Настройка отступов
        paragraph_format = style.paragraph_format
        paragraph_format.line_spacing = 1.5
        paragraph_format.space_after = Pt(12)

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
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Заголовки таблицы
        header_cells = table.rows[0].cells
        header_cells[0].text = '№'
        header_cells[1].text = 'Основание'
        header_cells[2].text = 'Сумма'
        header_cells[3].text = 'Примечание'

        # Применяем стили к заголовкам
        for cell in header_cells:
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Добавляем строки с данными (пример)
        row = table.add_row().cells
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

    def get_document_path(self, document_id: str) -> Optional[str]:
        """
        Получает путь к сгенерированному документу
        """
        if document_id in self.documents:
            return self.documents[document_id]["file_path"]
        return None

    def delete_document(self, document_id: str) -> bool:
        """
        Удаляет сгенерированный документ
        """
        try:
            if document_id in self.documents:
                file_path = self.documents[document_id]["file_path"]

                # Удаляем файл
                if os.path.exists(file_path):
                    os.remove(file_path)

                # Удаляем запись
                del self.documents[document_id]

                logger.info(f"Документ {document_id} успешно удален")
                return True
            else:
                logger.warning(f"Документ {document_id} не найден")
                return False

        except Exception as e:
            logger.error(f"Ошибка при удалении документа {document_id}: {str(e)}")
            return False

    def cleanup_old_documents(self, max_age_hours: int = 24):
        """
        Удаляет старые документы
        """
        try:
            current_time = datetime.now()
            documents_to_delete = []

            for doc_id, doc_info in self.documents.items():
                generation_time = datetime.fromisoformat(doc_info["generation_date"])
                age_hours = (current_time - generation_time).total_seconds() / 3600

                if age_hours > max_age_hours:
                    documents_to_delete.append(doc_id)

            for doc_id in documents_to_delete:
                self.delete_document(doc_id)

            logger.info(f"Удалено {len(documents_to_delete)} старых документов")

        except Exception as e:
            logger.error(f"Ошибка при очистке старых документов: {str(e)}")
