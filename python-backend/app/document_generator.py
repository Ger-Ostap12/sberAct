import os
import sys
import uuid
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Set, List
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.shared import OxmlElement, qn
# Локальный импорт анализатора без package-префикса, чтобы работать при запуске из app/
from document_analyzer import DocumentAnalyzer
from templates_resolver_mixin import TemplatesResolverMixin
from generator_inflection_mixin import GeneratorInflectionMixin
from docx_ops_mixin import DocxOpsMixin
from obligations_render_mixin import ObligationsRenderMixin
from formatting_mixin import FormattingMixin

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentGenerator(TemplatesResolverMixin, GeneratorInflectionMixin, DocxOpsMixin, ObligationsRenderMixin, FormattingMixin):
    def __init__(self):
        """
        Инициализация генератора документов
        """
        if getattr(sys, "frozen", False):
            self.generated_dir = Path(sys.executable).parent / "generated"
        else:
            self.generated_dir = Path(__file__).resolve().parents[2] / "generated"
        self.generated_dir.mkdir(exist_ok=True)

        # Словарь для отслеживания сгенерированных документов
        self.documents = {}

        # Загружаем шаблоны
        self.templates = self.load_templates()

    def _templates_root(self) -> Path:
        """
        Корень папки с шаблонами. Проверяем несколько возможных путей.
        Приоритет: Shablony, затем Templates/templates для совместимости.
        При запуске из exe: Shablony рядом с exe, _internal, шаблоны актов без залогов.
        При запуске из исходников — Shablony в корне проекта.
        """
        project_root = self._project_root()
        candidates = []

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            # Сначала шаблоны рядом с exe (можно менять без пересборки), затем встроенные в бинарник
            candidates = [
                exe_dir / "Shablony",
                exe_dir / "Templates",
                exe_dir / "templates",
            ]
            if hasattr(sys, "_MEIPASS"):
                me = Path(sys._MEIPASS)
                candidates.extend([
                    me / "Shablony",
                    me / "Templates",
                    me,
                ])
            candidates.extend([
                exe_dir / "_internal" / "Shablony",
                exe_dir / "_internal" / "Templates",
                exe_dir / "_internal" / "templates",
                project_root / "Shablony",
                project_root / "Templates",
                project_root / "templates",
                exe_dir,
                project_root,
            ])
        else:
            candidates = [
                project_root / "Shablony",  # Основная папка шаблонов
                project_root / "Templates",  # Fallback для совместимости
                project_root,  # project_root/шаблоны актов без залогов
            ]

        for p in candidates:
            if not p.exists() or not p.is_dir():
                continue
            # Проверяем наличие шаблонов: Shablony/шаблоны..., Templates/шаблоны..., либо шаблоны... напрямую
            if (p / "шаблоны актов без залогов").exists():
                return p
            if (p / "Shablony" / "шаблоны актов без залогов").exists():
                return p / "Shablony"
            if (p / "Templates" / "шаблоны актов без залогов").exists():
                return p / "Templates"
            if (p / "templates" / "шаблоны актов без залогов").exists():
                return p / "templates"

        return candidates[0] if candidates else project_root / "Shablony"

    def _project_root(self) -> Path:
        """Корень проекта (родитель python-backend)."""
        return Path(__file__).resolve().parents[2]

    def _resolve_template_path(self, path: Path) -> Path:
        """
        Если шаблон не найден — ищем по fallback: корень проекта, альтернативные имена,
        любой .docx в той же папке, папки шаблоны актов без залогов в корне проекта.
        """
        if path.exists():
            return path

        root = self._templates_root()
        proj = self._project_root()

        # 1. Тот же относительный путь в корне проекта (шаблоны актов без залогов/...)
        try:
            rel = path.relative_to(root)
            legacy = proj / rel
            if legacy.exists():
                logger.info(f"Шаблон взят из корня проекта (fallback): {rel}")
                return legacy
        except ValueError:
            pass

        # 2. Прямой поиск в project_root/шаблоны актов без залогов/физ реализация ВКЛ в РТК/
        realization_subdirs = [
            proj / "Shablony" / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
            proj / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
            proj / "Templates" / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
            proj / "templates" / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
            root / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
            root / "Shablony" / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
            root / "templates" / "шаблоны актов без залогов" / "физ реализация ВКЛ в РТК",
        ]
        target_names = [path.name]
        # Альтернативные имена для типичных шаблонов
        if path.name == "Реализация ВКЛ.docx":
            target_names = ["Реализация ВКЛ.docx", "Реализация ВКЛ несколько договоров.docx", "Реализация принятие РТК.docx"]
        elif path.name == "Реализация принятие РТК.docx":
            target_names = ["Реализация принятие РТК.docx", "Реализация ВКЛ.docx", "Реализация ВКЛ несколько договоров.docx"]

        for search_dir in [path.parent] + realization_subdirs:
            if not search_dir.exists():
                continue
            for name in target_names:
                candidate = search_dir / name
                if candidate.exists():
                    logger.info(f"Используем шаблон (fallback): {candidate}")
                    return candidate
            # Любой .docx в папке
            try:
                for f in sorted(search_dir.glob("*.docx")):
                    logger.info(f"Используем шаблон из папки {search_dir.name}: {f.name}")
                    return f
            except Exception:
                pass

        return path

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

    def _prepare_replacement_data(self, doc: Document, data: Dict[str, Any]) -> Dict[str, Any]:
        """Подготовка cleaned_data для подстановки: очистка от звёздочек,
        нормализация ЮЛ/КФХ/ИП, адреса, дат, синхронизация и форматирование сумм,
        поля промежуточных актов и третьих лиц. Возвращает cleaned_data.
        Вынесено из replace_document_data без изменения поведения (gen-golden).
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
        logger.info(f"📊 Ключевые поля в cleaned_data: creditorName={cleaned_data.get('creditorName')}, inn={cleaned_data.get('inn')}, creditorAddress={cleaned_data.get('creditorAddress')}")

        # Для ЮЛ используем короткое наименование в [2]/[2.1]/[2.2], чтобы не тянуть
        # артефакты вроде "ИП Общества..." и некорректные ФИО-падежи.
        if (cleaned_data.get("entityType") or "").strip().lower() == "legal":
            legal_name = (
                str(cleaned_data.get("legalShortName") or "").strip()
                or str(cleaned_data.get("debtorName") or "").strip()
                or str(cleaned_data.get("applicantName") or "").strip()
            )
            if legal_name:
                # Если есть кавычки, берём внутреннее имя (ООО «Азбука» -> Азбука).
                quote_match = re.search(r'[«"]\s*([^»"]+?)\s*[»"]', legal_name)
                if quote_match:
                    legal_name = quote_match.group(1).strip()

                # Срезаем орг-правовую "шапку".
                legal_name = re.sub(
                    r'^(?:ИП\s+)?(?:общество|общества)\s+с\s+ограниченн\w+\s+ответственн\w+\s+',
                    '',
                    legal_name,
                    flags=re.IGNORECASE
                ).strip(" -\t\n\r«»\"'")

                if legal_name:
                    cleaned_data["applicantName"] = legal_name
                    cleaned_data["applicantNameGenitive"] = legal_name
                    cleaned_data["applicantNameDative"] = legal_name
                    cleaned_data["applicantNameInstrumental"] = legal_name
                    cleaned_data["applicantNameAccusative"] = legal_name
                    cleaned_data["legalShortName"] = legal_name
                    logger.info(f"🏢 Для ЮЛ нормализовано имя должника: {legal_name}")

        # Адрес должника/заявителя не должен совпадать с адресом кредитора (частая ошибка извлечения)
        applicant_addr = (cleaned_data.get("applicantAddress") or "").strip()
        creditor_addr = (cleaned_data.get("creditorAddress") or "").strip()
        if applicant_addr and creditor_addr and applicant_addr == creditor_addr:
            cleaned_data["applicantAddress"] = ""
            logger.warning("⚠️ Адрес заявителя совпадал с адресом кредитора — очищен (маркер [6] останется пустым)")

        # [11] — только дата публикации на сайте ЕФРСБ (не подставляем дату Коммерсанта)
        # Для газеты «Коммерсантъ» используются [67] (номер) и [68] (дата)
        if not cleaned_data.get("efirsbPublicationDate"):
            # Fallback только из полей, связанных с ЕФРСБ/сообщением, не из messageDate (может быть Коммерсант)
            for field in ("publicationDate",):
                value = cleaned_data.get(field)
                if value:
                    cleaned_data["efirsbPublicationDate"] = value
                    logger.info("ℹ️ Используем %s как efirsbPublicationDate для плейсхолдера [11]", field)
                    break

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

        # Обработка пользовательской даты
        if cleaned_data.get("date"):
            # Если дата в формате YYYY-MM-DD (из input type="date"), конвертируем в DD.MM.YYYY
            date_value = cleaned_data.get("date")
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
                try:
                    date_obj = datetime.strptime(date_value, "%Y-%m-%d")
                    cleaned_data["date"] = date_obj.strftime("%d.%m.%Y")
                    logger.info(f"📅 Конвертирована дата: {date_value} -> {cleaned_data['date']}")
                except ValueError:
                    logger.warning(f"⚠️ Не удалось распарсить дату: {date_value}")

        # Синхронизация loanDebt и principalDebt
        if cleaned_data.get("loanDebt") and not cleaned_data.get("principalDebt"):
            cleaned_data["principalDebt"] = cleaned_data["loanDebt"]
            cleaned_data["principalDebt13"] = cleaned_data["loanDebt"]
        elif cleaned_data.get("principalDebt") and not cleaned_data.get("loanDebt"):
            cleaned_data["loanDebt"] = cleaned_data["principalDebt"]

        # Синхронизация interest и interest14
        if cleaned_data.get("interest") and not cleaned_data.get("interest14"):
            cleaned_data["interest14"] = cleaned_data["interest"]
        elif cleaned_data.get("interest14") and not cleaned_data.get("interest"):
            cleaned_data["interest"] = cleaned_data["interest14"]

        # Синхронизация forfeit и forfeit15
        if cleaned_data.get("forfeit") and not cleaned_data.get("forfeit15"):
            cleaned_data["forfeit15"] = cleaned_data["forfeit"]
        elif cleaned_data.get("forfeit15") and not cleaned_data.get("forfeit"):
            cleaned_data["forfeit"] = cleaned_data["forfeit15"]

        # Синхронизация penalties и forfeit15
        if cleaned_data.get("penalties") and not cleaned_data.get("forfeit15"):
            cleaned_data["forfeit15"] = cleaned_data["penalties"]
            cleaned_data["forfeit"] = cleaned_data["penalties"]

        # Синхронизация stateDuty и stateDuty16
        if cleaned_data.get("stateDuty") and not cleaned_data.get("stateDuty16"):
            cleaned_data["stateDuty16"] = cleaned_data["stateDuty"]
        elif cleaned_data.get("stateDuty16") and not cleaned_data.get("stateDuty"):
            cleaned_data["stateDuty"] = cleaned_data["stateDuty16"]

        # Фолбэк-маппинг госпошлины для ГЕНЕРАЦИИ (не для формы): анализатор
        # раскладывает пошлину типо-эксклюзивно (банкротная [16] ИЛИ ссудная [17]),
        # но шаблон может содержать любой из маркеров. Чтобы сумма не потерялась,
        # заполняем ПУСТОЙ маркер из доступной пошлины. Две разные пошлины (обе
        # заполнены) не трогаем.
        _sd16 = cleaned_data.get("stateDuty16") or cleaned_data.get("stateDuty")
        _sd17 = cleaned_data.get("loanStateDuty17")
        if _sd17 and not _sd16:
            cleaned_data["stateDuty16"] = _sd17
            cleaned_data["stateDuty"] = _sd17
        elif _sd16 and not _sd17:
            cleaned_data["loanStateDuty17"] = _sd16

        # Форматирование сумм: приводим все суммы к виду '1 234 567,89'
        amount_fields = ["loanDebt", "principalDebt", "principalDebt13", "interest", "interest14",
                        "forfeit", "forfeit15", "penalties", "stateDuty", "stateDuty16", "loanStateDuty17",
                        "totalDebt", "debtAmount", "bankCommission", "priorAmount", "priorStateDuty"]
        for field in amount_fields:
            if field in cleaned_data and cleaned_data[field]:
                raw = str(cleaned_data[field]).strip()

                # Приводим к числу: убираем пробелы и нецифровые символы, нормализуем разделители
                tmp = raw.replace("\u202f", " ").replace("\xa0", " ").replace(" ", "")
                has_comma = "," in tmp
                has_dot = "." in tmp

                if has_comma and has_dot:
                    # Если есть и запятая, и точка, считаем, что запятая — разделитель копеек
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
                    number = float(tmp) if tmp else None
                except Exception:
                    number = None

                if number is not None:
                    formatted = self._format_amount_value(number)
                    cleaned_data[field] = formatted
                    logger.info(f"💰 Форматирована сумма {field}: {formatted}")

        placeholders_in_doc = self._collect_placeholders(doc)

        # Дополнительная подготовка данных для заявлений к ИП
        source_document_type = (data.get("sourceDocumentType") or "").lower()
        if source_document_type:
            cleaned_data.setdefault("sourceDocumentType", source_document_type)
        if source_document_type in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                    "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                    "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral",
                                    "ip_collection", "ip_collection_collateral", "ip_collection_collateral_auto"]:
            applicant_name = cleaned_data.get("applicantName")
            if applicant_name and not applicant_name.upper().startswith("ИП"):
                cleaned_data["applicantNameRaw"] = applicant_name
                cleaned_data["applicantName"] = f"ИП {applicant_name}"

            # Дублируем ключевые суммы при необходимости
            if "totalDebt" not in cleaned_data and cleaned_data.get("debtAmount"):
                cleaned_data["totalDebt"] = cleaned_data["debtAmount"]

            if "debtAmount" not in cleaned_data and cleaned_data.get("totalDebt"):
                cleaned_data["debtAmount"] = cleaned_data["totalDebt"]

            # Для ip_collection, ip_collection_collateral и ip_collection_collateral_auto проверяем наличие полей [1000], [1001], [1004]
            if source_document_type in ("ip_collection", "ip_collection_collateral", "ip_collection_collateral_auto"):
                logger.info(f"🔍 Проверка полей для ip_collection:")
                logger.info(f"  creditAmount [1000]: {cleaned_data.get('creditAmount')}")
                logger.info(f"  creditTermMonths [1001]: {cleaned_data.get('creditTermMonths')}")
                logger.info(f"  debtSnapshotDate [1004]: {cleaned_data.get('debtSnapshotDate')}")
                # Защищаем эти поля от перезаписи
                if not cleaned_data.get('creditAmount'):
                    logger.warning(f"⚠️ Поле creditAmount [1000] не найдено для ip_collection")
                if not cleaned_data.get('creditTermMonths'):
                    logger.warning(f"⚠️ Поле creditTermMonths [1001] не найдено для ip_collection")
                if not cleaned_data.get('debtSnapshotDate'):
                    logger.warning(f"⚠️ Поле debtSnapshotDate [1004] не найдено для ip_collection")

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

        # Заполняем поля [86] (причина) и [87] (для сторон) для актов "Отложение" и "Возврат"
        # Проверяем, есть ли данные для этих актов
        reason = (
            cleaned_data.get('intermediate_postponement_reason') or
            cleaned_data.get('intermediate_return_reason') or
            cleaned_data.get('acceptance_no_motion_other_reason') or
            ''
        )
        for_parties = (
            cleaned_data.get('intermediate_postponement_forParties') or
            cleaned_data.get('intermediate_return_forParties') or
            cleaned_data.get('acceptance_no_motion_other_forParties') or
            ''
        )

        if reason:
            cleaned_data['reason86'] = reason
            logger.info(f"📝 Установлено поле reason86 (маркер [86]): {reason[:100]}...")
        if for_parties:
            cleaned_data['forParties87'] = for_parties
            logger.info(f"📝 Установлено поле forParties87 (маркер [87]): {for_parties[:100]}...")

        # Заполняем поле [85] (запросы суда) для актов "Отложение", "Определение о принятии", "Принятие после Б/Д"
        court_requests = (
            cleaned_data.get('intermediate_postponement_courtRequests') or
            cleaned_data.get('acceptance_definition_courtRequests') or
            cleaned_data.get('acceptance_after_no_motion_courtRequests') or
            ''
        )
        if court_requests:
            cleaned_data['courtRequests85'] = court_requests
            logger.info(f"📝 Установлено поле courtRequests85 (маркер [85]): {court_requests[:100]}...")

        # Заполняем поле [25] (Название/ФИО третьего лица) из массива thirdParties
        third_parties = cleaned_data.get('thirdParties', [])
        if third_parties and isinstance(third_parties, list) and len(third_parties) > 0:
            # Берем ФИО первого третьего лица для маркера [25]
            first_third_party_name = third_parties[0].get('name', '') if isinstance(third_parties[0], dict) else ''
            if first_third_party_name:
                cleaned_data['thirdPartyName25'] = first_third_party_name
                logger.info(f"📝 Установлено поле thirdPartyName25 (маркер [25]): {first_third_party_name[:100]}...")
        # Также проверяем старое поле thirdPartyName для обратной совместимости
        elif cleaned_data.get('thirdPartyName'):
            cleaned_data['thirdPartyName25'] = cleaned_data.get('thirdPartyName')
            logger.info(f"📝 Установлено поле thirdPartyName25 (маркер [25]) из thirdPartyName: {cleaned_data.get('thirdPartyName')[:100]}...")
        return cleaned_data

    def _apply_debtor_name_field_mapping(self, cleaned_data: Dict[str, Any], field_mapping: Dict[str, str], is_mortgage_document: bool) -> Dict[str, str]:
        """Настраивает маппинг [2]/[2.1]/[2.2] под должника: для не-ипотеки —
        дательный падеж (applicantNameDative); для ипотеки — ОПФ/падежи
        mortgageDebtorName|debtorName и правки field_mapping. Возвращает
        (возможно пересозданный) field_mapping. Вынесено из replace_document_data
        без изменения поведения (gen-golden).
        """
        # Для всех типов, кроме ипотеки, [2.2] - это имя должника в дательном падеже (applicantNameDative)
        # Для ипотеки [2.2] - это представитель истца (mortgageRepresentative22)
        if not is_mortgage_document:
            # Если есть applicantNameDative, используем его для [2.2]
            if cleaned_data.get("applicantNameDative"):
                field_mapping["applicantNameDative"] = "2.2"
                # Убираем mortgageRepresentative22 из маппинга для не-ипотечных документов
                field_mapping.pop("mortgageRepresentative22", None)
                logger.info(f"Используем applicantNameDative для [2.2]: {cleaned_data.get('applicantNameDative')}")

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

            # Для маркеров [2], [2.1], [2.2] сохраняем ОПФ (ООО, АО и т.д.) вместе с названием организации
            mortgage_debtor_name = cleaned_data.get("mortgageDebtorName", "")
            debtor_name = cleaned_data.get("debtorName", "")
            # Обновляем значения в данных, сохраняя ОПФ для маркеров
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

            if mortgage_debtor_name and "," in mortgage_debtor_name:
                # Несколько должников: имя и падежи уже склеены, пословное склонение не делаем.
                logger.info("Несколько должников (mortgage) — пропускаем пословное склонение")
            elif mortgage_debtor_name and "суд" not in mortgage_debtor_name.lower():
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
            elif debtor_name and "," in debtor_name:
                # Несколько должников: имя и падежи уже склеены, пословное склонение не делаем.
                cleaned_data["mortgageDebtorName"] = debtor_name
                logger.info("Несколько должников (debtorName) — пропускаем пословное склонение")
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
        return field_mapping

    def _base_field_mapping(self) -> Dict[str, str]:
        """Базовый маппинг полей данных на номера маркеров шаблона
        ([1], [2], [2.1], [13]…). Возвращает свежий словарь (вызывающий код
        его мутирует под ипотеку/типы). Вынесено из replace_document_data
        без изменения поведения (gen-golden).
        """
        field_mapping = {
            "caseNumber": "1",           # [1] - Номер дела
            "courtName": "0",            # [0] - Название суда (арбитражный суд области/края/республики)
            "mortgageCourtAddress001": "001",  # [001] - Адрес суда (ипотека)
            "mortgageCourtName002": "002",     # [002] - Наименование суда (ипотека)
            "applicantName": "2",        # [2] - ФИО должника
            "applicantNameGenitive": "2.1",  # [2.1] - ФИО должника в родительном падеже
            "applicantNameInstrumental": "2.3",  # [2.3] - ФИО должника в творительном падеже
            "applicantNameAccusative": "2.4",  # [2.4] - ФИО должника в винительном падеже
            "mortgageRepresentative22": "2.2",  # [2.2] - Представитель истца (ипотека)
            "birthDate": "3",            # [3] - Дата рождения
            "birthPlace": "3.1",        # [3.1] - Город/место рождения
            "inn": "4",                  # [4] - ИНН
            "ogrnip": "4.1",             # [4.1] - ОГРНИП индивидуального предпринимателя
            "snils": "5",                # [5] - СНИЛС
            "applicantAddress": "6",     # [6] - Адрес регистрации
            "courtDecisionDate": "7",    # [7] - Дата решения суда
            "managerName": "8",          # [8] - ФИО финансового управляющего
            "messageNumber": "9",        # [9] - Номер сообщения ЕФРСБ
            "mortgagePeriodAmount10": "10",  # [10] - Сумма за период (ипотека)
            "efirsbPublicationDate": "11",  # [11] - Дата публикации на сайте ЕФРСБ
            "kommersantNumber": "67",    # [67] - Номер газеты «Коммерсантъ»
            "kommersantDate": "68",      # [68] - Дата газеты «Коммерсантъ»
            "mortgagePrincipalAmount11": "11",  # [11] - Просроченный основной долг (ипотека)
            "cpCaseDate": "554",         # [554] - Дата из номера CP-Case
            "debtSnapshotDate88": "88",  # [88] - Дата состояния задолженности (для инициирования ЮЛ)
            "totalDebt": "12",           # [12] - Общая сумма долга
            "mortgageInterestAmount12": "12",  # [12] - Просроченные проценты (ипотека)
            "sroName": "987",            # [987] - Название СРО (саморегулируемая организация)
            "creditorName": "989",       # [989] - Название кредитора
            "creditorAddress": "988",    # [988] - Юридический адрес кредитора
            "creditorOgrn": "990",       # [990] - ОГРН кредитора
            "creditorInn": "991",        # [991] - ИНН кредитора
            # Исключаем старые поля, чтобы не конфликтовать с новыми
            # "principalDebt": "13",     # [13] - Основной долг (старое поле)
            # "interest": "14",          # [14] - Проценты (старое поле)
            # "forfeit": "15",           # [15] - Неустойка (старое поле)
            # "stateDuty": "16",         # [16] - Госпошлина (старое поле)
            "principalDebt13": "13",     # [13] - Основной долг из блока "ПРОСИТ СУД"
            "principalDebt": "13",       # [13] - Основной долг (общее поле)
            "loanDebt": "13",           # [13] - Ссудная задолженность (синхронизируется с principalDebt)
            "interest14": "14",          # [14] - Проценты из блока "ПРОСИТ СУД"
            "interest": "14",            # [14] - Проценты (общее поле)
            "forfeit15": "15",           # [15] - Неустойка из блока "ПРОСИТ СУД"
            "forfeit": "15",             # [15] - Неустойка (общее поле)
            "penalties": "15",           # [15] - Штрафные санкции (синоним неустойки)
            "stateDuty16": "16",         # [16] - Банкротная госпошлина
            "stateDuty": "16",           # [16] - Банкротная госпошлина (общее поле)
            "loanStateDuty17": "17",     # [17] - Ссудная госпошлина
            "objectionsDeadline18": "18",  # [18] - Установка срока на предоставление возражений
            "considerationDeadline19": "19",  # [19] - На рассмотрение заявления в срок
            "withoutMovementDeadline20": "20",  # [20] - Срок для оставления без движения
            "separateDisputeNumber22": "22",  # [22] - Номер обособленного спора
            "applicationReceiptDate23": "23",  # [23] - Дата поступления заявления в суд (согласно штампу)
            "courtSubmissionDate24": "24",     # [24] - Дата направления в суд
            "courtHearingDateTime99": "99",    # [99] - Дата и время судебного заседания
            "judge": "415",              # [415] - Судья
            "date": "DATE",              # [DATE] - Дата (пользовательская)
            "mortgageCreditAmount111": "111",  # [111] - Сумма кредита (ипотека)
            "mortgageCreditTerm112": "112",    # [112] - Срок кредита (ипотека)
            "mortgageInterestRate113": "113",  # [113] - Процентная ставка (ипотека)
            "mortgagePenaltyRate114": "114",   # [114] - Ставка неустойки (ипотека)
            "mortgagePeriodStart120": "120",   # [120] - Начало расчетного периода (ипотека)
            "mortgagePeriodEnd121": "121",     # [121] - Конец расчетного периода (ипотека)
            "bankCommission": "122",           # [122] - Комиссия Банка (сумма)
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
            "other35": "35",                      # [35] - Иное
            "currentInterest36": "36",            # [36] - Срочные проценты на основной долг
            "currentInterestOverdue37": "37",    # [37] - Срочные проценты на просроченный основной долг
            "reason86": "86",                     # [86] - Причина (для актов "Отложение", "Возврат", "Определение Б/Д иное")
            "forParties87": "87",                 # [87] - Для сторон (для актов "Отложение", "Возврат", "Определение Б/Д иное")
            "courtRequests85": "85",              # [85] - Запросы суда (для актов "Отложение", "Определение о принятии", "Принятие после Б/Д")
            "ppDepositDate80": "80",              # [80] - Дата ПП депозит
            "ppStateDutyDate81": "81",            # [81] - Дата ПП ГП
            "thirdPartyName25": "25",             # [25] - Название/ФИО третьего лица
            # Ранее вынесенное решение другого суда (вставляется только в те акты,
            # где эти маркеры физически есть в шаблоне → «не во все»).
            "priorCourtName": "90",               # [90] - Суд ранее вынесенного решения
            "priorCaseNumber": "91",              # [91] - Номер дела ранее вынесенного решения
            "priorAmount": "92",                  # [92] - Взысканная сумма по ранее вынесенному решению
            "priorDecisionDate": "93",            # [93] - Дата ранее вынесенного решения
            "priorStateDuty": "94",               # [94] - Госпошлина по ранее вынесенному (прошлому) делу
        }
        return field_mapping

    def _apply_field_mapping_replacements(self, doc: Document, cleaned_data: Dict[str, Any], field_mapping: Dict[str, str], is_mortgage_document: bool, is_ip: bool, is_physical_collateral: bool) -> None:
        """Подставляет значения полей в маркеры [N] согласно field_mapping.
        Для ипотеки — приоритетные поля и формат сумм 'руб.'; для прочих —
        спец-поля ИП/ФЛ-залога и нормализация дат. Мутирует doc. Вынесено из
        replace_document_data без изменения поведения (gen-golden).
        """
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
                    "stateDuty16": "16"  # [16] - Банкротная госпошлина
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

                # Нормализация дат в формат DD.MM.YYYY (даты поступления, направления и т.д.)
                if field_key in ("applicationReceiptDate23", "courtSubmissionDate24"):
                    formatted_value = self._normalize_date_format(str(field_value))
                elif field_key == "courtHearingDateTime99" and str(field_value).strip():
                    # Дата и время: 2026-02-19T13:18 -> 19.02.2026 13:18
                    raw = str(field_value).strip()
                    if "T" in raw:
                        date_part = raw.split("T")[0]
                        time_part = raw.split("T")[1] if "T" in raw else ""
                        formatted_value = self._normalize_date_format(date_part)
                        if time_part:
                            formatted_value = f"{formatted_value} {time_part.replace('-', ':')}"
                    else:
                        formatted_value = self._normalize_date_format(raw)
                else:
                    formatted_value = str(field_value)

                if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                    logger.info(f"🔄 Заменено {placeholder} на {formatted_value} (поле: {field_key})")

    def replace_document_data(self, doc: Document, data: Dict[str, Any]):
        """
        Заменяет данные в существующем документе, используя нумерацию [1], [2], [3] и т.д.

        Args:
            doc: Документ для замены
            data: Данные для замены
        """
        cleaned_data = self._prepare_replacement_data(doc, data)
        # is_ip нужен ниже по методу; пролог его не возвращает — пересчёт из cleaned_data
        is_ip = "ip_enforcement" in (cleaned_data.get("sourceDocumentType") or "").lower()

        field_mapping = self._base_field_mapping()

        is_mortgage_document = (cleaned_data.get("sourceDocumentType") or "").lower() == "mortgage_claim"
        is_ip_collateral = (cleaned_data.get("sourceDocumentType") or "").lower() == "ip_enforcement_statement_collateral"
        is_physical_collateral = (cleaned_data.get("sourceDocumentType") or "").lower() in ["physical_realization_collateral", "physical_restructuring_collateral", "observation_collateral", "competition_collateral"]

        field_mapping = self._apply_debtor_name_field_mapping(cleaned_data, field_mapping, is_mortgage_document)

        # Коррекция падежей для женщин и восстановление обрезанной фамилии (ФЛ)
        self._correct_female_applicant_cases(cleaned_data)

        # Нормализуем регистр всех имен перед заменой в документе
        name_fields = [
            "applicantName", "debtorName", "creditorName", "legalShortName",
            "applicantNameGenitive", "applicantNameInstrumental", "applicantNameAccusative", "applicantNameDative",
            "mortgageDebtorName", "mortgageDebtorNameDative", "mortgageRepresentative22", "kfhHeadName"
        ]
        for field_name in name_fields:
            if field_name in cleaned_data and cleaned_data[field_name]:
                original_value = cleaned_data[field_name]
                # Пропускаем нормализацию, если значение уже содержит только префикс "ИП" без имени
                if original_value.strip().upper() == "ИП":
                    continue
                normalized_value = self._normalize_name_case(original_value)
                if normalized_value != original_value:
                    cleaned_data[field_name] = normalized_value
                    logger.info(f"📝 Нормализован регистр {field_name}: '{original_value}' -> '{normalized_value}'")

        # Заменяем данные в параграфах
        logger.info("🔍 Начинаем замену данных в документе...")

        # Нормализация номера дела: убираем лишний суффикс после года (А44-1233-4/2025-4 -> А44-1233-4/2025)
        case_number = cleaned_data.get("caseNumber", "")
        if case_number:
            # Убираем дублирование вида номер/год-цифра (например А44-1233-4/2025-4 -> А44-1233-4/2025)
            trailing_suffix = re.match(r'^(.+/\d{4})-\d+$', case_number.strip())
            if trailing_suffix:
                normalized = trailing_suffix.group(1)
                cleaned_data["caseNumber"] = normalized
                logger.info(f"📝 Убран лишний суффикс в номере дела: {case_number} -> {normalized}")
                case_number = normalized

            # Паттерн для поиска дублирования: номер-номер/год-номер/год (А53-2345-4/2025-4/2025 -> А53-2345-4/2025)
            pattern = r'^([А-ЯЁA-Z0-9-]+)/(\d{4})-([А-ЯЁA-Z0-9-]+)/(\d{4})$'
            match = re.match(pattern, case_number)
            if match:
                prefix = match.group(1)
                year1 = match.group(2)
                suffix = match.group(3)
                year2 = match.group(4)
                if year1 == year2 and suffix in prefix:
                    cleaned_data["caseNumber"] = f"{prefix}/{year1}"
                    logger.info(f"📝 Исправлено дублирование номера дела: {case_number} -> {cleaned_data['caseNumber']}")
                    case_number = cleaned_data["caseNumber"]

        # Модифицируем номер дела, если есть номер обособленного спора (только если его ещё нет в номере)
        # Формат: A99-15434/2025 -> A99-15434-4/2025. Не добавляем -4, если уже есть А44-1233-4/2025
        if cleaned_data.get("separateDisputeNumber22"):
            separate_dispute_number = str(cleaned_data.get("separateDisputeNumber22")).strip()
            case_number = cleaned_data.get("caseNumber", "")
            if case_number and separate_dispute_number:
                pattern = r'^([А-ЯЁA-Z0-9-]+)/(\d{4})$'
                match = re.match(pattern, case_number)
                if match:
                    prefix = match.group(1)
                    year = match.group(2)
                    # Не добавляем суффикс, если он уже есть в префиксе (например А44-1233-4)
                    if prefix.endswith(f"-{separate_dispute_number}"):
                        logger.info(f"📝 Номер дела уже содержит обособленный спор: {case_number}")
                    else:
                        modified_case_number = f"{prefix}-{separate_dispute_number}/{year}"
                        cleaned_data["caseNumber"] = modified_case_number
                        logger.info(f"📝 Номер дела модифицирован с учетом обособленного спора: {case_number} -> {modified_case_number}")
                else:
                    # Если формат не совпадает, пытаемся вставить перед последним слэшем
                    if '/' in case_number:
                        parts = case_number.rsplit('/', 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            modified_case_number = f"{parts[0]}-{separate_dispute_number}/{parts[1]}"
                            cleaned_data["caseNumber"] = modified_case_number
                            logger.info(f"📝 Номер дела модифицирован (альтернативный формат): {case_number} -> {modified_case_number}")
                        else:
                            logger.warning(f"⚠️ Не удалось модифицировать номер дела: {case_number} (нестандартный формат)")
                    else:
                        logger.warning(f"⚠️ Не удалось модифицировать номер дела: {case_number} (нет слэша с годом)")

        self._apply_field_mapping_replacements(doc, cleaned_data, field_mapping, is_mortgage_document, is_ip, is_physical_collateral)

        # Обрабатываем обязательства (договоры) - номера 100-113
        self.replace_obligations_data(doc, cleaned_data)

        # Обрабатываем поля без нумерации (по контексту)
        self.replace_contextual_fields(doc, cleaned_data)

        # Обрабатываем специальные маркеры [DATE], [415] и [66]
        if cleaned_data.get("date"):
            date_value = cleaned_data.get("date")
            if self._replace_placeholder_in_doc(doc, "[DATE]", date_value):
                logger.info(f"🔄 Заменено [DATE] на {date_value}")
            # [66] — дата определения о принятии заявления к производству в формате «___» __________ 20__ года
            date_66 = self._format_date_66(date_value)
            if date_66 and self._replace_placeholder_in_doc(doc, "[66]", date_66):
                logger.info(f"🔄 Заменено [66] на {date_66}")

        if cleaned_data.get("judge"):
            judge_value = cleaned_data.get("judge")
            if self._replace_placeholder_in_doc(doc, "[415]", judge_value):
                logger.info(f"🔄 Заменено [415] на {judge_value}")

        # Удаляем все пустые маркеры, для которых нет значений
        self._remove_empty_placeholders(doc, cleaned_data, field_mapping)

        # Финальный пост-процессинг всего документа:
        # подчищаем форматы дат, номера дел и оставшиеся маркеры,
        # чтобы в итоговом акте всё выглядело идеально.
        self._postprocess_document_formatting(doc, cleaned_data)

    def _remove_empty_placeholders(self, doc: Document, cleaned_data: Dict[str, Any], field_mapping: Dict[str, str]):
        """
        Удаляет из документа все маркеры, для которых нет значений в данных.
        Также удаляет контекст вокруг маркеров (например, "Дело№ [1]" удаляется полностью).

        Args:
            doc: Документ для обработки
            cleaned_data: Данные с заполненными полями
            field_mapping: Маппинг полей на номера маркеров
        """
        logger.info("🧹 Удаляем пустые маркеры из документа")

        # Собираем все маркеры из документа
        all_placeholders = self._collect_placeholders(doc)

        # Создаем обратный маппинг: номер маркера -> список полей
        marker_to_fields = {}
        for field_name, marker_number in field_mapping.items():
            marker = f"[{marker_number}]"
            if marker not in marker_to_fields:
                marker_to_fields[marker] = []
            marker_to_fields[marker].append(field_name)

        # Специальные маркеры, которые обрабатываются отдельно
        # Проверяем, был ли заполнен [992] в replace_obligations_data
        # [992] заполняется только если обязательств > 5
        obligations = cleaned_data.get('obligations', [])
        obligations_count = len(obligations) if isinstance(obligations, list) else 0
        marker_992_filled = obligations_count > 5

        special_markers = {
            "[DATE]": cleaned_data.get("date"),
            "[415]": cleaned_data.get("judge"),
            "[66]": cleaned_data.get("date"),  # [66] — дата определения о принятии заявления к производству (то же поле "дата")
            "[992]": marker_992_filled,  # Заполнен только если обязательств > 5
            # [86] и [87] обрабатываются через обычный field_mapping, не нужны в special_markers
        }

        # Специальная логика для госпошлин [16] и [17]:
        # заранее определяем, для каких маркеров реально есть суммы.
        has_state_duty_16 = bool(
            str(cleaned_data.get("stateDuty16") or cleaned_data.get("stateDuty") or "").strip()
        )
        has_state_duty_17 = bool(str(cleaned_data.get("loanStateDuty17") or "").strip())

        removed_count = 0
        # ВАЖНО: _collect_placeholders возвращает set — порядок итерации зависит от
        # рандомизации хеша строк (PYTHONHASHSEED) и менялся бы между процессами.
        # Удаление маркера с контекстом затрагивает соседнюю пунктуацию, поэтому от
        # порядка зависел итоговый текст (висячая «.» при пустых полях залога).
        # Сортируем (числовые маркеры — по значению, спецмаркеры вроде [DATE] — после),
        # чтобы вывод был детерминирован независимо от hashseed.
        def _placeholder_order(ph: str):
            m = re.match(r'\[(\d+(?:\.\d+)*)\]', ph)
            if m:
                return (0, [int(p) for p in m.group(1).split('.')], ph)
            return (1, [], ph)

        for placeholder in sorted(all_placeholders, key=_placeholder_order):
            # Маркеры обязательств (100-129) не пропускаем: если они остались после replace_obligations_data,
            # значит данные не подтянулись — удаляем маркер вместе с контекстом (фраза «кредитный договор от [100] № …» и т.п.)
            match = re.match(r'\[(\d+)\]', placeholder)
            # if match: number = int(match.group(1)); if 100 <= number < 130: continue  — убрано по требованию

            # Госпошлины [16] и [17] обрабатываем отдельно после цикла,
            # чтобы избежать ситуации, когда из-за неоднозначностей удаляются обе строки.
            if placeholder in ("[16]", "[17]"):
                continue

            # Проверяем специальные маркеры
            if placeholder in special_markers:
                marker_value = special_markers[placeholder]
                # Если значение False или пустое, удаляем маркер с контекстом
                if not marker_value:
                    # Удаляем пустой специальный маркер с контекстом
                    self._remove_placeholder_with_context(doc, placeholder)
                    removed_count += 1
                    logger.info(f"🗑️ Удален пустой специальный маркер с контекстом: {placeholder}")
                # Если значение есть, маркер уже был заменен в предыдущих шагах, пропускаем
                continue

            # Проверяем обычные маркеры через field_mapping
            if placeholder in marker_to_fields:
                # Проверяем, есть ли хотя бы одно поле с значением для этого маркера
                has_value = False
                for field_name in marker_to_fields[placeholder]:
                    value = cleaned_data.get(field_name)
                    # Проверяем, что значение не пустое и не является пустой строкой или пробелами
                    if value and str(value).strip() and str(value).strip().lower() not in ['не указано', 'не указана', 'none', 'null', '']:
                        has_value = True
                        break

                if not has_value:
                    # Удаляем пустой маркер с контекстом
                    self._remove_placeholder_with_context(doc, placeholder)
                    removed_count += 1
                    logger.info(f"🗑️ Удален пустой маркер с контекстом: {placeholder} (поля: {', '.join(marker_to_fields[placeholder])})")
            else:
                # Маркер не найден в маппинге - возможно, это неизвестный маркер
                # Проверяем, есть ли значение в cleaned_data для этого маркера (по номеру маркера)
                marker_num = placeholder.strip('[]')
                has_value_in_data = False
                # Проверяем все поля в cleaned_data, которые могут соответствовать этому маркеру
                for field_name, field_value in cleaned_data.items():
                    if field_value and str(field_value).strip() and str(field_value).strip().lower() not in ['не указано', 'не указана', 'none', 'null', '']:
                        # Если поле маппится на этот маркер, значит значение есть
                        if field_mapping.get(field_name) == marker_num:
                            has_value_in_data = True
                            break

                if not has_value_in_data:
                    # Удаляем его с контекстом, чтобы не было видно в финальном документе
                    self._remove_placeholder_with_context(doc, placeholder)
                    removed_count += 1
                    logger.info(f"🗑️ Удален неизвестный маркер с контекстом: {placeholder}")

        # После общей очистки отдельно обрабатываем госпошлины:
        # - если для [16] нет суммы — удаляем только её строку
        # - если для [17] нет суммы — удаляем только её строку
        if not has_state_duty_16:
            self._remove_placeholder_with_context(doc, "[16]")
        if not has_state_duty_17:
            self._remove_placeholder_with_context(doc, "[17]")

        if removed_count > 0:
            logger.info(f"✅ Удалено {removed_count} пустых маркеров из документа")
        else:
            logger.info("ℹ️ Пустых маркеров не найдено")

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

        # Текущий номер дела и номер обособленного спора (для устранения дублирования)
        case_number = str(data.get("caseNumber", "") or "")
        separate_dispute_number = str(data.get("separateDisputeNumber22", "") or "").strip()

        # Заменяем в параграфах
        for paragraph in doc.paragraphs:
            text = paragraph.text

            # Убираем дублирование номера обособленного спора рядом с номером дела,
            # если номер обособленного спора уже включён в сам номер дела.
            # Пример: "Дело№А53-37965-4/2025 4" -> "Дело№А53-37965-4/2025"
            if case_number and separate_dispute_number:
                pattern_case_sep = rf"({re.escape(case_number)})\s+{re.escape(separate_dispute_number)}\b"
                if re.search(pattern_case_sep, text):
                    new_text = re.sub(pattern_case_sep, r"\1", text)
                    if new_text != text:
                        paragraph.text = new_text
                        text = new_text
                        logger.info(
                            "🧹 Удалено дублирование номера обособленного спора рядом с номером дела"
                        )

            # [9] и [11] — только ЕФРСБ: номер и дата сообщения на сайте
            efirsb_date = data.get('efirsbPublicationDate', '')
            if efirsb_date and 'ЕФРСБ' in text and 'сообщение' in text:
                pattern = r'ЕФРСБ\s+сообщение[^0-9]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})'
                if re.search(pattern, text):
                    paragraph.text = re.sub(pattern, f'ЕФРСБ сообщение {efirsb_date}', text)
                    logger.info(f"Заменена дата сообщения в контексте ЕФРСБ [11]: {efirsb_date}")
                elif 'ЕФРСБ сообщение' in text and not re.search(r'ЕФРСБ\s+сообщение\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}', text):
                    paragraph.text = text.replace('ЕФРСБ сообщение', f'ЕФРСБ сообщение {efirsb_date}')
                    logger.info(f"Добавлена дата сообщения после ЕФРСБ [11]: {efirsb_date}")

            # [67] и [68] подставляются только через маркеры в шаблоне (замена в основном цикле).
            # Контекстную подстановку в абзацы с «Коммерсант» не делаем — дата и номер только в местах [68] и [67].

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

    def _resolve_standard_templates(self, data: Dict[str, Any], normalized_template: str, source_document_type: str, source_document_type_for_routing: str, is_kfh: bool):
        """Стандартный роутинг: по template_type / sourceDocumentType / процедуре
        выбирает набор шаблонов и procedure_type. Возвращает (templates, procedure_type).
        Может выставлять data['_skip_obligation_blocks']. Вынесено из generate
        без изменения поведения (gen-golden).
        """
        # Стандартная логика (для обратной совместимости и для явного выбора template_type)
        if normalized_template in {"observation_single", "observation_multiple"}:
            normalized_template = "observation"

        # ПРИОРИТЕТ: Проверяем на процедуру "умерший" в первую очередь
        if normalized_template == "deceased" or source_document_type == "deceased" or (data.get('procedureType') or '').lower() == "deceased" or any(keyword in (data.get('procedureTypeRaw') or '').lower() for keyword in ["умер", "умерший", "смерть", "смерти"]):
            # Шаблоны для процедуры "умерший" - ПРИОРИТЕТ перед всеми остальными
            templates = self._get_templates_for_procedure("deceased")
            procedure_type = "deceased"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: умерший")
        elif normalized_template == "physical_restructuring_collateral" or source_document_type_for_routing == "physical_restructuring_collateral":
            # Шаблоны для ФЛ с залогом в реструктуризации
            templates = self._get_physical_restructuring_collateral_templates()
            procedure_type = "physical_restructuring_collateral"
            logger.info(
                f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ФЛ с залогом в реструктуризации"
            )
        elif normalized_template == "physical_realization_collateral" or source_document_type_for_routing == "physical_realization_collateral":
            # Шаблоны для ФЛ с залогом в реализации
            templates = self._get_physical_collateral_templates()
            procedure_type = "physical_realization_collateral"
            logger.info(
                f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ФЛ с залогом в реализации"
            )
        elif normalized_template in ["kfh_observation", "kfh_observation_collateral"] or \
             (is_kfh and (normalized_template in ["observation", "observation_single", "observation_multiple"] or
                          source_document_type_for_routing == "observation_collateral" or
                          source_document_type_for_routing in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
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
            elif source_document_type_for_routing == "observation_collateral":
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
        elif normalized_template == "ip_collection_collateral" or source_document_type_for_routing == "ip_collection_collateral":
            # Шаблоны для искового заявления о взыскании с ИП с залогом
            templates = self._get_ip_collection_collateral_templates()
            procedure_type = "ip_collection_collateral"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ИП с залогом")
        elif normalized_template == "ip_collection_collateral_auto" or source_document_type_for_routing == "ip_collection_collateral_auto":
            # Шаблоны для искового заявления о взыскании с ИП залог авто ([1221] — описание авто)
            templates = self._get_ip_collection_collateral_auto_templates()
            procedure_type = "ip_collection_collateral_auto"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ИП залог авто")
        elif normalized_template == "legal_collection" or source_document_type_for_routing == "legal_collection":
            # Шаблоны для искового заявления о взыскании с ЮЛ
            templates = self._get_legal_collection_templates()
            procedure_type = "legal_collection"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ЮЛ")
        elif normalized_template == "legal_collection_collateral" or source_document_type_for_routing == "legal_collection_collateral":
            # Шаблоны для искового заявления о взыскании с ЮЛ с залогом
            templates = self._get_legal_collection_collateral_templates()
            procedure_type = "legal_collection_collateral"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ЮЛ с залогом")
        elif normalized_template == "legal_collection_collateral_auto" or source_document_type_for_routing == "legal_collection_collateral_auto":
            # Шаблоны для искового заявления о взыскании с ЮЛ залог авто ([1221] — описание авто)
            templates = self._get_legal_collection_collateral_auto_templates()
            procedure_type = "legal_collection_collateral_auto"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ЮЛ залог авто")
        elif normalized_template == "ip_collection" or source_document_type_for_routing == "ip_collection":
            # Шаблоны для искового заявления о взыскании с ИП
            templates = self._get_ip_collection_templates()
            procedure_type = "ip_collection"
            logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ИП")
        elif normalized_template in ["ip_enforcement", "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                     "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"] or \
             source_document_type_for_routing in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                     "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                     "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"]:
            # Определяем наличие залога
            if (
                normalized_template.endswith("_collateral")
                or source_document_type_for_routing in ["ip_enforcement_statement_collateral", "ip_enforcement_realization_collateral",
                                                        "ip_enforcement_restructuring_collateral"]
            ):
                has_collateral_flag = True
            else:
                has_collateral_flag = str(data.get("ipHasCollateral", "")).strip().lower() in {"true", "1", "yes", "да"}

            # Определяем тип процедуры
            if "restructuring" in source_document_type_for_routing or normalized_template == "ip_enforcement_restructuring":
                ip_procedure_type = "restructuring"
            else:
                ip_procedure_type = "realization"  # По умолчанию реализация

            templates = self._get_ip_enforcement_templates(has_collateral_flag, ip_procedure_type)
            procedure_type = source_document_type_for_routing or normalized_template or "ip_enforcement"
            logger.info(
                f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ИП "
                f"({ip_procedure_type}, залог: {'есть' if has_collateral_flag else 'нет'})"
            )
        elif normalized_template == "initiation_physical" or source_document_type_for_routing == "initiation_physical":
            templates = self._get_initiation_physical_templates()
            procedure_type = "initiation_physical"
            data["_skip_obligation_blocks"] = True
            logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 3 ДОКУМЕНТОВ для инициирования банкротства физического лица")
        elif normalized_template == "initiation_legal" or source_document_type_for_routing == "initiation_legal":
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
        elif normalized_template == "mortgage" or source_document_type_for_routing == "mortgage_claim":
            templates = self._get_mortgage_templates()
            procedure_type = "mortgage"
            data["_skip_obligation_blocks"] = True
            logger.info("🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ 1 ДОКУМЕНТА для ипотечного иска")
        elif normalized_template == "observation_collateral" or source_document_type_for_routing == "observation_collateral":
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
        elif normalized_template == "competition_collateral" or source_document_type_for_routing == "competition_collateral":
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
        return templates, procedure_type

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
            # Проверяем, есть ли выбранные пользователем акты (могут быть в data или в data.fields)
            fields = data.get("fields") or {}

            # Несколько должников: при 2+ авторитетно пересобираем плоские поля и падежи
            # из массива debtors (учёт правок пользователя в форме). Склейка через запятую,
            # шаблоны не меняем. Одиночный должник — поведение прежнее.
            debtors_in = data.get("debtors") or fields.get("debtors") or []
            valid_debtors = [d for d in debtors_in if isinstance(d, dict) and (d.get("name") or "").strip()]
            if len(valid_debtors) >= 2:
                try:
                    combined = DocumentAnalyzer()._combine_debtors(valid_debtors)
                    fields.update(combined)
                    data["fields"] = fields
                    for k, v in combined.items():
                        data[k] = v
                    logger.info(f"Склеено {len(valid_debtors)} должников: {combined.get('applicantName')}")
                except Exception as exc:
                    logger.warning(f"Не удалось склеить должников при генерации: {exc}")
            selected_acts_ids = data.get("selectedActsIds") or fields.get("selectedActsIds")
            selected_acts_data_str = data.get("selectedActsData") or fields.get("selectedActsData")
            selected_entity_type = data.get("selectedEntityType") or fields.get("selectedEntityType")
            selected_collateral_option = data.get("selectedCollateralOption") or fields.get("selectedCollateralOption")

            # Базовые признаки документа и шаблона
            normalized_template = (template_type or "").lower()
            source_document_type = (data.get("sourceDocumentType") or fields.get("sourceDocumentType") or "").lower()
            is_kfh = bool(data.get("isKfh") or fields.get("isKfh"))
            explicit_template_selected = bool(normalized_template)
            source_document_type_for_routing = source_document_type if not explicit_template_selected else ""

            # ВАЖНО: если пользователь ЯВНО выбрал тип акта в окне "Выбор типа судебного акта"
            # (template_type непустой: mortgage, rtk_single_obligation и т.п.),
            # мы должны уважать этот выбор и НЕ подменять его списком selectedActsIds,
            # который относится к автоматическим рекомендациям/РТК-комплектам.
            #
            # Поэтому используем selectedActs только когда template_type пустой.
            can_use_selected_acts = bool(selected_acts_ids) and not normalized_template

            # Если пользователь выбрал акты в интерфейсе (старый режим "выбор актов"),
            # и при этом нет явного template_type — используем их.
            if can_use_selected_acts:
                logger.info(f"🎯 Используем выбранные пользователем акты: {selected_acts_ids}")
                logger.info(f"📋 Тип лица: {selected_entity_type}, Залог: {selected_collateral_option}")

                # Извлекаем дополнительные поля из selectedActsData (JSON строка)
                if selected_acts_data_str:
                    try:
                        import json
                        selected_acts_list = json.loads(selected_acts_data_str)
                        for act in selected_acts_list:
                            act_id = act.get("id")
                            additional_fields = act.get("additionalFields", {})
                            rtk_variant = act.get("rtkVariant")

                            # Сохраняем rtkVariant для акта final_rtk_inclusion
                            if act_id == "final_rtk_inclusion" and rtk_variant:
                                data["final_rtk_inclusion_variant"] = rtk_variant
                                logger.info(f"📝 Вариант для final_rtk_inclusion: {rtk_variant}")

                            if additional_fields:
                                # Добавляем дополнительные поля в data для использования в шаблонах
                                reason = additional_fields.get("reason", "")
                                for_parties = additional_fields.get("forParties", "")
                                court_requests = additional_fields.get("courtRequests", "")
                                if act_id == "acceptance_no_motion_other":
                                    data["acceptance_no_motion_other_reason"] = reason
                                    data["acceptance_no_motion_other_forParties"] = for_parties
                                elif act_id == "intermediate_return":
                                    data["intermediate_return_reason"] = reason
                                    data["intermediate_return_forParties"] = for_parties
                                elif act_id == "intermediate_postponement":
                                    data["intermediate_postponement_reason"] = reason
                                    data["intermediate_postponement_forParties"] = for_parties
                                    data["intermediate_postponement_courtRequests"] = court_requests
                                    logger.info(f"📝 Дополнительные поля для {act_id}: reason={reason[:50]}..., forParties={for_parties[:50]}..., courtRequests={court_requests[:50]}...")
                                elif act_id == "acceptance_definition":
                                    data["acceptance_definition_courtRequests"] = court_requests
                                    logger.info(f"📝 Дополнительные поля для {act_id}: courtRequests={court_requests[:50]}...")
                                elif act_id == "acceptance_after_no_motion":
                                    data["acceptance_after_no_motion_courtRequests"] = court_requests
                                    logger.info(f"📝 Дополнительные поля для {act_id}: courtRequests={court_requests[:50]}...")
                                else:
                                    logger.info(f"📝 Дополнительные поля для {act_id}: reason={reason[:50]}..., forParties={for_parties[:50]}...")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось распарсить selectedActsData: {e}")

                templates = self._map_selected_acts_to_templates(
                    selected_acts_ids,
                    selected_entity_type or data.get("entityType") or fields.get("entityType", "individual"),
                    selected_collateral_option or "no_collateral",
                    data
                )

                if templates:
                    logger.info(f"✅ Найдено {len(templates)} шаблонов для выбранных актов")
                    procedure_type = "custom_selected_acts"
                else:
                    logger.warning("⚠️ Не найдено шаблонов для выбранных актов, используем стандартную логику")
                    templates = None

            # Если templates не был установлен выше (стандартная логика), устанавливаем его здесь
            use_standard_logic = 'templates' not in locals() or templates is None or len(templates) == 0

            if use_standard_logic:
                templates, procedure_type = self._resolve_standard_templates(
                    data, normalized_template, source_document_type,
                    source_document_type_for_routing, is_kfh,
                )
            # Если templates не был установлен выше (стандартная логика), он должен быть установлен в блоке else
            if 'templates' not in locals() or templates is None:
                logger.error("❌ Не удалось определить шаблоны для генерации")
                return {
                    "success": False,
                    "error": "Не удалось определить шаблоны для генерации документов"
                }

            logger.info(f"📊 Полученные данные: {data}")
            logger.info(f"📋 Будет сгенерировано {len(templates)} документов")

            generated_documents = {}
            document_ids = []

            # Генерируем каждый документ
            for doc_type, template_info in templates.items():
                logger.info(f"📄 Генерируем документ: {template_info['name']}")

                template_path = self._resolve_template_path(template_info['path'])
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

            # Проверяем, были ли сгенерированы документы
            if len(generated_documents) == 0:
                missing_templates = []
                for doc_type, template_info in templates.items():
                    if not template_info['path'].exists():
                        missing_templates.append(f"{template_info['name']} ({template_info['path'].absolute()})")

                error_message = f"Не найдены шаблоны документов. Отсутствующие файлы:\n" + "\n".join(missing_templates)
                logger.error(error_message)
                return {
                    "success": False,
                    "error": error_message
                }

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
