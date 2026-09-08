import os
import sys
import time
import uuid
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Set, List
from docx import Document
from docx.document import Document as DocxDocument
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.shared import OxmlElement, qn
# Локальный импорт анализатора без package-префикса, чтобы работать при запуске из app/
from claim_resolution import CLAIM_RESOLUTION_TEXTS, PARTIAL, build_partial_denial
from document_analyzer import DocumentAnalyzer
from templates_resolver_mixin import TemplatesResolverMixin
from generator_inflection_mixin import GeneratorInflectionMixin
from docx_ops_mixin import DocxOpsMixin
from obligations_render_mixin import ObligationsRenderMixin
from formatting_mixin import FormattingMixin
import paths

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentGenerator(TemplatesResolverMixin, GeneratorInflectionMixin, DocxOpsMixin, ObligationsRenderMixin, FormattingMixin):
    def __init__(self):
        """
        Инициализация генератора документов
        """
        self.generated_dir = paths.generated_dir()

        self.documents = {}

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
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                me = Path(meipass)
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

    def _resolve_template_path(self, path: Path, allow_any_docx_fallback: bool = True) -> Path:
        """
        Если шаблон не найден — ищем по fallback: корень проекта, альтернативные имена,
        любой .docx в той же папке, папки шаблоны актов без залогов в корне проекта.

        allow_any_docx_fallback=False отключает последний шаг («любой .docx в папке»).
        Этот шаг подставляет ПРОИЗВОЛЬНЫЙ акт, когда нужного файла нет: «О введении
        наблюдения» «О введении конкурсное ликвидируемый», «Продление Б/Д»
        «Реализация ВКЛ несколько договоров». Для актов, ЯВНО выбранных пользователем,
        это недопустимо (решение Андрея): лучше честно сообщить, что шаблона нет, чем
        выдать под видом выбранного акта другой. Для стандартного роутинга шаг оставлен.
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
            # Любой .docx в папке — только когда подмена произвольным актом допустима
            if not allow_any_docx_fallback:
                continue
            try:
                for f in sorted(search_dir.glob("*.docx")):
                    logger.info(f"Используем шаблон из папки {search_dir.name}: {f.name}")
                    return f
            except Exception:
                # Без лога сбой обхода каталога неотличим от «шаблонов нет»,
                # а наружу уезжает одинаковое «не найдены шаблоны документов».
                logger.debug(f"Не удалось прочитать каталог шаблонов {search_dir}", exc_info=True)

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

    @staticmethod
    def _extract_org_short_name(candidates: List[Optional[str]]) -> Optional[str]:
        """Достаёт чистое короткое наименование организации из списка кандидатов.

        Приоритет — содержимое ёлочек «...» (канонический формат debtorName:
        «ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ОРГТЕХНИКА»» ОРГТЕХНИКА).
        Ёлочки берём раньше остального, потому что legalShortName иногда приходит
        кривым ('ОРГТЕХНИКА" (ООО "ОРГТЕХНИКА")') и извлечение из прямых кавычек
        давало мусор «(ООО». Если ёлочек нет ни у одного кандидата — срезаем
        орг-правовую «шапку» (ООО/общество с ограниченной ответственностью) и
        обрамляющие кавычки у первого непустого кандидата. Возвращает None, если
        ничего осмысленного не нашлось.
        """
        def _clean(s: str) -> str:
            return s.strip(" -\t\n\r«»\"'()")

        # Проход 1: ёлочки «...» — самый надёжный источник.
        for cand in candidates:
            if not cand:
                continue
            m = re.search(r'«\s*([^«»]+?)\s*»', str(cand))
            if m:
                name = _clean(m.group(1))
                if name and '(' not in name and ')' not in name:
                    return name

        # Проход 2: срезаем ОПФ-шапку у первого непустого кандидата.
        for cand in candidates:
            if not cand:
                continue
            s = re.sub(
                r'^(?:ИП\s+)?(?:общество|общества)\s+с\s+ограниченн\w+\s+ответственн\w+\s+',
                '',
                str(cand),
                flags=re.IGNORECASE,
            )
            # Если внутри прямые кавычки "..." — берём первый чистый (без скобок) токен.
            m2 = re.search(r'"\s*([^"()]+?)\s*"', s)
            if m2:
                name = _clean(m2.group(1))
                if name:
                    return name
            name = _clean(s)
            if name and '(' not in name and ')' not in name:
                return name
        return None

    def clean_extracted_value(self, value: str) -> str:
        """Очищает извлеченное значение от звездочек и других маскирующих символов"""
        if not value:
            return value

        cleaned = re.sub(r'\*+', '', value)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()

        return cleaned

    def _prepare_replacement_data(self, doc: DocxDocument, data: Dict[str, Any]) -> Dict[str, Any]:
        """Подготовка cleaned_data для подстановки: очистка от звёздочек,
        нормализация ЮЛ/КФХ/ИП, адреса, дат, синхронизация и форматирование сумм,
        поля промежуточных актов и третьих лиц. Возвращает cleaned_data.
        Вынесено из replace_document_data без изменения поведения (gen-golden).
        """
        logger.info("Заменяем данные в документе")
        logger.info(f"Данные для замены: {data}")

        cleaned_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned_data[key] = self.clean_extracted_value(value)
            elif isinstance(value, list):
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
        logger.info(f" Ключевые поля в cleaned_data: creditorName={cleaned_data.get('creditorName')}, inn={cleaned_data.get('inn')}, creditorAddress={cleaned_data.get('creditorAddress')}")

        # Для ЮЛ используем короткое наименование в [2]/[2.1]/[2.2], чтобы не тянуть
        # артефакты вроде "ИП Общества..." и некорректные ФИО-падежи.
        if (cleaned_data.get("entityType") or "").strip().lower() == "legal":
            # Приоритет кандидатов: debtorName (канонический «…»-формат) впереди
            # legalShortName, т.к. legalShortName иногда приходит кривым
            # ('ОРГТЕХНИКА" (ООО "ОРГТЕХНИКА")') и ломает извлечение «(ооо».
            legal_name = self._extract_org_short_name([
                cleaned_data.get("debtorName"),
                cleaned_data.get("legalShortName"),
                cleaned_data.get("applicantName"),
            ])
            if legal_name:
                cleaned_data["applicantName"] = legal_name
                cleaned_data["applicantNameGenitive"] = legal_name
                cleaned_data["applicantNameDative"] = legal_name
                cleaned_data["applicantNameInstrumental"] = legal_name
                cleaned_data["applicantNameAccusative"] = legal_name
                cleaned_data["legalShortName"] = legal_name
                logger.info(f" Для ЮЛ нормализовано имя должника: {legal_name}")


        creditor_name = str(cleaned_data.get("creditorName") or "").strip()
        if creditor_name:
            if creditor_name.upper().startswith("ФНС"):
                # ФНС: в шаблонах маркер [989] стоит ПОСЛЕ "ФНС России в лице", поэтому
                # кладём в [989] только часть после "в лице" (иначе "ФНС России в лице
                # ФНС России в лице …" — дублирование). Регистр НЕ нормализуем — там
                # аббревиатуры ИФНС/УФНС, которые title-case ломает (ИФНС Ифнс).
                cleaned_data["_fnsCreditor"] = True
                m = re.match(r'^\s*ФНС\s+России\s+в\s+лице\s+(.+)$', creditor_name,
                             re.IGNORECASE | re.DOTALL)
                if m:
                    inspection = re.sub(r'\s+', ' ', m.group(1)).strip(' ,.')
                    cleaned_data["creditorName"] = inspection
                    logger.info(f"ФНС: в [989] подставим инспекцию: {inspection}")
            else:
                normalized_creditor_name = self._extract_org_short_name([creditor_name]) or creditor_name
                if normalized_creditor_name and normalized_creditor_name != creditor_name:
                    cleaned_data["creditorName"] = normalized_creditor_name
                    logger.info(f"Для кредитора-ЮЛ нормализовано название: {normalized_creditor_name}")

        # Адрес должника/заявителя не должен совпадать с адресом кредитора (частая ошибка извлечения)
        applicant_addr = (cleaned_data.get("applicantAddress") or "").strip()
        creditor_addr = (cleaned_data.get("creditorAddress") or "").strip()
        if applicant_addr and creditor_addr and applicant_addr == creditor_addr:
            cleaned_data["applicantAddress"] = ""
            logger.warning("Адрес заявителя совпадал с адресом кредитора — очищен (маркер [6] останется пустым)")

        # [11] — только дата публикации на сайте ЕФРСБ (не подставляем дату Коммерсанта)
        # Для газеты «Коммерсантъ» используются [67] (номер) и [68] (дата)
        if not cleaned_data.get("efirsbPublicationDate"):
            # Fallback только из полей, связанных с ЕФРСБ/сообщением, не из messageDate (может быть Коммерсант)
            for field in ("publicationDate",):
                value = cleaned_data.get(field)
                if value:
                    cleaned_data["efirsbPublicationDate"] = value
                    logger.info("Используем %s как efirsbPublicationDate для плейсхолдера [11]", field)
                    break

        entity_type = (cleaned_data.get("entityType") or "").lower()
        source_doc_type = (cleaned_data.get("sourceDocumentType") or "").lower()
        is_ip = "ip_enforcement" in source_doc_type
        is_kfh = bool(cleaned_data.get("isKfh"))

        # Очистка имени для КФХ: убираем "ГЛАВА КФХ ИП" и оставляем только ФИО
        if is_kfh:
            kfh_head_name = cleaned_data.get("kfhHeadName", "")
            if kfh_head_name:
                cleaned_data["applicantName"] = kfh_head_name
                logger.info(f"Используем kfhHeadName для КФХ: '{kfh_head_name}'")
            else:
                applicant_name = cleaned_data.get("applicantName", "")
                if applicant_name:
                    cleaned_name = re.sub(
                        r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                        '',
                        applicant_name,
                        flags=re.IGNORECASE
                    ).strip()
                    if cleaned_name:
                        cleaned_data["applicantName"] = cleaned_name
                        logger.info(f"Очищено имя КФХ: '{applicant_name}' -> '{cleaned_name}'")

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
                        logger.info(f"Очищено debtorName КФХ: '{debtor_name}' -> '{cleaned_debtor_name}'")

            kfh_head_name = cleaned_data.get("kfhHeadName", "")
            if kfh_head_name:
                analyzer = DocumentAnalyzer()

                genitive = analyzer._convert_name_to_genitive(kfh_head_name)
                if genitive:
                    cleaned_data["applicantNameGenitive"] = genitive
                    logger.info(f"КФХ: пересоздан applicantNameGenitive из kfhHeadName: '{genitive}'")

                instrumental = analyzer._convert_name_to_instrumental(kfh_head_name)
                if instrumental:
                    cleaned_data["applicantNameInstrumental"] = instrumental
                    logger.info(f"КФХ: пересоздан applicantNameInstrumental из kfhHeadName: '{instrumental}'")

                accusative = analyzer._convert_name_to_accusative(kfh_head_name)
                if accusative:
                    cleaned_data["applicantNameAccusative"] = accusative
                    logger.info(f"КФХ: пересоздан applicantNameAccusative из kfhHeadName: '{accusative}'")
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
                            logger.info(f" Очищено {field_name} КФХ: '{field_value}' -> '{cleaned_field_value}'")

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
            logger.info(f" Проверка полей для ИП: birthDate={cleaned_data.get('birthDate')}, snils={cleaned_data.get('snils')}, ipCollateralContractNumber={cleaned_data.get('ipCollateralContractNumber')}")

        # Проверяем наличие новых полей
        new_fields = ['principalDebt13', 'interest14', 'forfeit15', 'stateDuty16']
        for field in new_fields:
            if field in cleaned_data:
                logger.info(f"Найдено поле {field}: {cleaned_data[field]}")
            else:
                logger.info(f"Поле {field} НЕ НАЙДЕНО в cleaned_data")

        # Проверяем наличие полей для ИП
        ip_fields = ['birthDate', 'snils', 'ipCollateralContractNumber', 'ipCollateralContractDate', 'ipCollateralClaimAmount']
        for field in ip_fields:
            if field in cleaned_data:
                logger.info(f"Найдено поле ИП {field}: {cleaned_data[field]}")
            else:
                logger.info(f"Поле ИП {field} НЕ НАЙДЕНО в cleaned_data")

        # Очистка адреса от маркера [6] для процедуры "умерший"
        procedure_type = (cleaned_data.get('procedureType') or '').lower()
        procedure_type_raw = (cleaned_data.get('procedureTypeRaw') or '').lower()
        if procedure_type == "deceased" or any(keyword in procedure_type_raw for keyword in ["умер", "умерший", "смерть", "смерти"]):
            applicant_address = cleaned_data.get("applicantAddress", "")
            if applicant_address:
                cleaned_address = re.sub(r'\s*\[6\]\s*', ' ', applicant_address, flags=re.IGNORECASE).strip()
                if cleaned_address != applicant_address:
                    cleaned_data["applicantAddress"] = cleaned_address
                    logger.info(f"Очищен адрес для умершего: '{applicant_address}' -> '{cleaned_address}'")

        current_date = datetime.now().strftime("%d.%m.%Y")
        cleaned_data["currentDate"] = current_date
        logger.info(f"Текущая дата формирования акта: {current_date}")

        # Обработка пользовательской даты: YYYY-MM-DD (из input type="date") -> DD.MM.YYYY
        date_value = cleaned_data.get("date")
        if date_value:
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
                try:
                    date_obj = datetime.strptime(date_value, "%Y-%m-%d")
                    cleaned_data["date"] = date_obj.strftime("%d.%m.%Y")
                    logger.info(f"Конвертирована дата: {date_value} -> {cleaned_data['date']}")
                except ValueError:
                    logger.warning(f"Не удалось распарсить дату: {date_value}")

        if cleaned_data.get("loanDebt") and not cleaned_data.get("principalDebt"):
            cleaned_data["principalDebt"] = cleaned_data["loanDebt"]
            cleaned_data["principalDebt13"] = cleaned_data["loanDebt"]
        elif cleaned_data.get("principalDebt") and not cleaned_data.get("loanDebt"):
            cleaned_data["loanDebt"] = cleaned_data["principalDebt"]

        if cleaned_data.get("interest") and not cleaned_data.get("interest14"):
            cleaned_data["interest14"] = cleaned_data["interest"]
        elif cleaned_data.get("interest14") and not cleaned_data.get("interest"):
            cleaned_data["interest"] = cleaned_data["interest14"]

        if cleaned_data.get("forfeit") and not cleaned_data.get("forfeit15"):
            cleaned_data["forfeit15"] = cleaned_data["forfeit"]
        elif cleaned_data.get("forfeit15") and not cleaned_data.get("forfeit"):
            cleaned_data["forfeit"] = cleaned_data["forfeit15"]

        if cleaned_data.get("penalties") and not cleaned_data.get("forfeit15"):
            cleaned_data["forfeit15"] = cleaned_data["penalties"]
            cleaned_data["forfeit"] = cleaned_data["penalties"]

        if cleaned_data.get("stateDuty") and not cleaned_data.get("stateDuty16"):
            cleaned_data["stateDuty16"] = cleaned_data["stateDuty"]
        elif cleaned_data.get("stateDuty16") and not cleaned_data.get("stateDuty"):
            cleaned_data["stateDuty"] = cleaned_data["stateDuty16"]

       
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
                        "totalDebt", "debtAmount", "bankCommission", "priorAmount", "priorStateDuty",
                        # ФНС-суммы по очередям реестра (недоимка/штрафы/пени/осн.долг/подытоги)
                        "fnsQ1Arrears", "fnsQ2Arrears", "fnsQ3Arrears",
                        "fnsQ3Penalties", "fnsQ3Forfeit", "fnsQ3LoanDebt",
                        "fnsQ1Total", "fnsQ2Total", "fnsQ3Total"]
        for field in amount_fields:
            if field in cleaned_data and cleaned_data[field]:
                raw = str(cleaned_data[field]).strip()

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
                    logger.info(f"Форматирована сумма {field}: {formatted}")

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

            if "totalDebt" not in cleaned_data and cleaned_data.get("debtAmount"):
                cleaned_data["totalDebt"] = cleaned_data["debtAmount"]

            if "debtAmount" not in cleaned_data and cleaned_data.get("totalDebt"):
                cleaned_data["debtAmount"] = cleaned_data["totalDebt"]

            # Для ip_collection, ip_collection_collateral и ip_collection_collateral_auto проверяем наличие полей [1000], [1001], [1004]
            if source_document_type in ("ip_collection", "ip_collection_collateral", "ip_collection_collateral_auto"):
                logger.info(f"Проверка полей для ip_collection:")
                logger.info(f"  creditAmount [1000]: {cleaned_data.get('creditAmount')}")
                logger.info(f"  creditTermMonths [1001]: {cleaned_data.get('creditTermMonths')}")
                logger.info(f"  debtSnapshotDate [1004]: {cleaned_data.get('debtSnapshotDate')}")
                if not cleaned_data.get('creditAmount'):
                    logger.warning(f"Поле creditAmount [1000] не найдено для ip_collection")
                if not cleaned_data.get('creditTermMonths'):
                    logger.warning(f"Поле creditTermMonths [1001] не найдено для ip_collection")
                if not cleaned_data.get('debtSnapshotDate'):
                    logger.warning(f"Поле debtSnapshotDate [1004] не найдено для ip_collection")

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
            logger.info(f"Установлено поле reason86 (маркер [86]): {reason[:100]}...")
        if for_parties:
            cleaned_data['forParties87'] = for_parties
            logger.info(f"Установлено поле forParties87 (маркер [87]): {for_parties[:100]}...")

        # Заполняем поле [85] (запросы суда) для актов "Отложение", "Определение о принятии", "Принятие после Б/Д"
        court_requests = (
            cleaned_data.get('intermediate_postponement_courtRequests') or
            cleaned_data.get('acceptance_definition_courtRequests') or
            cleaned_data.get('acceptance_after_no_motion_courtRequests') or
            ''
        )
        if court_requests:
            cleaned_data['courtRequests85'] = court_requests
            logger.info(f"Установлено поле courtRequests85 (маркер [85]): {court_requests[:100]}...")

        
        interested = self._collect_interested_persons(cleaned_data)
        if interested:
            cleaned_data['thirdPartyName25'] = interested[0]['name']
            logger.info(f"Установлено поле thirdPartyName25 (маркер [25]): {interested[0]['name'][:100]}")

            for idx, person in enumerate(interested[:self.MAX_INTERESTED_SLOTS], start=1):
                cleaned_data[f'interestedName25_{idx}'] = person['name']
                cleaned_data[f'interestedBirthDate52_{idx}'] = person['birthDate']
                cleaned_data[f'interestedAddress54_{idx}'] = person['address']
            logger.info(f"Заинтересованных лиц в пуле: {len(interested)}")
        return cleaned_data

    # Слотов под заинтересованных лиц в легенде маркеров: [25.1]-[25.5]
    MAX_INTERESTED_SLOTS = 5

    @staticmethod
    def _collect_interested_persons(cleaned_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Единый пул заинтересованных лиц: наследники, затем третьи лица.

        Заинтересованное лицо = наследник = третье лицо (решение от 16.07) — в маркеры
        подставляется любой из них, они равны. Порядок: сначала heirs, следом thirdParties.
        Место рождения ([53.x]) в пул не входит: такого поля нет ни у наследника, ни у
        третьего лица — маркер вычищается из текста (_cleanup_empty_person_components).
        """
        persons: List[Dict[str, str]] = []

        def _add(raw: Any) -> None:
            if not isinstance(raw, dict):
                return
            name = str(raw.get('name') or '').strip()
            if not name:
                return
            persons.append({
                'name': name,
                'birthDate': str(raw.get('birthDate') or '').strip(),
                'address': str(raw.get('address') or '').strip(),
            })

        for source_key in ('heirs', 'thirdParties'):
            source = cleaned_data.get(source_key)
            if isinstance(source, list):
                for raw_person in source:
                    _add(raw_person)

        # Легаси-путь: плоские поля thirdParty* (когда массивов нет вообще)
        if not persons and cleaned_data.get('thirdPartyName'):
            _add({
                'name': cleaned_data.get('thirdPartyName'),
                'birthDate': cleaned_data.get('thirdPartyBirthDate'),
                'address': cleaned_data.get('thirdPartyAddress'),
            })

        return persons

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
            if cleaned_data.get("applicantNameDative"):
                field_mapping["applicantNameDative"] = "2.2"
                field_mapping.pop("mortgageRepresentative22", None)
                logger.info(f"Используем applicantNameDative для [2.2]: {cleaned_data.get('applicantNameDative')}")

        if is_mortgage_document:
            field_mapping = dict(field_mapping)
            # НОВАЯ схема финансов ипотеки (ипотека_маркера.md, разд. 2 «Финансовые данные»):
            #   [12]=общая сумма долга, [13]=осн.долг, [14]=проценты, [15]=неустойка,
            #   [16]=госпошлина, [1360]=итог, [1361]=досуд.экспертиза, [1362]=неустойка за проценты.
            # База уже даёт totalDebt→12, principalDebt→13, interest→14, forfeit→15,
            # stateDuty→16 — их НЕ трогаем. Снимаем только старую ипотечную схему
            # ([10]/[11]/[12]-проценты) и переносим досуд.экспертизу [16]→[1361].
            # Старая ипотечная схема ([10]/[11]/[12]-проценты, [111]-[114]) удалена из
            # базового маппинга целиком — ни один ипотечный шаблон её не использует.
            # Детали кредита теперь [1000]-[1003], номера договоров — [110]-[115].
            field_mapping["mortgageCreditAmount111"] = "1000"
            field_mapping["mortgageCreditTerm112"] = "1001"
            field_mapping["mortgageInterestRate113"] = "1002"
            field_mapping["mortgagePenaltyRate114"] = "1003"
            field_mapping["pretrialExpenses16"] = "1361"
            field_mapping["pretrialExpenses"] = "1361"
            field_mapping["totalWithDuty1360"] = "1360"           # [1360] - итоговая сумма
            # Представитель истца (ипотека_маркера.md, разд. «Представители»):
            #   [1440]=ФИО, [1441]=доверенность с, [1442]=доверенность по.
            # Фронт кладёт ФИО в representativeName (mortgageRepresentative22 копируется
            # в него на форме), даты — representativePoaFrom/To (уже ДД.ММ.ГГГГ).
            # Каноним — representativeName; старый ключ убираем, чтобы пустой не затирал [1440].
            if not cleaned_data.get("representativeName") and cleaned_data.get("mortgageRepresentative22"):
                cleaned_data["representativeName"] = cleaned_data["mortgageRepresentative22"]
            field_mapping.pop("mortgageRepresentative22", None)
            field_mapping["representativeName"] = "1440"
            field_mapping["representativePoaFrom"] = "1441"
            field_mapping["representativePoaTo"] = "1442"
            # [1302] — вышестоящая инстанция (извещение: «поручением [1302]»,
            # «в здании [1302]», «направлено в [1302]», подпись). Основные вхождения —
            # родительный («поручением [суда]», «в здании [суда]»), поэтому склоняем
            # higherCourt в родительный (решение Андрея 31.07.2026). В шаблоне убрано
            # лишнее слово «суда» после [1302] — склонённая форма уже включает «суда».
            higher_court = (cleaned_data.get("higherCourt") or "").strip()
            if higher_court:
                cleaned_data["higherCourtGenitive1302"] = self._court_name_to_case(higher_court, "gent", agree_gender="masc")
                field_mapping["higherCourtGenitive1302"] = "1302"
                # [1302.1] — та же инстанция в ИМЕНИТЕЛЬНОМ: «дело будет направлено
                # в Ростовский областной суд». Родительный [1302] там давал
                # «направлено в Ростовского областного суда».
                cleaned_data["higherCourtNominative1302_1"] = higher_court
                field_mapping["higherCourtNominative1302_1"] = "1302.1"
            else:
                field_mapping["higherCourt"] = "1302"  # пусто → мягкая чистка сотрёт маркер
                field_mapping["higherCourtNominative1302_1"] = "1302.1"
            # [1308] адрес здания вышестоящей инстанции, [1309] адрес для почтовой
            # корреспонденции вышестоящей инстанции — новые поля формы (извещение).
            field_mapping["higherCourtAddress"] = "1308"
            field_mapping["higherCourtPostalAddress"] = "1309"
            # Добавляем mortgageDebtorName в маппинг для [2]
            field_mapping["mortgageDebtorName"] = "2"
            # [100]/[110] обычно заполняет replace_obligations_data из массива
            # obligations. Но в ипотечной форме договор один и приходит плоскими
            # contractNumber/contractDate — без массива маркеры оставались пустыми,
            # и зачистка уносила вместе с ними всю фразу «задолженность по
            # кредитному договору № … от … за период … в размере …».
            _obligations = cleaned_data.get("obligations")
            if isinstance(_obligations, list) and _obligations:
                field_mapping.pop("contractDate", None)
                field_mapping.pop("contractNumber", None)
            else:
                field_mapping["contractDate"] = "100"
                field_mapping["contractNumber"] = "110"
                logger.info("Ипотека без массива обязательств — [100]/[110] из contractDate/contractNumber")

            # [1360] «а всего взыскать» = общая сумма долга + госпошлина.
            if not cleaned_data.get("totalWithDuty1360"):
                def _amount_to_num(raw: str) -> float:
                    s = re.sub(r"[^\d.,]", "", re.sub(r"\s", "", str(raw or "")))
                    if not s:
                        return 0.0
                    if "," in s:  # запятая — десятичный разделитель, точки — разряды
                        s = s.replace(".", "").replace(",", ".")
                    try:
                        return float(s)
                    except ValueError:
                        return 0.0
                _total = _amount_to_num(cleaned_data.get("totalDebt"))
                _duty = _amount_to_num(cleaned_data.get("stateDuty16") or cleaned_data.get("stateDuty"))
                if _total:
                    cleaned_data["totalWithDuty1360"] = self._format_amount_value(_total + _duty)

            # Родительный падеж названия суда для акта ([002.1]). Приоритет —
            # значение из формы (mortgageCourtNameGenitive — «якорь» справочника,
            # гарантированно верная форма); иначе склоняем название суда морфологией.
            court_gen = (cleaned_data.get("mortgageCourtNameGenitive") or "").strip()
            if not court_gen:
                court_src = cleaned_data.get("mortgageCourtName002") or cleaned_data.get("courtName") or ""
                court_gen = self._court_name_to_genitive(court_src)
            if court_gen:
                cleaned_data["mortgageCourtNameGenitive"] = court_gen
                field_mapping["mortgageCourtNameGenitive"] = "002.1"
                logger.info(f"Родительный падеж названия суда для [002.1]: {court_gen}")
            # Новые маркеры суда/извещения (спека §2, §3.2): эл. почта, сайт, дата
            # исходящего письма. Поля приходят с формы плоскими editedFields.
            field_mapping["courtEmail"] = "1300"
            field_mapping["courtSite"] = "1301"
            field_mapping["noticeDate"] = "1310"
            # [1304] УИД дела, [1306] категория дела — только с формы, источника в
            # заявлении нет. [1307] город вынесения акта выводим из названия суда
            # («Октябрьский районный суд г. Ростова-на-Дону» → «г. Ростов-на-Дону»):
            # отдельного поля на форме нет, а без маркера зачистка резала соседнюю
            # дату (см. _is_clause_boundary).
            field_mapping["caseUid1304"] = "1304"
            field_mapping["caseCategory1306"] = "1306"
            field_mapping["actCity1307"] = "1307"
            # [7] дата решения. Форма пишет «Дату принятия решения» в общее поле
            # date (оттуда же берётся [66] для определений), а [7] завязан на
            # courtDecisionDate — без бэкфилла маркер оставался пустым и уносил
            # с собой «г.» перед городом («14.08.2026 г. Новороссийск» → «Новороссийск»).
            if not cleaned_data.get("courtDecisionDate") and cleaned_data.get("date"):
                cleaned_data["courtDecisionDate"] = cleaned_data["date"]
                logger.info(f"[7] дата решения из поля date: {cleaned_data['date']}")
            # Маркеры, которые есть в шаблонах, но до сих пор не были заведены. Пустой
            # маркер не просто не заполняется — зачистка уносит вместе с ним соседнюю
            # фразу, поэтому дыры в маппинге дороже, чем кажутся.
            field_mapping["forfeitInterest1362"] = "1362"       # неустойка за просроченные проценты
            field_mapping["stateDutyLocalBudget1363"] = "1363"  # госпошлина в доход местного бюджета
            field_mapping["milCzzContractNumber"] = "1378"      # № договора ЦЖЗ (военная ипотека)
            field_mapping["milCzzContractDate"] = "1379"        # дата договора ЦЖЗ
            field_mapping["creditorBranchAddress1443"] = "1443"  # адрес филиала истца
            if not cleaned_data.get("actCity1307"):
                city = self._city_from_court_name(cleaned_data.get("courtName"))
                if city:
                    cleaned_data["actCity1307"] = city
                    logger.info(f"Город вынесения акта [1307] из названия суда: {city}")
            # [001] адрес суда: форма шлёт courtAddress, маркер завязан на
            # mortgageCourtAddress001 — бэкфилл, чтобы шапка извещения заполнялась.
            if not cleaned_data.get("mortgageCourtAddress001") and cleaned_data.get("courtAddress"):
                cleaned_data["mortgageCourtAddress001"] = cleaned_data["courtAddress"]
            # [99] дата+время заседания: нормализуем ЗАРАНЕЕ (datetime-local
            # «2026-08-08T20:42» → «08.08.2026 20:42»), иначе не-анкорная замена дат
            # оставляет ISO-разделитель «T» в акте («08.08.2026T20:42»).
            _hearing = str(cleaned_data.get("courtHearingDateTime99") or "").strip()
            if "T" in _hearing:
                cleaned_data["courtHearingDateTime99"] = self._normalize_date_format(_hearing)
            # Предмет ипотеки — новые маркеры (спека §2 «Предмет ипотеки»).
            field_mapping["mortgageCadastralNumber1226"] = "1226"
            field_mapping["mortgagePropertyAddress1227"] = "1227"
            field_mapping["mortgageNpcStrategy1228"] = "1228"
            field_mapping["mortgageEgrnRecord1229"] = "1229"
            field_mapping["mortgageEgrnRecordDate1230"] = "1230"
            field_mapping["mortgageDduContract1231"] = "1231"
            field_mapping["mortgageDduDate1232"] = "1232"
            field_mapping["mortgagePropertyArea1233"] = "1233"
            field_mapping["mortgageSaleMethod1234"] = "1234"
            # ЦЖЗ / Росвоенипотека [1370]-[1377]: данных в заявлении нет — юрист вводит
            # их вручную в финблоке формы (военная ипотека). Ключи mil* — как на фронте.
            field_mapping["milPrincipalCzz"] = "1370"      # осн. долг по ЦЖЗ
            field_mapping["milInterestRate"] = "1371"      # процентная ставка
            field_mapping["milPenaltyRate"] = "1372"       # ставка пени
            field_mapping["milInterestPeriodFrom"] = "1373"  # период начисления процентов с
            field_mapping["milInterestPeriodTo"] = "1374"    # период по
            field_mapping["milLoanInterest"] = "1375"      # проценты за пользование займом
            field_mapping["milPenaltySum"] = "1376"        # пени
            field_mapping["milTotalClaim"] = "1377"        # общая сумма взыскания
            field_mapping["cjzClaimant1381"] = "1381"      # ФГКУ Росвоенипотека (взыскатель)
            # Для ипотеки используем mortgageDebtorName или debtorName вместо applicantName для [2]
            def strip_ooo(name: str) -> str:
                """Remove ООО/Общество с ограниченной ответственностью prefix to leave only the org name."""
                if not name:
                    return name
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
                    # Родительный [2.1] — только при спец-условии (сохраняем поведение).
                    if applicant_name_genitive and "суд" in applicant_name_genitive.lower():
                        genitive_name = self._decline_person_name(mortgage_debtor_name, "gent")
                        cleaned_data["applicantNameGenitive"] = genitive_name
                        field_mapping["applicantNameGenitive"] = "2.1"
                        logger.info(f"Преобразовано mortgageDebtorName в родительный падеж для [2.1]: {genitive_name}")

                    # Дательный [2.2] — с учётом женского рода (Нуриева -> Нуриевой).
                    dative_name = self._decline_person_name(mortgage_debtor_name, "datv")
                    cleaned_data["mortgageDebtorNameDative"] = dative_name
                    field_mapping["mortgageDebtorNameDative"] = "2.2"
                    # Творительный [2.3] «заключённый между … и <должник>»: для ипотеки
                    # это ДОЛЖНИК, а не ЮЛ/суд из applicantNameInstrumental — перезаписываем.
                    cleaned_data["applicantNameInstrumental"] = self._decline_person_name(mortgage_debtor_name, "ablt")
                    # Представитель истца теперь [1440], ответчику [2.2] он больше не мешает.
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
                    # Родительный [2.1] — только при спец-условии (сохраняем поведение).
                    if applicant_name_genitive and "суд" in applicant_name_genitive.lower():
                        genitive_name = self._decline_person_name(debtor_name, "gent")
                        cleaned_data["applicantNameGenitive"] = genitive_name
                        field_mapping["applicantNameGenitive"] = "2.1"
                        logger.info(f"Преобразовано debtorName в родительный падеж для [2.1]: {genitive_name}")

                    # Дательный [2.2] — с учётом женского рода (Нуриева -> Нуриевой).
                    dative_name = self._decline_person_name(debtor_name, "datv")
                    cleaned_data["mortgageDebtorNameDative"] = dative_name
                    field_mapping["mortgageDebtorNameDative"] = "2.2"
                    # Творительный [2.3] «заключённый между … и <должник>».
                    cleaned_data["applicantNameInstrumental"] = self._decline_person_name(debtor_name, "ablt")
                    logger.info(f"Преобразовано debtorName в дательный падеж для [2.2]: {dative_name}")
                except Exception as e:
                    logger.warning(f"Не удалось преобразовать debtorName в падежи: {e}")
            elif current_applicant_name and "суд" in current_applicant_name.lower():
                logger.warning(f"applicantName содержит 'суд' ({current_applicant_name}), не используем для [2]. mortgageDebtorName: {mortgage_debtor_name}, debtorName: {debtor_name[:100] if debtor_name else 'None'}")
            else:
                logger.warning(f"Не удалось найти правильное ФИО ответчика. mortgageDebtorName: {mortgage_debtor_name}, debtorName: {debtor_name[:100] if debtor_name else 'None'}, applicantName: {current_applicant_name[:100] if current_applicant_name else 'None'}")

            # НАДЁЖНАЯ гарантия [2]/[2.1]/[2.2]/[2.3]: ветки выше заполняют падежи не
            # всегда ([2.1] — только «при спец-условии»; несколько должников —
            # склонение пропускается; пустой flat mortgageDebtorName). Пустой [2.2]
            # уносит контекст-чисткой «[989] к [2.2] о расторжении…» вместе с истцом.
            # Берём лучший источник имени и склоняем ПОИМЁННО (несколько — через запятую).
            best_name = (mortgage_debtor_name or debtor_name or "").strip()
            if not best_name:
                cand = (cleaned_data.get("applicantName") or "").strip()
                if cand and "суд" not in cand.lower():
                    best_name = cand
            if best_name and "суд" not in best_name.lower():
                def _decline_multi(nm: str, case: str) -> str:
                    return ", ".join(
                        self._decline_person_name(part.strip(), case)
                        for part in nm.split(",") if part.strip()
                    )
                if not cleaned_data.get("mortgageDebtorName"):
                    cleaned_data["mortgageDebtorName"] = best_name
                    field_mapping["mortgageDebtorName"] = "2"
                if field_mapping.get("applicantNameGenitive") != "2.1":
                    cleaned_data["applicantNameGenitive"] = _decline_multi(best_name, "gent")
                    field_mapping["applicantNameGenitive"] = "2.1"
                if not cleaned_data.get("mortgageDebtorNameDative"):
                    cleaned_data["mortgageDebtorNameDative"] = _decline_multi(best_name, "datv")
                    field_mapping["mortgageDebtorNameDative"] = "2.2"
                inst = (cleaned_data.get("applicantNameInstrumental") or "")
                if not inst or "суд" in inst.lower():
                    cleaned_data["applicantNameInstrumental"] = _decline_multi(best_name, "ablt")
        return field_mapping

    def _court_name_to_case(self, name: str, grammeme: str, agree_gender: str = None) -> str:
        """Название суда → заданный падеж (grammeme pymorphy: 'gent'/'datv'/'loct'/…).
        Одно поле формы (именительный) → любой падеж для акта. Склоняем пословно
        прилагательные и слово «суд» (до него включительно); хвост (город,
        «г. Ростова-на-Дону») оставляем как есть — иначе морфология искажает топоним.
        Fallback — исходное слово, если pymorphy не разобрал. Регистр первого
        символа каждого слова сохраняем.

        agree_gender ('masc'/'femn'/'neut') — навязать род прилагательным, чтобы они
        согласовались с «суд» (муж.). pymorphy в отрыве иногда берёт женский разбор
        «областной» → не склоняет; с agree_gender='masc' даёт «областного». По
        умолчанию None — прежнее поведение (golden не затрагивается)."""
        if not name or not name.strip():
            return name
        try:
            from pymorphy3 import MorphAnalyzer
            morph = MorphAnalyzer()
        except Exception as e:
            logger.warning(f"pymorphy недоступен для склонения суда: {e}")
            return name
        words = name.split()
        result: list = []
        inflect_done = False
        for word in words:
            if inflect_done:
                result.append(word)
                continue
            parsed = morph.parse(word)[0]
            grammemes = {grammeme}
            # Прилагательные согласуем по роду с «суд», иначе pymorphy может оставить
            # «областной» в женском разборе несклонённым.
            if agree_gender and "ADJF" in parsed.tag:
                grammemes = {grammeme, agree_gender, "sing"}
            form = parsed.inflect(grammemes)
            inflected = form.word if form else word
            if word[:1].isupper():
                inflected = inflected[:1].upper() + inflected[1:]
            result.append(inflected)
            # После слова с леммой «суд» склонение прекращаем (город — как есть).
            if parsed.normal_form == "суд":
                inflect_done = True
        return " ".join(result)

    def _court_name_to_genitive(self, name: str) -> str:
        """Родительный падеж названия суда («…районного суда…»)."""
        return self._court_name_to_case(name, "gent")

    # Город в названии суда стоит в родительном («…суд г. Ростова-на-Дону»), а в
    # шапке акта нужен именительный («г. Ростов-на-Дону»).
    # Без IGNORECASE: заглавная буква — единственный признак, отличающий название
    # города от продолжения слова («города Ростова-на-Дону» иначе даёт «ород»).
    _COURT_CITY_RE = re.compile(r"(?:\bг\.|\bгор\.|\bгород[аеу]?\b)\s*([А-ЯЁ][А-Яа-яЁё\-]*)")

    def _city_from_court_name(self, court_name: Optional[str]) -> str:
        """Город вынесения акта ([1307]) из названия суда.

        Отдельного поля на форме нет, а маркер есть во всех решениях и в длинном
        определении. Пустой маркер опаснее неточного: зачистка уносила вместе с
        ним соседнюю дату, поэтому выводим город из того, что уже заполнено.
        """
        match = self._COURT_CITY_RE.search(str(court_name or ""))
        if not match:
            return ""
        source = match.group(1)
        nominative = self._court_name_to_case(source, "nomn") or source
        # pymorphy возвращает всё строчными («ростов-на-дону»), а в шапке акта
        # нужен исходный регистр. Переносим его по частям через дефис: «на»
        # остаётся строчной, «Дону» — заглавной.
        src_parts = source.split("-")
        out_parts = nominative.split("-")
        if len(src_parts) == len(out_parts):
            out_parts = [
                part.capitalize() if src[:1].isupper() else part
                for part, src in zip(out_parts, src_parts)
            ]
            nominative = "-".join(out_parts)
        elif source[:1].isupper():
            nominative = nominative.capitalize()
        return f"г. {nominative}"

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
            # [002] (наименование суда) снят: по ипотека_маркера.md разд. 1 суд — это [0].
            # Родительный падеж [002.1] остаётся, он живёт в определениях о принятии.
            "applicantName": "2",        # [2] - ФИО должника
            "applicantNameGenitive": "2.1",  # [2.1] - ФИО должника в родительном падеже
            "applicantNameInstrumental": "2.3",  # [2.3] - ФИО должника в творительном падеже
            "applicantNameAccusative": "2.4",  # [2.4] - ФИО должника в винительном падеже
            "mortgageRepresentative22": "1440",  # [1440] - Представитель истца ФИО (ипотека, спека)
            "respondentRepresentativeName": "1445",  # [1445] - Представитель ответчика ФИО (ипотека)
            "birthDate": "3",            # [3] - Дата рождения
            "birthPlace": "3.1",        # [3.1] - Город/место рождения
            "inn": "4",                  # [4] - ИНН
            "ogrnip": "4.1",             # [4.1] - ОГРНИП индивидуального предпринимателя
            "snils": "5",                # [5] - СНИЛС
            "applicantAddress": "6",     # [6] - Адрес регистрации
            "courtDecisionDate": "7",    # [7] - Дата решения суда
            "managerName": "8",          # [8] - ФИО финансового управляющего
            "managerInn": "41",           # [41] - ИНН финансового управляющего
            "managerAddress": "42",       # [42] - Почтовый адрес финансового управляющего
            "messageNumber": "9",        # [9] - Номер сообщения ЕФРСБ
            "efirsbPublicationDate": "11",  # [11] - Дата публикации на сайте ЕФРСБ
            "kommersantNumber": "67",    # [67] - Номер газеты «Коммерсантъ»
            "kommersantDate": "68",      # [68] - Дата газеты «Коммерсантъ»
            "cpCaseDate": "554",         # [554] - Дата из номера CP-Case
            "debtSnapshotDate88": "88",  # [88] - Дата состояния задолженности (для инициирования ЮЛ)
            "lastTaxReportDate": "82",         # [82] - Дата последней налоговой отчётности (отсутствующий)
            "lastAccountingReportDate": "83",  # [83] - Дата последней бухгалтерской отчётности (отсутствующий)
            "lastAccountOperationDate": "84",  # [84] - Дата последней операции по счетам (отсутствующий)
            "notaryName": "43",          # [43] - ФИО нотариуса (умерший)
            "notaryAddress": "43.1",     # [43.1] - Адрес нотариуса (умерший)
            "deathDate": "45",           # [45] - Дата смерти должника
            "deathCertificate": "46",    # [46] - Номер/реквизиты свидетельства о смерти
            "totalDebt": "12",           # [12] - Общая сумма долга
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
            # ФНС (уполномоченный орган): суммы по очередям реестра требований кредиторов.
            # Недоимка по очередям [34.1]/[34.2]/[34.3]; штрафы 3-й очереди [26];
            # пени 3-й очереди [27]; основной долг (ЮЛ/субсидиарка) [13].
            # Эти поля есть только в ФНС-заявлениях, поэтому обычным актам не мешают.
            "fnsQ1Arrears": "34.1",      # [34.1] - Недоимка 1-й очереди
            "fnsQ2Arrears": "34.2",      # [34.2] - Недоимка 2-й очереди
            "fnsQ3Arrears": "34.3",      # [34.3] - Недоимка 3-й очереди
            "fnsQ3Penalties": "26",      # [26]  - Штрафы (3-я очередь)
            "fnsQ3Forfeit": "27",        # [27]  - Пени (3-я очередь)
            "fnsQ3LoanDebt": "13",       # [13]  - Основной долг (ФНС ЮЛ/субсидиарка)
            "stateDuty16": "16",         # [16] - Банкротная госпошлина
            "stateDuty": "16",           # [16] - Банкротная госпошлина (общее поле)
            "loanStateDuty17": "17",     # [17] - Ссудная госпошлина
            "objectionsDeadline18": "18",  # [18] - Установка срока на предоставление возражений
            "considerationDeadline19": "19",  # [19] - На рассмотрение заявления в срок
            "withoutMovementDeadline20": "20",  # [20] - Срок для оставления без движения
            "authorName": "29",          # [29] - ФИО секретаря/помощника судьи
            "separateDisputeNumber22": "22",  # [22] - Номер обособленного спора
            "applicationReceiptDate23": "23",  # [23] - Дата поступления заявления в суд (согласно штампу)
            "courtSubmissionDate24": "24",     # [24] - Дата направления в суд
            "courtHearingDateTime99": "99",    # [99] - Дата и время судебного заседания
            "judge": "415",              # [415] - Судья
            "date": "DATE",              # [DATE] - Дата (пользовательская)
            "mortgagePeriodStart120": "120",   # [120] - Начало расчетного периода (ипотека)
            "mortgagePeriodEnd121": "121",     # [121] - Конец расчетного периода (ипотека)
            "bankCommission": "122",           # [122] - Комиссия Банка (сумма)
            # Ипотека, новая схема маркеров (ипотека_маркера.md). Значения приходят
            # с формы «Ипотека», в разборе заявления их нет.
            "noticeDate": "1310",              # [1310] - Дата извещения (дата исходящего в шапке)
            "claimResolutionText": "888",      # [888] - Исход по иску (из claimResolution)
            "claimPartialDenialText": "889",   # [889] - Отказ в остальной части (только «частично»)
            "mortgageCollateralDescription1221": "1221",  # [1221] - Описание предмета залога
            # Специальная дата для юр. инициирования конкурсного (ликвидируемый) — маркер [5555]
            "liquidationRecordDate5555": "5555",
            "liquidatorName": "5556",                    # [5556] - ФИО ликвидатора
            "liquidationApplicationNumber": "5557",      # [5557] - Номер сообщения о ликвидации
            "liquidationDate": "5558",                    # [5558] - Дата сообщения о ликвидации
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
            # Заинтересованные лица = наследники = третьи лица (лица равны, один пул):
            # [25.x] ФИО, [52.x] дата рождения, [54.x] адрес регистрации.
            # [53.x] (место рождения) не мапится — данных нет, маркер вычищается.
            **{
                f"interested{field}_{idx}": f"{marker}.{idx}"
                for idx in range(1, 6)
                for field, marker in (("Name25", "25"), ("BirthDate52", "52"), ("Address54", "54"))
            },
            # Ипотека: поименные слоты ответчиков [1400.x]-[1409.x] (спека §2).
            # Данные (mortgageResp*_{idx}) заполняются в generate() из массива debtors.
            **{
                f"mortgageResp{field}_{idx}": f"{marker}.{idx}"
                for idx in range(1, 6)
                for field, marker in (
                    ("Nom1400", "1400"), ("Gen1401", "1401"), ("Dat1402", "1402"),
                    ("Addr1403", "1403"), ("Inn1404", "1404"), ("Birth1405", "1405"),
                    ("BirthPlace1406", "1406"), ("PassSer1407", "1407"),
                    ("PassNum1408", "1408"), ("Ins1409", "1409"),
                )
            },
            # Ранее вынесенное решение другого суда (вставляется только в те акты,
            # где эти маркеры физически есть в шаблоне «не во все»).
            "priorCourtName": "90",               # [90] - Суд ранее вынесенного решения
            "priorCaseNumber": "91",              # [91] - Номер дела ранее вынесенного решения
            "priorAmount": "92",                  # [92] - Взысканная сумма по ранее вынесенному решению
            "priorDecisionDate": "93",            # [93] - Дата ранее вынесенного решения
            "priorStateDuty": "94",               # [94] - Госпошлина по ранее вынесенному (прошлому) делу
        }
        return field_mapping

    def _apply_claim_resolution(self, cleaned_data: Dict[str, Any]) -> None:
        """Готовит тексты [888] и [889] из выбора «Удовлетворение иска».

        Мутирует cleaned_data, подстановку делает общий маппинг. Вызывать ДО
        `_apply_field_mapping_replacements`, иначе поля не доедут до документа.

        Незаполненная радиогруппа — норма для не-ипотечных актов: там маркеров
        [888]/[889] в шаблоне нет, а если есть — их снимет зачистка пустых.
        """
        resolution = str(cleaned_data.get("claimResolution") or "").strip().lower()
        if not resolution:
            return

        text = CLAIM_RESOLUTION_TEXTS.get(resolution)
        if text is None:
            # Не молчим: фронт мог прислать новое значение радиогруппы, о котором
            # бэкенд не знает, — в акте это обернулось бы вычищенным маркером.
            logger.warning(f"⚠️ Неизвестный claimResolution: {resolution!r}, [888]/[889] не заполняем")
            return

        cleaned_data["claimResolutionText"] = text
        logger.info(f" Исход по иску [888]: {text}")

        if resolution != PARTIAL:
            return

        cleaned_data["claimPartialDenialText"] = build_partial_denial(cleaned_data.get("creditorName"))
        logger.info(" Частичное удовлетворение — заполнен абзац [889]")

    def _apply_field_mapping_replacements(self, doc: DocxDocument, cleaned_data: Dict[str, Any], field_mapping: Dict[str, str], is_mortgage_document: bool, is_ip: bool, is_physical_collateral: bool) -> None:
        """Подставляет значения полей в маркеры [N] согласно field_mapping.
        Для ипотеки — приоритетные поля и формат сумм 'руб.'; для прочих —
        спец-поля ИП/ФЛ-залога и нормализация дат. Мутирует doc. Вынесено из
        replace_document_data без изменения поведения (gen-golden).
        """
        # Для ипотеки сначала заменяем приоритетные поля, чтобы избежать конфликтов
        if is_mortgage_document:
            # Приоритетные поля для ипотеки (заменяются первыми)
            # Поля старой схемы ([10]/[11]/[12]-проценты) из списка убраны вместе
            # со схемой — приоритет им больше не нужен, конфликтовать не с чем.
            priority_fields = ["mortgageDebtorName", "mortgageDebtorNameDative", "applicantNameGenitive",
                             "mortgagePeriodEnd121", "mortgagePeriodStart120"]

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
                            logger.warning(f"Пропускаем замену [121] - значение '{value_str}' не похоже на дату (поле: {field_key})")
                            continue

                    formatted_value = str(field_value)
                    if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                        logger.info(f"Заменено {placeholder} на {formatted_value} (поле: {field_key})")

            # Затем заменяем остальные поля, но пропускаем те, которые уже были заменены приоритетными
            replaced_placeholders = set()
            for field_key in priority_fields:
                if field_key in field_mapping:
                    replaced_placeholders.add(field_mapping[field_key])

            for field_key, field_value in cleaned_data.items():
                if field_key not in field_mapping or not field_value:
                    continue

                if field_key in priority_fields:
                    continue

                field_number = field_mapping[field_key]
                placeholder = f"[{field_number}]"

                if field_number in replaced_placeholders:
                    logger.debug(f"⏭Пропускаем {placeholder} - уже заменен приоритетным полем")
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
                    logger.info(f"Заменено {placeholder} на {formatted_value} (поле: {field_key})")
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
                        if value_str.lower() in ["от", "none", "null", ""]:
                            logger.warning(f"Поле {entity_type_label} {field_key} имеет некорректное значение: {value_str}")
                            continue
                        placeholder = f"[{field_number}]"
                        formatted_value = value_str
                        if self._replace_placeholder_in_doc(doc, placeholder, formatted_value):
                            logger.info(f"Заменено {placeholder} на {formatted_value[:100]}... (поле {entity_type_label}: {field_key})")
                    else:
                        logger.warning(f"Поле {entity_type_label} {field_key} отсутствует или пустое в cleaned_data")

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
                    logger.info(f"Заменено {placeholder} на {formatted_value} (поле: {field_key})")

    def replace_document_data(self, doc: DocxDocument, data: Dict[str, Any]):
        """
        Заменяет данные в существующем документе, используя нумерацию [1], [2], [3] и т.д.

        Args:
            doc: Документ для замены
            data: Данные для замены
        """
        cleaned_data = self._prepare_replacement_data(doc, data)
        # is_ip нужен ниже по методу; пролог его не возвращает — пересчёт из cleaned_data
        is_ip = "ip_enforcement" in (cleaned_data.get("sourceDocumentType") or "").lower()

        # Приоритет публикации ЕФРСБ/«Коммерсантъ» — до замены маркеров, пока текст ещё содержит [9]/[11]/[67]/[68]
        self._apply_efrsb_kommersant_priority(doc, cleaned_data)

        # Неустойка: если в заявлении её не было — убираем маркер [15] вместе с контекстом
        # ("руб. - неустойка" и т.п.), пока текст ещё содержит [13]/[14]/[15] в исходном виде
        self._apply_penalty_removal(doc, cleaned_data)


        if cleaned_data.get("_fnsCreditor"):
            self._apply_fns_third_queue_total(doc, cleaned_data)

        field_mapping = self._base_field_mapping()

        is_mortgage_document = (cleaned_data.get("sourceDocumentType") or "").lower() == "mortgage_claim"
        is_ip_collateral = (cleaned_data.get("sourceDocumentType") or "").lower() == "ip_enforcement_statement_collateral"
        is_physical_collateral = (cleaned_data.get("sourceDocumentType") or "").lower() in ["physical_realization_collateral", "physical_restructuring_collateral", "observation_collateral", "competition_collateral"]

        field_mapping = self._apply_debtor_name_field_mapping(cleaned_data, field_mapping, is_mortgage_document)

        # Извещение: апеллянт [1401.2] должен перечислять ВСЕХ ответчиков (в шаблоне
        # только один слот [1401.2], без [1401.1]). Собираем все слоты
        # mortgageRespGen1401_{i} через запятую в слот _2 (решение Андрея 31.07.2026).
        # Только для извещения — в резолютивках [1401.1]/[1401.2] раздельны, там не трогаем.
        if is_mortgage_document and data.get("_current_doc_type") == "mortgage_notice":
            appellants = [
                (cleaned_data.get(f"mortgageRespGen1401_{i}") or "").strip()
                for i in range(1, 6)
            ]
            appellants = [a for a in appellants if a]
            if len(appellants) > 1:
                cleaned_data["mortgageRespGen1401_2"] = ", ".join(appellants)

        # Резолютивки с представителями: блок «ответчика – [1400.2], представителя
        # ответчика [1400.2] – [1445]». Оба маркера указывают на ОДНОГО ответчика —
        # того, у кого представитель, — но слот в шаблоне жёстко второй. При
        # единственном ответчике слот 2 пуст, и зачистка уносила весь блок.
        # Подставляем в него первого ответчика.
        if is_mortgage_document and not (cleaned_data.get("mortgageRespNom1400_2") or "").strip():
            sole_respondent = (cleaned_data.get("mortgageRespNom1400_1") or "").strip()
            if sole_respondent:
                cleaned_data["mortgageRespNom1400_2"] = sole_respondent
                logger.info("Один ответчик — слот [1400.2] заполнен из [1400.1]")

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
                if original_value.strip().upper() == "ИП":
                    continue
                # ФНС-кредитор — не имя, а орг. название с аббревиатурами (ИФНС/УФНС),
                # title-case их ломает (ИФНС Ифнс). Оставляем регистр как есть.
                if field_name == "creditorName" and cleaned_data.get("_fnsCreditor"):
                    continue
                normalized_value = self._normalize_name_case(original_value)
                if normalized_value != original_value:
                    cleaned_data[field_name] = normalized_value
                    logger.info(f" Нормализован регистр {field_name}: '{original_value}' -> '{normalized_value}'")

        # Заменяем данные в параграфах
        logger.info("Начинаем замену данных в документе...")

        # Нормализация номера дела: убираем лишний суффикс после года (А44-1233-4/2025-4 -> А44-1233-4/2025)
        case_number = cleaned_data.get("caseNumber", "")
        if case_number:
            trailing_suffix = re.match(r'^(.+/\d{4})-\d+$', case_number.strip())
            if trailing_suffix:
                normalized = trailing_suffix.group(1)
                cleaned_data["caseNumber"] = normalized
                logger.info(f"Убран лишний суффикс в номере дела: {case_number} -> {normalized}")
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
                    logger.info(f" Исправлено дублирование номера дела: {case_number} -> {cleaned_data['caseNumber']}")
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
                    if prefix.endswith(f"-{separate_dispute_number}"):
                        logger.info(f" Номер дела уже содержит обособленный спор: {case_number}")
                    else:
                        modified_case_number = f"{prefix}-{separate_dispute_number}/{year}"
                        cleaned_data["caseNumber"] = modified_case_number
                        logger.info(f" Номер дела модифицирован с учетом обособленного спора: {case_number} -> {modified_case_number}")
                else:
                    if '/' in case_number:
                        parts = case_number.rsplit('/', 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            modified_case_number = f"{parts[0]}-{separate_dispute_number}/{parts[1]}"
                            cleaned_data["caseNumber"] = modified_case_number
                            logger.info(f"Номер дела модифицирован (альтернативный формат): {case_number} -> {modified_case_number}")
                        else:
                            logger.warning(f"Не удалось модифицировать номер дела: {case_number} (нестандартный формат)")
                    else:
                        logger.warning(f"Не удалось модифицировать номер дела: {case_number} (нет слэша с годом)")

        
        self._apply_extra_interested_persons(doc, cleaned_data)
        self._cleanup_empty_person_components(doc, cleaned_data)

        # После нормализации creditorName — он уходит в текст абзаца [889] как есть.
        self._apply_claim_resolution(cleaned_data)

        self._apply_field_mapping_replacements(doc, cleaned_data, field_mapping, is_mortgage_document, is_ip, is_physical_collateral)

        # Обрабатываем обязательства (договоры) - номера 100-113
        self.replace_obligations_data(doc, cleaned_data)

        self.replace_contextual_fields(doc, cleaned_data)

        # «конкурсное производство сроком до __.__.____» — в шаблонах конкурсного
        # (ликвидируемый/отсутствующий) стоит литеральный прочерк без маркера; срок
        # берём из даты заседания [99] (только дата, без времени).
        self._apply_konkurs_srok(doc, cleaned_data)

        # Обрабатываем специальные маркеры [DATE], [415] и [66]
        date_value = cleaned_data.get("date")
        if date_value:
            if self._replace_placeholder_in_doc(doc, "[DATE]", date_value):
                logger.info(f"Заменено [DATE] на {date_value}")
            # [66] — дата определения о принятии заявления к производству в формате «___» __________ 20__ года
            date_66 = self._format_date_66(date_value)
            if date_66 and self._replace_placeholder_in_doc(doc, "[66]", date_66):
                logger.info(f"Заменено [66] на {date_66}")

        judge_value = cleaned_data.get("judge")
        if judge_value:
            if self._replace_placeholder_in_doc(doc, "[415]", judge_value):
                logger.info(f"Заменено [415] на {judge_value}")

        # Удаляем все пустые маркеры, для которых нет значений
        self._remove_empty_placeholders(doc, cleaned_data, field_mapping, doc_type=data.get("_current_doc_type"))

        # ФНС: если компонент очереди (штрафы/пени/недоимка) пуст — после удаления
        # маркера остаётся осиротевшее ", руб. – штрафы". Подчищаем такие хвосты.
        if cleaned_data.get("_fnsCreditor"):
            self._cleanup_empty_fns_components(doc)

        
        if is_ip:
            self._apply_ip_debtor_wording(doc)

       
        if not is_mortgage_document:
            self._apply_secretary_wording(doc, str(cleaned_data.get("authorRole") or "").strip().lower())

        
        self._postprocess_document_formatting(doc, cleaned_data)

    def _apply_efrsb_kommersant_priority(self, doc: DocxDocument, cleaned_data: Dict[str, Any]) -> None:
        """В части актов рядом упомянуты обе публикации — ЕФРСБ (обёрнута в
        квадратные скобки как опциональный блок) и «Коммерсантъ» (без скобок).
        Приоритет — «Коммерсантъ»: если для него есть данные, блок ЕФРСБ убирается
        целиком вместе со скобками; если данных «Коммерсантъ» нет, а ЕФРСБ есть —
        оставляем ЕФРСБ, но снимаем скобки-разметку и убираем упоминание «Коммерсантъ».
        Должно вызываться до замены маркеров [9]/[11]/[67]/[68] на значения.
        """
        has_kommersant = bool(str(cleaned_data.get("kommersantNumber") or "").strip()) and \
            bool(str(cleaned_data.get("kommersantDate") or "").strip())

        efrsb_block_pattern = r"\[\s*на сайте ЕФРСБ\s*№\s*\[9\]\s*от\s*\[11\]\s*\]\s*"
        kommersant_block_pattern = r"в газете\s*«Коммерсантъ»\s*№\s*\[67\]\s*от\s*\[68\]\s*"

        if has_kommersant:
            self._replace_regex_in_doc(doc, efrsb_block_pattern, "")
        else:
            def _strip_brackets(match) -> str:
                inner = match.group(0).strip()
                return inner[1:-1].strip() + " "
            self._replace_regex_in_doc(doc, efrsb_block_pattern, _strip_brackets)
            self._replace_regex_in_doc(doc, kommersant_block_pattern, "")

    def _apply_penalty_removal(self, doc: DocxDocument, cleaned_data: Dict[str, Any]) -> None:
        """Если в заявлении не было данных о неустойке — маркер [15] убирается вместе
        с контекстом ("[15] руб. - неустойка" / "неустойка - [15] руб." и т.п.) из
        перечислений долга, где рядом есть [13]/[14] (основной долг/проценты).

        Отдельные самостоятельные предложения про неустойку (например, "требование о
        взыскании неустойки ... подлежит удовлетворению" или "... учесть отдельно в
        реестре ...", где рядом с [15] нет [13]/[14]) НЕ трогаем — пользователь решил
        оставлять их как есть (2026-07-17, п.5). Должно вызываться до замены маркеров
        [13]/[14]/[15] на значения.
        """
        has_penalty = bool(str(
            cleaned_data.get("forfeit15") or cleaned_data.get("forfeit") or cleaned_data.get("penalties") or ""
        ).strip())
        if has_penalty:
            return

        marker_pattern = re.compile(r"\[15\]")
        context_markers = ("[13]", "[14]")

        clause_pattern = re.compile(
            r"(?:,\s*)?"
            r"(?:"
            # «руб.» опциональна: часть шаблонов пишет «[15] руб. неустойки», а
            # часть — «[15] неустойки» (напр. «Решение Умерший старый»), и без
            # этого послабления слово «неустойки» оставалось в резолютивке
            # висеть без суммы: «…2 438 262,70 руб. процентов, неустойки в
            # третью очередь реестра».
            r"\[15\]\s*(?:руб\.?)?\s*[-–—]?\s*неустойк\w*(?:\s*,\s*как\s+обеспеченн\w+[^.]*)?"
            r"|"
            r"неустойк\w*\s*(?:в\s+размере|в\s+сумме)?\s*[-–—]?\s*\[15\]\s*(?:руб\.?)?"
            r")\.?",
            re.IGNORECASE,
        )

        def process_paragraphs(paragraphs):
            for paragraph in paragraphs:
                text = paragraph.text
                if not marker_pattern.search(text):
                    continue
                if not any(marker in text for marker in context_markers):
                    # Отдельное предложение про неустойку без [13]/[14] рядом — не трогаем.
                    continue
                new_text = clause_pattern.sub("", text)
                if new_text == text:
                    continue
                
                new_text = re.sub(r",\s*,", ",", new_text)
                new_text = re.sub(r"\s{2,}", " ", new_text).strip()
                new_text = re.sub(r",\s*\.\s*$", ".", new_text)
                new_text = re.sub(r",+\s*$", "", new_text).rstrip()
                if new_text and new_text[-1] not in ".;:":
                    new_text += "."
                paragraph.text = new_text

        process_paragraphs(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    process_paragraphs(cell.paragraphs)

    @staticmethod
    def _format_interested_person(person: Dict[str, str]) -> str:
        """«Иванов И.И. (01.01.1980 года рождения, адрес регистрации: …)» — по образцу
        разметки слота в шаблоне. Пустые компоненты опускаются; если нет ни одного —
        только ФИО. Место рождения не выводим: данных нет (см. _collect_interested_persons)."""
        details = []
        if person['birthDate']:
            details.append(f"{person['birthDate']} года рождения")
        if person['address']:
            details.append(f"адрес регистрации: {person['address']}")
        return f"{person['name']} ({', '.join(details)})" if details else person['name']

    def _apply_extra_interested_persons(self, doc: DocxDocument, cleaned_data: Dict[str, Any]) -> None:
        """Заинтересованных лиц больше, чем слотов [25.x] в шаблоне — дописываем
        оставшихся построчно, без новых маркеров (тот же приём, что для обязательств
        сверх слотов в replace_obligations_data).

        Вставляем текст сразу после блока последнего слота, пока его маркеры ещё не
        заменены на значения. Если слот размечен с деталями в скобках
        («[25.1] ([52.1] года рождения, … [54.1])») — дописываем после закрывающей
        скобки и в том же формате; если слот стоит голым («наследник [25.1] принял») —
        дописываем только ФИО сразу после маркера.
        """
        persons = self._collect_interested_persons(cleaned_data)
        if not persons:
            return

        # Реально размеченные слоты: [25.1]-[25.5]. Слоты идут подряд от 1.
        slots = sorted(
            int(m.group(1))
            for placeholder in self._collect_placeholders(doc)
            for m in [re.fullmatch(r"\[25\.(\d+)\]", placeholder)]
            if m
        )
        if not slots:
            return

        max_slot = max(slots)
        if len(persons) <= max_slot:
            return

        extra_suffix = ", " + ", ".join(
            self._format_interested_person(p) for p in persons[max_slot:]
        )
        names_only_suffix = ", " + ", ".join(p['name'] for p in persons[max_slot:])

        last_marker = f"[25.{max_slot}]"
        # Блок последнего слота с деталями в скобках: «[25.N] (… [54.N])»
        block_re = re.compile(
            re.escape(last_marker) + r"\s*\([^)]*\[54\." + str(max_slot) + r"\][^)]*\)"
        )

        def process(paragraphs):
            for paragraph in paragraphs:
                text = paragraph.text
                if last_marker not in text:
                    continue
                if block_re.search(text):
                    paragraph.text = block_re.sub(
                        lambda m: m.group(0) + extra_suffix, text, count=1
                    )
                else:
                    paragraph.text = text.replace(
                        last_marker, last_marker + names_only_suffix, 1
                    )

        process(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    process(cell.paragraphs)

        logger.info(
            f"Дописано заинтересованных лиц сверх слотов ({max_slot}): {len(persons) - max_slot}"
        )

    def _cleanup_empty_person_components(self, doc: DocxDocument, cleaned_data: Dict[str, Any]) -> None:
        """Вырезает компоненты заинтересованного лица, для которых нет данных, вместе
        с их подписью — иначе в тексте останется «( года рождения, уроженка , адрес…)».

        Место рождения ([53.x]) вычищается ВСЕГДА: поля нет ни у наследника, ни у
        третьего лица (решение Андрея — UI не трогаем). Дата рождения ([52.x]) — только
        когда пусто: у наследника её нет, у третьего лица есть.
        Работает по литеральным маркерам, до общей замены полей.
        """
        persons = self._collect_interested_persons(cleaned_data)

        for idx in range(1, self.MAX_INTERESTED_SLOTS + 1):
            person = persons[idx - 1] if idx <= len(persons) else None

            # Место рождения: данных нет никогда. «уроженка [53.1], » / «место рождения: [53.1], »
            self._replace_regex_in_doc(
                doc, r"(?:уроженк\w*|мест\w*\s+рождения)\s*:?\s*\[53\." + str(idx) + r"\]\s*,?\s*", ""
            )
            self._replace_regex_in_doc(doc, r"\[53\." + str(idx) + r"\]\s*,?\s*", "")

            if not person or not person['birthDate']:
                self._replace_regex_in_doc(
                    doc, r"\[52\." + str(idx) + r"\]\s*года\s+рождения\s*,?\s*", ""
                )
                self._replace_regex_in_doc(doc, r"\[52\." + str(idx) + r"\]\s*,?\s*", "")

            if not person or not person['address']:
                self._replace_regex_in_doc(
                    doc, r"адрес\w*\s+регистрации\s*:?\s*\[54\." + str(idx) + r"\]\s*,?\s*", ""
                )

        # Скобка, оставшаяся пустой после выноса всех компонентов: «Иванов И.И. ()»
        self._replace_regex_in_doc(doc, r"\s*\(\s*[,;:\s]*\)", "")
        # Подчистка пунктуации на стыке вырезанного
        self._replace_regex_in_doc(doc, r"\(\s*,\s*", "(")
        self._replace_regex_in_doc(doc, r",\s*\)", ")")
        self._replace_regex_in_doc(doc, r"\s+([,.)])", r"\1")
        self._replace_regex_in_doc(doc, r"\s{2,}", " ")

    def _cleanup_empty_fns_components(self, doc: DocxDocument) -> None:
        """Убирает осиротевшие «, руб. – <компонент>» без суммы, оставшиеся когда
        компонент очереди ФНС (штрафы/пени/недоимка/осн.долг) пуст и его маркер
        ([26]/[27]/[34.x]/[13]) был удалён. Числа при этом не задеваются: паттерн
        требует запятую вплотную к «руб.» (у заполненных значений перед «руб.» — цифры)."""
        # «…, руб. – штрафы» / «…, руб. – пени» / «…, руб. – недоимка» / «…, руб. – основной долг»
        self._replace_regex_in_doc(
            doc,
            r",\s*руб\.\s*[–—-]\s*(?:недоимк\w*|пени|штраф\w*|основн\w+\s+долг\w*)",
            "",
        )
        # Подчистка пунктуации на стыке.
        self._replace_regex_in_doc(doc, r",\s*\.", ".")
        self._replace_regex_in_doc(doc, r"\s{2,}", " ")

    def _apply_fns_third_queue_total(self, doc: DocxDocument, cleaned_data: Dict[str, Any]) -> None:
        """У ФНС маркер [12] неоднозначен между шаблонами: в резолютивке ВКЛ он
        означает ПОДЫТОГ 3-й очереди («включить в третью очередь … в размере [12],
        из которых: [34.3] недоимка, [27] пени»), а в реструктуризации — ОБЩУЮ
        сумму долга. Здесь заполняем [12] подытогом 3-й очереди (fnsQ3Total) только
        в абзацах про третью очередь с оборотом «из которых». Остальные [12]
        (общая сумма) заполнит обычный маппинг totalDebt [12] позже. fnsQ3Total уже
        отформатирован как сумма в _prepare_replacement_data."""
        q3 = str(cleaned_data.get("fnsQ3Total") or "").strip()
        if not q3:
            return

        def process(paragraphs):
            for p in paragraphs:
                t = p.text
                if "[12]" in t and "треть" in t.lower() and "из котор" in t.lower():
                    p.text = t.replace("[12]", q3)

        process(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    process(cell.paragraphs)

    def _apply_konkurs_srok(self, doc: DocxDocument, cleaned_data: Dict[str, Any]) -> None:
        """Заполняет срок конкурсного производства («сроком до __.__.____»).

        В шаблонах «О введении конкурсное (ликвидируемый/отсутствующий)» на месте
        срока стоит литеральный прочерк без маркера. Дату берём из [99]
        (courtHearingDateTime99) — только дату, без времени (для срока время не нужно).
        Если даты нет — прочерк оставляем как есть (не портим шаблон).
        """
        raw = str(cleaned_data.get("courtHearingDateTime99") or "").strip()
        if not raw:
            return
        date_part = raw.split("T")[0] if "T" in raw else raw
        date_only = self._normalize_date_format(date_part)
        if not date_only or not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_only):
            return

        def _fill(match):
            return match.group(1) + date_only

        # «…конкурсное производство сроком до __.__.____» «…сроком до 31.07.2026»
        self._replace_regex_in_doc(
            doc,
            r"(конкурсн\w*\s+производств\w*\s+сроком\s+до\s+)_[_.]*_",
            _fill,
        )

    def _apply_ip_debtor_wording(self, doc: DocxDocument) -> None:
        """Заменяет "должник/должника/должнику" на "индивидуальный предприниматель"
        в соответствующем падеже (им./род./дат.), сохраняя регистр первой буквы."""
        replacements = [
            (r"\bдолжнику\b", "индивидуальному предпринимателю"),
            (r"\bдолжника\b", "индивидуального предпринимателя"),
            (r"\bдолжник\b", "индивидуальный предприниматель"),
        ]
        for pattern, phrase in replacements:
            def _sub(match, phrase=phrase):
                word = match.group(0)
                return phrase[:1].upper() + phrase[1:] if word[:1].isupper() else phrase
            self._replace_regex_in_doc(doc, pattern, _sub)

    def _apply_secretary_wording(self, doc: DocxDocument, author_role: str) -> None:
        """Шаблоны по умолчанию по-разному называют роль ведущего протокол — где-то
        "помощником судьи [29]", где-то "секретарем"/"секретарём судьи [29]" (е/ё —
        встречаются оба написания). Приводим словоформу к роли, выбранной пользователем
        в интерфейсе; если роль не выбрана — оставляем текст шаблона как есть."""
        if author_role not in ("секретарь", "помощник"):
            return

        def _make_sub(phrase: str):
            def _sub(match) -> str:
                word = match.group(0)
                return phrase[:1].upper() + phrase[1:] if word[:1].isupper() else phrase
            return _sub

        if author_role == "секретарь":
            self._replace_regex_in_doc(doc, r"\bпомощником\b", _make_sub("секретарём"))
        else:
            self._replace_regex_in_doc(doc, r"\bсекретар[её]м\b", _make_sub("помощником"))

    def _remove_empty_placeholders(self, doc: DocxDocument, cleaned_data: Dict[str, Any], field_mapping: Dict[str, str], doc_type: Optional[str] = None):
        """
        Удаляет из документа все маркеры, для которых нет значений в данных.
        Также удаляет контекст вокруг маркеров (например, "Дело№ [1]" удаляется полностью).

        Args:
            doc: Документ для обработки
            cleaned_data: Данные с заполненными полями
            field_mapping: Маппинг полей на номера маркеров
        """
        logger.info(" Удаляем пустые маркеры из документа")

        all_placeholders = self._collect_placeholders(doc)

        # Ипотека: незаполненный маркер уносит всю фразу, а опустевший абзац
        # удаляется целиком (требование от 30.07.2026). Банкротные акты идут
        # прежним путём — их вывод зафиксирован golden-эталонами.
        is_mortgage = (cleaned_data.get("sourceDocumentType") or "").lower() == "mortgage_claim"
        # Извещение — сплошной обязательный boilerplate; вырезать предложение/абзац
        # вокруг пустого маркера (напр. [1302], у которого нет источника данных)
        # нельзя: пропадает шапка суда и половина текста. Для него — мягкое
        # удаление только самого маркера, вёрстка и текст сохраняются как в шаблоне.
        if is_mortgage and doc_type == "mortgage_notice":
            drop_placeholder = self._remove_placeholder_token
        elif is_mortgage:
            drop_placeholder = self._remove_placeholder_phrase
        else:
            drop_placeholder = self._remove_placeholder_with_context

        # Создаем обратный маппинг: номер маркера -> список полей
        marker_to_fields = {}
        for field_name, marker_number in field_mapping.items():
            marker = f"[{marker_number}]"
            if marker not in marker_to_fields:
                marker_to_fields[marker] = []
            marker_to_fields[marker].append(field_name)

        
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

            if placeholder in special_markers:
                marker_value = special_markers[placeholder]
                if not marker_value:
                    # Удаляем пустой специальный маркер с контекстом
                    drop_placeholder(doc, placeholder)
                    removed_count += 1
                    logger.info(f" Удален пустой специальный маркер с контекстом: {placeholder}")
                # Если значение есть, маркер уже был заменен в предыдущих шагах, пропускаем
                continue

            if placeholder in marker_to_fields:
                has_value = False
                for field_name in marker_to_fields[placeholder]:
                    value = cleaned_data.get(field_name)
                    if value and str(value).strip() and str(value).strip().lower() not in ['не указано', 'не указана', 'none', 'null', '']:
                        has_value = True
                        break

                if not has_value:
                    # Удаляем пустой маркер с контекстом
                    drop_placeholder(doc, placeholder)
                    removed_count += 1
                    logger.info(f" Удален пустой маркер с контекстом: {placeholder} (поля: {', '.join(marker_to_fields[placeholder])})")
            else:
                # Маркер не найден в маппинге - возможно, это неизвестный маркер
                marker_num = placeholder.strip('[]')
                has_value_in_data = False
                for field_name, field_value in cleaned_data.items():
                    if field_value and str(field_value).strip() and str(field_value).strip().lower() not in ['не указано', 'не указана', 'none', 'null', '']:
                        if field_mapping.get(field_name) == marker_num:
                            has_value_in_data = True
                            break

                if not has_value_in_data:
                    # Удаляем его с контекстом, чтобы не было видно в финальном документе
                    drop_placeholder(doc, placeholder)
                    removed_count += 1
                    logger.info(f" Удален неизвестный маркер с контекстом: {placeholder}")

        # После общей очистки отдельно обрабатываем госпошлины:
        # - если для [16] нет суммы — удаляем только её строку
        # - если для [17] нет суммы — удаляем только её строку
        if not has_state_duty_16:
            drop_placeholder(doc, "[16]")
        if not has_state_duty_17:
            drop_placeholder(doc, "[17]")

        if removed_count > 0:
            logger.info(f"Удалено {removed_count} пустых маркеров из документа")
        else:
            logger.info("ℹПустых маркеров не найдено")

    def replace_contextual_fields(self, doc: DocxDocument, data: Dict[str, Any]):
        """
        Заменяет поля без нумерации по контексту

        Args:
            doc: Документ
            data: Данные для замены
        """
        logger.info("Заменяем поля без нумерации по контексту")

        manager_fields = {
            'managerBirthDate': 'финансовый управляющий',
            'managerAddress': 'финансовый управляющий',
            'managerInn': 'финансовый управляющий',
        }

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

        for paragraph in doc.paragraphs:
            text = paragraph.text

            
            if case_number and separate_dispute_number:
                pattern_case_sep = rf"({re.escape(case_number)})\s+{re.escape(separate_dispute_number)}\b"
                if re.search(pattern_case_sep, text):
                    new_text = re.sub(pattern_case_sep, r"\1", text)
                    if new_text != text:
                        paragraph.text = new_text
                        text = new_text
                        logger.info(
                            " Удалено дублирование номера обособленного спора рядом с номером дела"
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

            for field_key, context in manager_fields.items():
                field_value = data.get(field_key, '')
                if field_value and context in text.lower():
                    if field_key == 'managerBirthDate':
                        pattern = r'(\d{1,2}[.,]\d{1,2}[.,]\d{4})[^,]*?финансовый\s+управляющий'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'{field_value} финансовый управляющий', text)
                            logger.info(f"Заменена дата рождения финансового управляющего: {field_value}")
                    elif field_key == 'managerAddress':
                        pattern = r'финансовый\s+управляющий[^,]*?адрес[:\s]+([^,\n]+)'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'финансовый управляющий адрес: {field_value}', text)
                            logger.info(f"Заменен адрес финансового управляющего: {field_value}")
                    elif field_key == 'managerInn':
                        pattern = r'финансовый\s+управляющий[^,]*?ИНН[:\s]*([0-9]{10,12})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'финансовый управляющий ИНН: {field_value}', text)
                            logger.info(f"Заменен ИНН финансового управляющего: {field_value}")

            for field_key, context in third_party_fields.items():
                field_value = data.get(field_key, '')
                if field_value and context in text.lower():
                    if field_key == 'thirdPartyName':
                        pattern = r'поручитель[:\s]+([А-ЯЁ][а-яё\s]+)'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель: {field_value}', text)
                            logger.info(f"Заменено ФИО поручителя: {field_value}")
                    elif field_key == 'thirdPartyBirthDate':
                        pattern = r'поручитель[^,]*?(\d{1,2}[.,]\d{1,2}[.,]\d{4})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель {field_value}', text)
                            logger.info(f"Заменена дата рождения поручителя: {field_value}")
                    elif field_key == 'thirdPartyAddress':
                        pattern = r'поручитель[^,]*?адрес[:\s]+([^,\n]+)'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель адрес: {field_value}', text)
                            logger.info(f"Заменен адрес поручителя: {field_value}")
                    elif field_key == 'thirdPartyInn':
                        pattern = r'поручитель[^,]*?ИНН[:\s]*([0-9]{10,12})'
                        if re.search(pattern, text):
                            paragraph.text = re.sub(pattern, f'поручитель ИНН: {field_value}', text)
                            logger.info(f"Заменен ИНН поручителя: {field_value}")
                    elif field_key == 'thirdPartySnils':
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
            templates = self._get_templates_for_procedure("deceased")
            procedure_type = "deceased"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: умерший")
        elif normalized_template == "physical_restructuring_collateral" or source_document_type_for_routing == "physical_restructuring_collateral":
            templates = self._get_physical_restructuring_collateral_templates()
            procedure_type = "physical_restructuring_collateral"
            logger.info(
                f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ФЛ с залогом в реструктуризации"
            )
        elif normalized_template == "physical_realization_collateral" or source_document_type_for_routing == "physical_realization_collateral":
            templates = self._get_physical_collateral_templates()
            procedure_type = "physical_realization_collateral"
            logger.info(
                f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ФЛ с залогом в реализации"
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
                f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для КФХ "
                f"({'наблюдение с залогом' if has_collateral else 'наблюдение, без залога'})"
            )
        elif normalized_template == "ip_collection_collateral" or source_document_type_for_routing == "ip_collection_collateral":
            templates = self._get_ip_collection_collateral_templates()
            procedure_type = "ip_collection_collateral"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ИП с залогом")
        elif normalized_template == "ip_collection_collateral_auto" or source_document_type_for_routing == "ip_collection_collateral_auto":
            # [1221] — описание авто
            templates = self._get_ip_collection_collateral_auto_templates()
            procedure_type = "ip_collection_collateral_auto"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ИП залог авто")
        elif normalized_template == "legal_collection" or source_document_type_for_routing == "legal_collection":
            templates = self._get_legal_collection_templates()
            procedure_type = "legal_collection"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ЮЛ")
        elif normalized_template == "legal_collection_collateral" or source_document_type_for_routing == "legal_collection_collateral":
            templates = self._get_legal_collection_collateral_templates()
            procedure_type = "legal_collection_collateral"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ЮЛ с залогом")
        elif normalized_template == "legal_collection_collateral_auto" or source_document_type_for_routing == "legal_collection_collateral_auto":
            # [1221] — описание авто
            templates = self._get_legal_collection_collateral_auto_templates()
            procedure_type = "legal_collection_collateral_auto"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ЮЛ залог авто")
        elif normalized_template == "ip_collection" or source_document_type_for_routing == "ip_collection":
            templates = self._get_ip_collection_templates()
            procedure_type = "ip_collection"
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для искового заявления о взыскании с ИП")
        elif normalized_template in ["ip_enforcement", "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                     "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"] or \
             source_document_type_for_routing in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                     "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                     "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"]:
            if (
                normalized_template.endswith("_collateral")
                or source_document_type_for_routing in ["ip_enforcement_statement_collateral", "ip_enforcement_realization_collateral",
                                                        "ip_enforcement_restructuring_collateral"]
            ):
                has_collateral_flag = True
            else:
                has_collateral_flag = str(data.get("ipHasCollateral", "")).strip().lower() in {"true", "1", "yes", "да"}

            if "restructuring" in source_document_type_for_routing or normalized_template == "ip_enforcement_restructuring":
                ip_procedure_type = "restructuring"
            else:
                ip_procedure_type = "realization"

            templates = self._get_ip_enforcement_templates(has_collateral_flag, ip_procedure_type)
            procedure_type = source_document_type_for_routing or normalized_template or "ip_enforcement"
            logger.info(
                f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для заявления ИП "
                f"({ip_procedure_type}, залог: {'есть' if has_collateral_flag else 'нет'})"
            )
        elif normalized_template == "initiation_physical" or source_document_type_for_routing == "initiation_physical":
            templates = self._get_initiation_physical_templates()
            procedure_type = "initiation_physical"
            data["_skip_obligation_blocks"] = True
            logger.info(" НАЧИНАЕМ ГЕНЕРАЦИЮ 3 ДОКУМЕНТОВ для инициирования банкротства физического лица")
        elif normalized_template == "initiation_legal" or source_document_type_for_routing == "initiation_legal":
            templates = self._get_initiation_legal_templates()
            procedure_type = "initiation_legal"
            logger.info(" НАЧИНАЕМ ГЕНЕРАЦИЮ 2 ДОКУМЕНТОВ для инициирования банкротства юридического лица")
        elif normalized_template == "initiation_legal_competition_absent":
            templates = self._get_initiation_legal_templates(contest_type="absent")
            procedure_type = "initiation_legal_competition_absent"
            logger.info(" НАЧИНАЕМ ГЕНЕРАЦИЮ 2 ДОКУМЕНТОВ для инициирования ЮЛ (конкурсное, отсутствующий должник)")
        elif normalized_template == "initiation_legal_competition_liquidation":
            templates = self._get_initiation_legal_templates(contest_type="liquidation")
            procedure_type = "initiation_legal_competition_liquidation"
            logger.info(" НАЧИНАЕМ ГЕНЕРАЦИЮ 2 ДОКУМЕНТОВ для инициирования ЮЛ (конкурсное, ликвидируемый должник)")
        elif normalized_template == "mortgage" or source_document_type_for_routing == "mortgage_claim":
            templates = self._get_mortgage_templates(data)
            procedure_type = "mortgage"
            data["_skip_obligation_blocks"] = True
            logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для ипотечного иска")
        elif normalized_template == "observation_collateral" or source_document_type_for_routing == "observation_collateral":
            if is_kfh:
                templates = self._get_kfh_observation_templates(has_collateral=True)
                procedure_type = "kfh_observation_collateral"
                logger.info(
                    f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для КФХ (наблюдение с залогом)"
                )
            else:
                templates = self._get_templates_for_procedure("observation_collateral")
                procedure_type = "observation_collateral"
                logger.info(
                    f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для наблюдения с залогом"
                )
        elif normalized_template == "competition_collateral" or source_document_type_for_routing == "competition_collateral":
            templates = self._get_templates_for_procedure("competition_collateral")
            procedure_type = "competition_collateral"
            logger.info(
                f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для конкурсного производства с залогом"
            )
        else:
            procedure_type = (data.get('procedureType') or '').lower()
            entity_type = str(data.get("entityType") or "").lower()
            raw = (data.get('procedureTypeRaw') or '').lower()

            # ПРИОРИТЕТ: Проверяем на процедуру "умерший" в первую очередь
            if procedure_type == "deceased" or any(keyword in raw for keyword in ["умер", "умерший", "смерть", "смерти"]):
                procedure_type = 'deceased'
                templates = self._get_templates_for_procedure("deceased")
                logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: умерший")
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
                        f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для КФХ (наблюдение, без залога)"
                    )
                    procedure_type = "kfh_observation"
                else:
                    templates = self._get_templates_for_procedure(procedure_type)
                    logger.info(f" НАЧИНАЕМ ГЕНЕРАЦИЮ {len(templates)} ДОКУМЕНТОВ для процедуры: {procedure_type}")
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
            elif len(valid_debtors) == 1:
                # Ипотека, один ответчик: плоский `inn` (маркер [4]) на грязном входе
                # мог перехватить ИНН третьего лица (Росреестр в ДДУ). Берём ИНН из
                # разобранной записи должника — он привязан к самому ответчику.
                own_inn = (valid_debtors[0].get("inn") or "").strip()
                if own_inn and own_inn != (data.get("inn") or fields.get("inn") or "").strip():
                    data["inn"] = own_inn
                    fields["inn"] = own_inn
                    data["fields"] = fields
                    logger.info(f"Ипотека: ИНН [4] взят из записи должника: {own_inn}")
                # Дата рождения [3] из записи должника — иначе пустой [3] в военной
                # строке взыскания уносит контекстом соседний [1377] (нет запятых).
                own_bd = (valid_debtors[0].get("birthDate") or "").strip()
                if own_bd and not (data.get("birthDate") or fields.get("birthDate")):
                    data["birthDate"] = own_bd
                    fields["birthDate"] = own_bd
                    data["fields"] = fields

            # Ипотека: разворачиваем ПЕРВЫЙ предмет залога в плоские поля под маркеры
            # предмета ([1226]-[1234]). Массив mortgageProperties строит анализатор;
            # value/startingPrice/appraisal уже покрыты базой ([1224]/[1225]/[1223]).
            mprops = data.get("mortgageProperties") or fields.get("mortgageProperties") or []
            if isinstance(mprops, list) and mprops and isinstance(mprops[0], dict):
                p0 = mprops[0]
                # Площадь [1233]: сперва готовое поле объекта (его заполняет
                # анализатор и правит юрист на форме), и только если пусто —
                # выковыриваем из описания. Раньше поле игнорировалось, и при
                # заполненном area маркер оставался пустым, унося за собой
                # «общей площадью …» из резолютивки.
                area = str(p0.get("area") or "").strip()
                if not area:
                    _am = re.search(r"площад[ьи][^\d]{0,12}([\d]+[.,]?\d*\s*(?:кв\.?\s*м|м2|м²|\+/-\s*\d+\s*кв))",
                                    str(p0.get("description") or ""), re.IGNORECASE)
                    if _am:
                        area = _am.group(1).strip()
                prop_flat = {
                    "mortgageCadastralNumber1226": p0.get("cadastralNumber"),
                    "mortgagePropertyAddress1227": p0.get("address"),
                    "mortgageNpcStrategy1228": p0.get("npcStrategy"),
                    "mortgageEgrnRecord1229": p0.get("egrnRecord"),
                    "mortgageEgrnRecordDate1230": p0.get("egrnRecordDate"),
                    "mortgageDduContract1231": p0.get("dduContract"),
                    "mortgageDduDate1232": p0.get("dduDate"),
                    "mortgagePropertyArea1233": area,
                    "mortgageSaleMethod1234": "путем продажи с публичных торгов",
                }
                for k, v in prop_flat.items():
                    if v and not (data.get(k) or fields.get(k)):
                        data[k] = v
                        fields[k] = v
                data["fields"] = fields

            # Ипотека: поименные СЛОТЫ ответчиков [1400.x]-[1409.x] для шапок
            # (извещение/повестка) — до 5 ответчиков. Падежи склоняем гендер-aware.
            for i, deb in enumerate(valid_debtors[:5], start=1):
                nm = (deb.get("name") or "").strip()
                if not nm:
                    continue
                slot = {
                    f"mortgageRespNom1400_{i}": self._capitalize_full_name(nm),
                    f"mortgageRespGen1401_{i}": self._decline_person_name(nm, "gent"),
                    f"mortgageRespDat1402_{i}": self._decline_person_name(nm, "datv"),
                    f"mortgageRespIns1409_{i}": self._decline_person_name(nm, "ablt"),
                    f"mortgageRespAddr1403_{i}": deb.get("address"),
                    f"mortgageRespInn1404_{i}": deb.get("inn"),
                    f"mortgageRespBirth1405_{i}": deb.get("birthDate"),
                    f"mortgageRespBirthPlace1406_{i}": deb.get("birthPlace") or deb.get("birthplace"),
                    f"mortgageRespPassSer1407_{i}": deb.get("passportSeries"),
                    f"mortgageRespPassNum1408_{i}": deb.get("passportNumber"),
                }
                for k, v in slot.items():
                    if v:
                        data[k] = v
                        fields[k] = v
            data["fields"] = fields

            # [1381] взыскатель ЦЖЗ — ФГКУ «Росвоенипотека» из третьих лиц.
            if not (data.get("cjzClaimant1381") or fields.get("cjzClaimant1381")):
                for tp in (data.get("thirdParties") or fields.get("thirdParties") or []):
                    nm = (tp.get("name") or "") if isinstance(tp, dict) else ""
                    if re.search(r"накопительно-ипотечн|росвоенипотек", nm, re.IGNORECASE):
                        data["cjzClaimant1381"] = nm
                        fields["cjzClaimant1381"] = nm
                        data["fields"] = fields
                        break
            selected_acts_ids = data.get("selectedActsIds") or fields.get("selectedActsIds")
            selected_acts_data_str = data.get("selectedActsData") or fields.get("selectedActsData")
            selected_entity_type = data.get("selectedEntityType") or fields.get("selectedEntityType")
            selected_collateral_option = data.get("selectedCollateralOption") or fields.get("selectedCollateralOption")

            normalized_template = (template_type or "").lower()
            source_document_type = (data.get("sourceDocumentType") or fields.get("sourceDocumentType") or "").lower()
            is_kfh = bool(data.get("isKfh") or fields.get("isKfh"))
            explicit_template_selected = bool(normalized_template)
            source_document_type_for_routing = source_document_type if not explicit_template_selected else ""

            # ВАЖНО: выбор актов в интерфейсе — АВТОРИТЕТНЫЙ источник, он приоритетнее
            # template_type. template_type приходит из pickTemplate() на фронте, который
            # подбирает шаблон АВТОМАТИЧЕСКИ и никогда не бывает пустым (фолбэк
            # 'rtk_single_obligation'), поэтому раньше условие `and not normalized_template`
            # всегда было ложным и выбор пользователя не использовался никогда —
            # вместо выбранных актов генерировался стандартный комплект.
            #
            # template_type остаётся в силе только когда пользователь не выбрал ни одного акта.
            can_use_selected_acts = bool(selected_acts_ids)
            unresolved_act_ids: List[str] = []

            # Если пользователь выбрал акты в интерфейсе (старый режим "выбор актов"),
            # и при этом нет явного template_type — используем их.
            if can_use_selected_acts:
                logger.info(f" Используем выбранные пользователем акты: {selected_acts_ids}")
                logger.info(f" Тип лица: {selected_entity_type}, Залог: {selected_collateral_option}")

                # Извлекаем дополнительные поля из selectedActsData (JSON строка)
                if selected_acts_data_str:
                    try:
                        import json
                        selected_acts_list = json.loads(selected_acts_data_str)
                        for act in selected_acts_list:
                            act_id = act.get("id")
                            additional_fields = act.get("additionalFields", {})
                            rtk_variant = act.get("rtkVariant")

                            if act_id == "final_rtk_inclusion" and rtk_variant:
                                data["final_rtk_inclusion_variant"] = rtk_variant
                                logger.info(f" Вариант для final_rtk_inclusion: {rtk_variant}")

                            if additional_fields:
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
                                    logger.info(f" Дополнительные поля для {act_id}: reason={reason[:50]}..., forParties={for_parties[:50]}..., courtRequests={court_requests[:50]}...")
                                elif act_id == "acceptance_definition":
                                    data["acceptance_definition_courtRequests"] = court_requests
                                    logger.info(f" Дополнительные поля для {act_id}: courtRequests={court_requests[:50]}...")
                                elif act_id == "acceptance_after_no_motion":
                                    data["acceptance_after_no_motion_courtRequests"] = court_requests
                                    logger.info(f" Дополнительные поля для {act_id}: courtRequests={court_requests[:50]}...")
                                else:
                                    logger.info(f" Дополнительные поля для {act_id}: reason={reason[:50]}..., forParties={for_parties[:50]}...")
                    except Exception as e:
                        logger.warning(f" Не удалось распарсить selectedActsData: {e}")

                templates, unresolved_act_ids = self._map_selected_acts_to_templates(
                    selected_acts_ids,
                    selected_entity_type or data.get("entityType") or fields.get("entityType", "individual"),
                    selected_collateral_option or "no_collateral",
                    data
                )

                # Выбор пользователя приоритетен: фолбэка на стандартный комплект здесь НЕТ.
                # Если не удалось сопоставить ни один выбранный акт — это ошибка, а не повод
                # сгенерировать документы, которых пользователь не просил.
                if not templates:
                    error_message = (
                        "Не удалось подобрать шаблоны для выбранных актов: "
                        + ", ".join(unresolved_act_ids or [selected_acts_ids])
                    )
                    logger.error(f" {error_message}")
                    return {"success": False, "error": error_message}

                logger.info(f" Найдено {len(templates)} шаблонов для выбранных актов")
                procedure_type = "custom_selected_acts"

            use_standard_logic = not can_use_selected_acts

            if use_standard_logic:
                templates, procedure_type = self._resolve_standard_templates(
                    data, normalized_template, source_document_type,
                    source_document_type_for_routing, is_kfh,
                )
            # Если templates не был установлен выше (стандартная логика), он должен быть установлен в блоке else
            if 'templates' not in locals() or templates is None:
                logger.error(" Не удалось определить шаблоны для генерации")
                return {
                    "success": False,
                    "error": "Не удалось определить шаблоны для генерации документов"
                }

            logger.info(f" Полученные данные: {data}")
            logger.info(f" Будет сгенерировано {len(templates)} документов")

            generated_documents = {}
            document_ids = []
            # Акты, которые пользователь выбрал, но сгенерировать не удалось: нет ветки
            # маппинга либо нет файла шаблона. Уходят в ответ, чтобы пользователь узнал
            # о них из интерфейса, а не только из логов.
            warnings: List[str] = [
                f"Акт «{act_id}» не поддерживается генерацией" for act_id in unresolved_act_ids
            ]

            for doc_type, template_info in templates.items():
                logger.info(f" Генерируем документ: {template_info['name']}")

                # Акт выбран пользователем — резолвим строго, без подмены произвольным .docx
                template_path = self._resolve_template_path(
                    template_info['path'], allow_any_docx_fallback=not can_use_selected_acts
                )
                logger.info(f"Путь к шаблону: {template_path.absolute()}")
                logger.info(f"Шаблон существует: {template_path.exists()}")

                if not template_path.exists():
                    logger.error(f"Шаблон не найден: {template_path.absolute()}")
                    warnings.append(
                        f"«{template_info['name']}» — файл шаблона не найден: {template_path.absolute()}"
                    )
                    continue

                doc = Document(str(template_path))
                logger.info(f"Загружен шаблон: {template_path}")

                self.set_times_new_roman_11(doc)

                # Заменяем данные в документе. Тип акта нужен _remove_empty_placeholders,
                # чтобы извещение чистило маркеры мягко (без вырезания предложений/абзацев).
                data["_current_doc_type"] = doc_type
                self.replace_document_data(doc, data)

                document_id = str(uuid.uuid4())
                document_ids.append(document_id)

                file_path = self.generated_dir / f"{document_id}.docx"
                doc.save(str(file_path))

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

                logger.info(f" Документ '{template_info['name']}' успешно сгенерирован: {file_path}")

            logger.info(f" Сгенерировано документов: {len(generated_documents)}")

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

            result = {
                "success": True,
                "documents": generated_documents,
                "document_ids": document_ids,
                "count": len(generated_documents)
            }
            if warnings:
                logger.warning(" Сгенерированы не все выбранные акты: " + "; ".join(warnings))
                result["warnings"] = warnings
            return result

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

                if os.path.exists(file_path):
                    os.remove(file_path)

                del self.documents[document_id]

                logger.info(f"Документ {document_id} успешно удален")
                return True
            else:
                logger.warning(f"Документ {document_id} не найден")
                return False

        except Exception as e:
            logger.error(f"Ошибка при удалении документа {document_id}: {str(e)}")
            return False

    def cleanup_old_documents(self, max_age_hours: int = 24) -> int:
        """
        Удаляет сгенерированные акты старше `max_age_hours` и возвращает их число.

        Акты — расходник: юрист скачал и ушёл. Раньше этот метод не вызывался
        ниоткуда, и папка росла бесконечно (в дереве разработки накопилось 376
        файлов на 13 МБ), а `self.documents` держал в памяти полный набор полей
        каждого документа за всё время жизни процесса.

        ОСТОРОЖНО. Метод удаляет файлы пользователя, поэтому границы жёсткие:
        только каталог `generated_dir` без рекурсии, только `*.docx` (и `*.zip`
        в подпапке `zips`), только по возрасту. Никаких «снести каталог».
        """
        removed = 0
        try:
            current_time = datetime.now()
            documents_to_delete = []

            for doc_id, doc_info in self.documents.items():
                generation_time = datetime.fromisoformat(doc_info["generation_date"])
                age_hours = (current_time - generation_time).total_seconds() / 3600

                if age_hours > max_age_hours:
                    documents_to_delete.append(doc_id)

            for doc_id in documents_to_delete:
                if self.delete_document(doc_id):
                    removed += 1

            removed += self._sweep_orphaned_files(max_age_hours)
            if removed:
                logger.info(f"Уборка: удалено {removed} устаревших файлов")

        except Exception as e:
            logger.error(f"Ошибка при очистке старых документов: {str(e)}")
        return removed

    def _sweep_orphaned_files(self, max_age_hours: int) -> int:
        """Подметает файлы, которых нет в `self.documents`.

        Реестр живёт только в памяти, поэтому после перезапуска бэкенда все
        прошлые акты становятся «ничьими» и обычная уборка их не видит. Ориентир
        для них — время модификации файла.
        """
        removed = 0
        cutoff = time.time() - max_age_hours * 3600
        known = {f"{doc_id}.docx" for doc_id in self.documents}

        # glob без рекурсии: подкаталоги (кроме zips ниже) не наши.
        targets = list(self.generated_dir.glob("*.docx"))
        zips_dir = self.generated_dir / "zips"
        if zips_dir.is_dir():
            targets += list(zips_dir.glob("*.zip"))

        for path in targets:
            if path.name in known:
                continue  # актуальный документ этого запуска — не трогаем
            try:
                if not path.is_file() or path.stat().st_mtime > cutoff:
                    continue
                path.unlink()
                removed += 1
            except OSError as exc:
                logger.debug(f"Не удалось удалить {path}: {exc}")
        return removed
