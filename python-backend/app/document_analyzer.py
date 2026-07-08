import re
import sys
import spacy
from docx import Document
from requisites_validation import is_valid_inn
from fio_detector import (
    extract_debtor_name,
    is_person_name,
    extract_debtor_details,
    extract_third_party_details,
    extract_debtors,
    extract_third_parties,
)
from org_normalizer import (
    base_org_name,
    norm_org_key,
    looks_like_law_ref,
    date_in_law_context,
)
from morph_utils import detect_gender, inflect_surname
from classify_mixin import ClassifyMixin
from parties_mixin import PartiesMixin
from amounts_mixin import AmountsMixin
from ip_mixin import IpExtractionMixin
from obligations_mixin import ObligationsMixin
from inflection_mixin import InflectionMixin
from patterns import build_patterns
from creditor_registry import _match_creditor_registry
import nlp_natasha as _nlp
import fns_registry as _fns_reg
from typing import Dict, Any, List, Tuple, Optional, Union
import logging
from pathlib import Path
import json

# Настройка логирования (должно быть до использования logger)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


try:
    from pymorphy3 import MorphAnalyzer
except ImportError:  # pragma: no cover - pymorphy3 может отсутствовать
    MorphAnalyzer = None

# Реестр известных банков/кредиторов: при совпадении названия подставляем ИНН, ОГРН, адрес из кода


class DocumentAnalyzer(ClassifyMixin, PartiesMixin, AmountsMixin, IpExtractionMixin, ObligationsMixin, InflectionMixin):
    def __init__(self):
        """
        Инициализация анализатора документов
        """
        self.nlp = None
        self.morph = None
        self.load_nlp_model()
        self.patterns = self.load_patterns()

    def load_nlp_model(self):
        """
        Загружает модель spaCy для русского языка.
        При запуске из exe (PyInstaller) модель ищется в _MEIPASS или рядом с exe (_internal).
        """
        try:
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).parent
                candidates = []
                if getattr(sys, "_MEIPASS", None):
                    candidates.append(Path(sys._MEIPASS) / "ru_core_news_sm")
                candidates.append(exe_dir / "_internal" / "ru_core_news_sm")
                candidates.append(exe_dir / "ru_core_news_sm")
                model_path = None
                for p in candidates:
                    if p.exists():
                        model_path = p
                        break
                if model_path:
                    self.nlp = spacy.load(str(model_path))
                    logger.info("Модель spaCy загружена из bundle (exe)")
                else:
                    self.nlp = None
                    logger.warning("Модель spaCy не найдена в bundle (exe)")
            else:
                self.nlp = spacy.load("ru_core_news_sm")
                logger.info("Модель spaCy загружена успешно")
        except OSError as e:
            logger.warning("Русская модель spaCy не найдена, используем базовую модель: %s", e)
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.error("Не удалось загрузить модель spaCy")
                self.nlp = None

    def load_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Загружает паттерны для извлечения данных
        """
        return build_patterns()

    def analyze(self, file_path: str) -> Dict[str, Any]:
        """
        Анализирует документ и извлекает данные

        Args:
            file_path: Путь к файлу документа

        Returns:
            Словарь с результатами анализа
        """
        try:
            logger.info(f"Начинаем анализ документа: {file_path}")

            # Извлекаем текст из документа
            text = self.extract_text(file_path)
            if not text:
                raise ValueError("Не удалось извлечь текст из документа")

            logger.info(f"Извлеченный текст (первые 500 символов): {text[:500]}")

            # Для повторного использования
            text_lower = text.lower()

            # Ранняя детекция КФХ
            is_kfh_detected, kfh_head_name = self._detect_kfh_head(text)

            # Определяем тип документа
            document_type = self.classify_document(text)

            # Извлекаем данные на основе типа документа
            if document_type in ("ip_collection", "ip_collection_collateral", "ip_collection_collateral_auto"):
                # Анализ ветки ИП-взыскания
                extracted_fields = self._analyze_ip_collection(text, document_type)
            elif document_type in ("legal_collection", "legal_collection_collateral", "legal_collection_collateral_auto"):
                # Анализ ветки взыскания с ЮЛ
                extracted_fields = self._analyze_legal_collection(text, document_type)
            elif document_type in ["ip_enforcement_statement", "ip_enforcement_statement_collateral",
                                 "ip_enforcement_realization", "ip_enforcement_realization_collateral",
                                 "ip_enforcement_restructuring", "ip_enforcement_restructuring_collateral"]:
                # Анализ ветки ИП-исполнения
                extracted_fields = self._analyze_ip_enforcement(text, document_type)
            elif document_type in ["physical_realization_collateral", "physical_restructuring_collateral", "observation_collateral", "competition_collateral"]:
                # Анализ ветки залога (реализация/наблюдение)
                extracted_fields = self._analyze_physical_collateral(text, document_type)
            else:
                # Универсальный fallback: если для типа документа нет собственных паттернов,
                # используем rtk_application как базовый шаблон, чтобы всё равно извлекать поля.
                effective_type = document_type
                if document_type not in self.patterns:
                    logger.info(
                        f"Тип документа '{document_type}' не имеет собственных паттернов, "
                        f"используем 'rtk_application' как базовый тип для извлечения полей"
                    )
                    effective_type = "rtk_application"

                extracted_fields = self.extract_fields(text, effective_type)
                collateral_detected = False

            # Возможный апгрейд типа -> observation_collateral
            document_type = self._maybe_upgrade_to_observation_collateral(extracted_fields, text, document_type, text_lower)

            # Устанавливаем флаг КФХ, если он был обнаружен ранним определением
            if is_kfh_detected:
                extracted_fields["isKfh"] = True
                if kfh_head_name:
                    extracted_fields["kfhHeadName"] = kfh_head_name
                logger.info(f"✅ Установлен флаг isKfh=True, глава КФХ: {kfh_head_name}")

            if document_type:
                extracted_fields["sourceDocumentType"] = document_type

            # Заполняем реквизиты кредитора: из реестра или из текста
            self._fill_creditor_requisites(extracted_fields, text)

            # Оцениваем уверенность в результатах
            confidence = self.calculate_confidence(document_type, extracted_fields, text)

            # Постобработка ипотеки и валидация номера дела
            self._postprocess_mortgage_and_case_number(extracted_fields, text, document_type)

            # Определяем рекомендуемые акты на основе типа документа, типа лица и залога
            recommended_acts = self._get_recommended_acts(document_type, extracted_fields, text)

            # Разделяем описание предметов залога на отдельные предметы и создаем массив collaterals
            collateral_description = extracted_fields.get("mortgageCollateralDescription1221")
            if collateral_description and re.match(r"^Кому\s+выдана\s+", (collateral_description or "").strip(), re.IGNORECASE):
                collateral_description = None
                if "mortgageCollateralDescription1221" in extracted_fields:
                    del extracted_fields["mortgageCollateralDescription1221"]
            # Собираем ВСЕ предметы залога по всему документу (по всем обязательствам):
            # недвижимость и авто, каждый своей карточкой. Дубли (один и тот же объект,
            # упомянутый в нескольких местах) схлопываем, оставляя самый заполненный.
            collateral_descs = self._extract_all_collateral_items(text)
            if not collateral_descs and collateral_description:
                collateral_descs = self._split_collateral_items(collateral_description)
            collaterals_list = self._dedupe_collaterals(
                [self._make_collateral_obj(idx, d) for idx, d in enumerate(collateral_descs)]
            )
            # Отбрасываем нереальные «иное» (шаблонные «Предметом залога является …»).
            collaterals_list = [c for c in collaterals_list if self._collateral_has_substance(c)]
            if collaterals_list:
                logger.info(f"✅ Создано {len(collaterals_list)} предметов залога: {[c['collateralType'] for c in collaterals_list]}")

            # Корректировка ФИО должника: если извлечённое имя не похоже на ФИО
            # физлица (например, regex подхватил «Обязательства По Своевременному»
            # или «ПАО Сбербанк Место»), берём детерминированный позиционный разбор
            # блока «Ответчик(и):/Должник:» и пересчитываем падежи.
            self._fix_debtor_name(text, extracted_fields)

            # Реквизиты должника-физлица из его записи
            details = self._finalize_debtor_person_requisites(extracted_fields, text)

            # Пост-очистка полей (адрес/третье лицо/суд)
            self._cleanup_extracted_fields(extracted_fields, text)

            # Своп сторон: applicantName ошибочно = кредитор (раскладки «Заявитель:» → «Должник:»)
            self._reconcile_applicant_is_debtor(extracted_fields, text)

            # Косметика артефактов сторон: роль-суффикс «(заёмщик)», хвост метки в courtName, мусорный managerName
            self._cleanup_party_artifacts(extracted_fields, text)

            # Формат ВТБ «реестр Nл»: метки КРЕДИТОР:/ДОЛЖНИК:/ФИН.УПРАВЛЯЮЩИЙ: идут
            # стопкой, значения — ниже по порядку. Обычный разбор путает стороны —
            # отдельный обработчик переустанавливает их (если сигнатура найдена).
            self._apply_stacked_party_layout(extracted_fields, text)

            # Реквизиты кредитора: повтор ПОСЛЕ установки creditorName (фолбэк по
            # метке «Заявитель …» выставляет имя в _cleanup_party_artifacts, а первый
            # вызов на стр.170 мог отработать вхолостую при пустом creditorName).
            if (not extracted_fields.get("creditorInn")
                    and not extracted_fields.get("creditorOgrn")):
                self._fill_creditor_requisites(extracted_fields, text)
            # Реквизиты из документа уже есть, но адрес кредитора пуст — дозаполняем
            # (адрес из блока кредитора или из реестра известных банков).
            elif not extracted_fields.get("creditorAddress"):
                self._fill_creditor_requisites(extracted_fields, text)

            # Заявление уполномоченного органа (ФНС): кредитор/заявитель — налоговый
            # орган (в шапке-бланке, без метки «Кредитор:»), а не должник-физлицо.
            # ДО разбора должников — чтобы карточка должника взяла ФИО/адрес из
            # debtor*, а не из applicantName (там ФНС). И ДО NLP-сети (у ФНС свой шаблон).
            self._apply_fns_authority(extracted_fields, text)

            # Гибрид-сеть (Natasha, второстепенно): если кредитор не распознан ни
            # меткой, ни реестром, ни ФНС-детектором — берём кандидата-организацию из
            # NER по шапке. Ловит незнакомые раскладки, где label-парсер пасует.
            self._fill_creditor_nlp(extracted_fields, text)

            # Списки должников и третьих лиц + дедуп
            debtors_result, third_parties_result = self._resolve_debtors_and_third_parties(extracted_fields, text, details)

            # Залоги. Недвижимость/авто — всегда реальны. «Иное» (оборудование,
            # линии, товары и т.п.) — это ВСЁ, что не недвижимость и не ТС; оставляем,
            # если у предмета есть конкретная стоимость и наименование (это и проверяет
            # _collateral_has_substance). Болванки переизвлечения («Поттер Г.Д.»,
            # «по доверенности №…») стоимости не имеют и отсеиваются там же.
            _raw_cols = collaterals_list if collaterals_list else extracted_fields.get('collaterals', [])
            collaterals_final = [c for c in _raw_cols if self._collateral_has_substance(c)]
            if not collaterals_final:
                extracted_fields.pop("mortgageCollateralDescription1221", None)
                extracted_fields.pop("collaterals", None)

            # Финальная нормализация блока «Финансовые данные» — последней, ПОСЛЕ
            # всех слияний (ip_specific_fields и пр.), чтобы её результат был
            # окончательным для неустойки/штрафов/госпошлин/дат ПП/итога.
            self._normalize_financial_block(extracted_fields, text)

            # Финансы из просительной части (суммы по обязательствам) — перекрывают
            # обычную нормализацию, если в «просим суд: …включить…» найдены суммы.
            self._apply_prayer_finances(extracted_fields, text)

            # Точечный разбор финансов формата ВТБ «реестр Nл» (сигнатура меток
            # стопкой) — общий парсер этот лейаут не берёт; перекрывает результат
            # ТОЛЬКО при найденной сигнатуре, не задевая остальной корпус.
            self._apply_stacked_finances(extracted_fields, text)

            # Табличная разбивка задолженности («Структура задолженности | Значение |
            # RUR» по нескольким договорам) — суммируется; гейт по сигнатуре таблицы
            # и валидация суммы = «ОБЩАЯ ЗАДОЛЖЕННОСТЬ».
            self._apply_table_breakdown_finances(extracted_fields, text)

            # ФНС-заявления: финансы по ОЧЕРЕДЯМ реестра (недоимка/налог/пени/штраф/
            # НДФЛ/взносы/госпошлина по 1/2/3 очереди). Гейт по кредитору-ФНС;
            # перекрывает общий парсер и чистит скрытый общий блок финансов.
            self._apply_fns_queue_finances(extracted_fields, text)

            # Имя кредитора, обрезанное на переносе строки внутри названия
            # («…"МТС-» + «Банк"» ниже) — дотягиваем по тексту.
            self._fix_truncated_creditor_name(extracted_fields, text)

            # Адрес управляющего — фолбэк для многострочного «Адрес регистрации:»,
            # когда ФИО и адрес на разных строках (общие паттерны не справляются).
            self._fill_manager_address(extracted_fields, text)

            # Саморегулируемая организация: сопоставляем упоминание СРО из текста с
            # реестром sro_data и подставляем каноничное полное имя (NAIM_FULL).
            self._resolve_manager_sro(extracted_fields, text)

            # Вспомогательный NLP-слой (Natasha, второстепенно): когда regex не
            # извлёк адрес совсем или обрезал его — достраиваем по окну роли.
            self._refine_addresses_nlp(extracted_fields, text)

            # Адрес не может содержать реквизиты (ИНН/ОГРН/ОГРНИП/СНИЛС/КПП) —
            # обрезаем хвост, а полностью мусорные адреса (без букв) убираем.
            self._sanitize_address_fields(extracted_fields)

            # Банкротная госпошлина не должна совпадать с итогом/осн.долгом —
            # это мусор (в документе отдельной банкротной госпошлины нет). Чистим.
            self._clear_garbage_bankruptcy_duty(extracted_fields)

            # Ранее вынесенное решение другого суда (взыскание до банкротства).
            prior_decision = self._extract_prior_court_decision(text)
            if prior_decision:
                for k, v in prior_decision.items():
                    if v:
                        extracted_fields[k] = v
                # Если основной номер дела совпал с «ранее вынесенным» — это его
                # контекст («…по делу №… взыскана…»), а не дело текущего заявления.
                pc = prior_decision.get("priorCaseNumber")
                if pc and extracted_fields.get("caseNumber") == pc:
                    extracted_fields.pop("caseNumber", None)

            # Разбивка полей финансов на слагаемые (для тултипа «откуда число») —
            # top-level, НЕ в fields (иначе попала бы в editedFields как [object Object]
            # и в golden). None, если разбивки нет.
            finance_breakdown = extracted_fields.pop("financeBreakdown", None)

            # Самобанкротство (заявитель = сам должник): флаг top-level, НЕ в
            # fields — по образцу financeBreakdown (не попадает в golden и в
            # editedFields фронта). Фронт по нему автопроставляет статус
            # должника «Самобанкрот» и скрывает блок кредитора.
            application_kind = (
                "self_bankruptcy" if self._detect_self_bankruptcy(text) else None
            )

            # Формируем результат
            result = {
                "documentType": document_type,
                "confidence": confidence,
                "fields": extracted_fields,
                "obligations": extracted_fields.get('obligations', []),
                "collaterals": collaterals_final,
                "financeBreakdown": finance_breakdown,
                "applicationKind": application_kind,
                "rawText": text,
                "metadata": {
                    "pageCount": self.get_page_count(file_path),
                    "wordCount": len(text.split()),
                    "language": "ru"
                },
                "recommendedActs": recommended_acts,
                "debtors": debtors_result,
                "thirdParties": third_parties_result
            }

            entity_type = extracted_fields.get("entityType")
            if entity_type:
                result["entityType"] = entity_type

            logger.info(f"Анализ завершен. Тип: {document_type}, уверенность: {confidence:.2f}")
            logger.info(f"Рекомендуемые акты: {recommended_acts}")
            return result

        except Exception as e:
            logger.error(f"Ошибка при анализе документа: {str(e)}")
            raise

    # Префиксы перед ФИО, которые убираем перед склонением.
    _NAME_PREFIX_RE = r'^(ИП\s+|ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+)'

    # Типы судов РФ (основы прилагательных перед словом «суд»).
    _COURT_KIND_RE = (
        r"(?:городск|районн|межрайонн|областн|краев|окружн|верховн|гарнизонн|военн|"
        r"арбитражн|конституционн|уставн|апелляционн|кассационн|третейск|мирск)\w*"
    )

    # Общие слова в названии суда, которые пишутся со строчной буквы.
    _COURT_LOWER_WORDS = {
        "суд", "суда", "суде", "суду", "судом", "арбитражный", "районный", "городской",
        "межрайонный", "областной", "краевой", "окружной", "верховный", "военный",
        "гарнизонный", "апелляционный", "кассационный", "конституционный", "уставный",
        "мировой", "мировому", "судье", "судьи", "судебного", "судебный", "участка",
        "участок", "области", "область", "край", "края", "краю", "республики",
        "республика", "республике", "округа", "округ", "округе", "города", "город",
        "автономного", "автономной", "общей", "юрисдикции", "района", "район", "и", "по",
    }


    def _clean_court_line(self, s: str) -> Optional[str]:
        """Очищает строку с названием суда: убирает приставку «В …» и хвост-адрес."""
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"^(?:В|Во)\s+(?=[А-ЯЁ])", "", s)          # адресная приставка «В …»
        s = re.sub(r"^(?:от\s+истца|истец|заявитель)[\s:,-]*", "", s, flags=re.IGNORECASE)
        s = re.split(r",?\s*\d{5,6}\b", s)[0]                  # обрезаем по почтовому индексу
        s = re.split(r"\s+(?:от\s+истца|от\s+заявител)", s, flags=re.IGNORECASE)[0]
        # обрезаем адресный хвост без индекса («…, ул. Ленина», «…, г. Москва»)
        s = re.split(r",\s*(?:ул\.|улиц|г\.|город|пр-?кт|проспект|пер\.|переул|пл\.|площад|наб\.|бул|шоссе|д\.\s*\d)",
                     s, flags=re.IGNORECASE)[0]
        s = s.strip(" ,.;")
        if 6 <= len(s) <= 140 and re.search(r"(?:суд|участ|судь)", s, re.IGNORECASE):
            return s
        return None






    def extract_text(self, file_path: str) -> str:
        """
        Извлекает текст из документа. Поддерживаются форматы: .docx (Word), .pdf.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_text_from_pdf(file_path)
        if suffix in (".docx", ".doc"):
            return self._extract_text_from_docx(file_path)
        raise ValueError(f"Неподдерживаемый формат файла: {suffix}. Используйте .docx или .pdf")

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """Извлекает текст из PDF."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                part = page.extract_text()
                if part and part.strip():
                    text_parts.append(part.strip())
            if not text_parts:
                raise ValueError("PDF не содержит извлекаемого текста (возможно, скан или пустой файл)")
            return "\n".join(text_parts)
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Ошибка при извлечении текста из PDF: {str(e)}")
            raise ValueError("Не удалось извлечь текст из PDF (возможно, файл поврежден или скан без OCR)") from e

    def _extract_text_from_docx(self, file_path: str) -> str:
        """Извлекает ВЕСЬ текст из Word документа (.docx).

        Полный обход (надмножество старой логики «параграфы + таблицы»):
          1. тело: параграфы и таблицы — в порядке документа (важно для
             контекстных паттернов классификации вида «Должник:\\nИП ...»);
          2. колонтитулы всех секций (6 контейнеров) — с дедупликацией;
          3. надписи / текстовые поля (w:txbxContent);
          4. сноски и концевые сноски.
        Реквизиты (наименование, ИНН, КПП, адрес, банк) в юр-заявлениях часто
        лежат именно в колонтитуле или надписи на бланке — старый способ их терял.
        """
        try:
            doc = Document(file_path)
            text_parts: List[str] = []

            # 1. Тело документа: параграфы, затем таблицы
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text.strip())

            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            text_parts.append(cell.text.strip())

            # 2. Колонтитулы всех секций: header/footer + first_page + even_page.
            # Секции часто ссылаются на один и тот же колонтитул — дедуплицируем.
            seen_headers = set()
            for section in doc.sections:
                for container in (
                    section.header, section.footer,
                    section.first_page_header, section.first_page_footer,
                    section.even_page_header, section.even_page_footer,
                ):
                    if container is None:
                        continue
                    try:
                        chunk_parts = []
                        for paragraph in container.paragraphs:
                            if paragraph.text.strip():
                                chunk_parts.append(paragraph.text.strip())
                        for table in container.tables:
                            for row in table.rows:
                                for cell in row.cells:
                                    if cell.text.strip():
                                        chunk_parts.append(cell.text.strip())
                        chunk = "\n".join(chunk_parts)
                        if chunk and chunk not in seen_headers:
                            seen_headers.add(chunk)
                            text_parts.append(chunk)
                    except Exception as exc:
                        logger.warning(f"Не удалось обработать колонтитул: {exc}")

            # 3 + 4. Надписи (w:txbxContent) и сноски/концевые сноски —
            # части DOCX, недоступные через объектную модель python-docx.
            text_parts.extend(self._extract_docx_raw_xml_text(file_path))

            if not text_parts:
                raise ValueError("Документ пуст или не содержит извлекаемого текста")
            return "\n".join(text_parts)
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Ошибка при извлечении текста из Word: {str(e)}")
            raise ValueError("Не удалось извлечь текст из документа (возможно, файл поврежден или пустой)") from e

    def _extract_docx_raw_xml_text(self, file_path: str) -> List[str]:
        """Собирает текст из частей DOCX, не покрытых моделью python-docx.

        Открывает .docx как zip и через lxml извлекает:
          - надписи / текстовые поля (w:txbxContent) из document.xml и всех
            header*/footer* — модель python-docx их не отдаёт;
          - сноски и концевые сноски (footnotes.xml / endnotes.xml).
        Полностью оффлайн (zipfile + lxml, lxml уже идёт зависимостью python-docx).
        """
        from zipfile import ZipFile
        from lxml import etree

        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        ns = {"w": W}
        results: List[str] = []
        seen = set()

        def paragraph_lines(node) -> List[str]:
            """Текст узла по абзацам: каждый w:p → одна строка (склейка w:t)."""
            lines = []
            for p in node.findall(".//w:p", ns):
                line = "".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
                if line:
                    lines.append(line)
            return lines

        def add(chunk: str) -> None:
            if chunk and chunk not in seen:
                seen.add(chunk)
                results.append(chunk)

        try:
            with ZipFile(file_path) as zf:
                names = set(zf.namelist())

                # 3. Надписи: document.xml + все header*/footer*.
                # Берём ТОЛЬКО w:txbxContent, иначе продублируем тело документа.
                txbx_parts = [
                    n for n in names
                    if n == "word/document.xml"
                    or (n.startswith(("word/header", "word/footer")) and n.endswith(".xml"))
                ]
                for part in txbx_parts:
                    root = etree.fromstring(zf.read(part))
                    for tb in root.findall(".//w:txbxContent", ns):
                        add("\n".join(paragraph_lines(tb)))

                # 4. Сноски и концевые сноски — целиком.
                for part in ("word/footnotes.xml", "word/endnotes.xml"):
                    if part not in names:
                        continue
                    root = etree.fromstring(zf.read(part))
                    for line in paragraph_lines(root):
                        add(line)
        except Exception as exc:
            logger.warning(f"Не удалось извлечь сырой XML-текст из DOCX: {exc}")

        return results



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
        tokens = [token for token in re.split(r"\s+", full_name.strip()) if token]
        capitalized_tokens = [self._capitalize_word(token) for token in tokens]
        return " ".join(capitalized_tokens)

    def _strip_ooo_prefix(self, name: Optional[str]) -> Optional[str]:
        """
        Убирает приставку ООО/Общество с ограниченной ответственностью, оставляя только название.
        """
        if not name:
            return name
        trimmed = name.strip(' «»"')
        match = re.match(
            r'^(?:ООО|Обществ[ао]\s+с\s+ограниченной\s+ответственностью)\s*[«"]?(.+?)[»"]?$',
            trimmed,
            re.IGNORECASE
        )
        if match:
            return self.clean_extracted_value(match.group(1).strip(' «»"'))
        return name

    def _convert_full_name_case(self, full_name: str, target_case: str) -> Optional[str]:
        if not full_name:
            return None
        tokens = [token for token in re.split(r"\s+", full_name.strip()) if token]
        if not tokens:
            return None
        inflected_tokens = [self._inflect_word(token, target_case) for token in tokens]
        result = " ".join(inflected_tokens).strip()
        return result or None

    def _extract_creditor_name_from_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        # Приоритет: полное название организации после "Истец:"
        patterns = [
            r"Истец[:\s]*\n\s*((?:ООО|ОАО|ПАО|ЗАО|АО|Обществ[ао]\s+с\s+ограниченной\s+ответственностью|Публичное\s+акционерное\s+общество)[^,\n\\[\\]]+)",  # Истец:\nПАО Сбербанк
            r"Истец[:\s]+((?:ООО|ОАО|ПАО|ЗАО|АО|Общество\s+с\s+ограниченной\s+ответственностью|Публичное\s+акционерное\s+общество)[^,\n\\[\\]]+)",  # Истец: ПАО Сбербанк
                        r"Истец[:\s]*\n\s*([А-ЯЁ][А-ЯЁа-яё\s«»\"“”]{5,100}?)(?=\n|$|,|\[|ИНН|ОГРН|адрес|телефон|Место|Дата)",  # Истец:\nНазвание организации
                        r"Истец[:\s]+([А-ЯЁ][А-ЯЁа-яё\s«»\"“”]{5,100}?)(?=\n|$|,|\[|ИНН|ОГРН|адрес|телефон|Место|Дата)",  # Истец: Название организации
            r"Истец[:\s]+([^\n]+)",  # Общий паттерн
        ]
        for pattern_str in patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE | re.MULTILINE)
            match = pattern.search(text)
            if match:
                creditor = match.group(1).strip()
                # Останавливаемся на ключевых словах, которые не являются частью названия
                stop_words = ['Место нахождения', 'Дата государственной регистрации', 'ОГРН', 'ИНН', 'адрес']
                for stop_word in stop_words:
                    if stop_word in creditor:
                        creditor = creditor.split(stop_word)[0].strip()
                creditor = self.clean_extracted_value(creditor)
                # Проверяем, что это не слишком длинный текст (не описание)
                if creditor and len(creditor) < 200 and not any(word in creditor.lower() for word in ['имеет право', 'потребовать', 'судебном порядке']):
                    return creditor

        # Фолбэк для иных раскладок: кредитор по синониму метки (Заявитель/Кредитор/
        # Взыскатель) и БЕЗ обязательного ОПФ — для гос.органов («ФНС России») и
        # банков без префикса. Берём имя до реквизитов/перевода строки.
        from label_synonyms import CREDITOR_HEADER_LABELS, labels_alternation
        alt = labels_alternation(CREDITOR_HEADER_LABELS)
        m = re.search(
            rf"(?:{alt})\s*:?\s*"
            rf"([А-ЯЁ][^\n\r]{{3,150}}?)"
            rf"(?=\n|\r|$|\bИНН\b|\bОГРН|Дата\s+гос|Место\s+нахожд|Почтовый|[Аа]дрес|www\.|\bтел)",
            text, re.IGNORECASE,
        )
        if m:
            creditor = self.clean_extracted_value(m.group(1)).strip(" ,;")
            # «ФНС России в лице\nМежрайонной ИФНС …» — кредитор продолжается на
            # следующей строке: дописываем продолжение до реквизитов/адреса.
            if re.search(r"в\s+лице\s*$", creditor, re.IGNORECASE):
                cont = re.search(
                    r"в\s+лице\s*\n\s*([^\n]+?)\s*(?=\n|Адрес|ИНН|ОГРН|Почтов|$)",
                    text, re.IGNORECASE,
                )
                if cont:
                    creditor = (creditor + " " + self.clean_extracted_value(cont.group(1))).strip(" ,;")
            # Срезаем хвостовую скобку с дублем/ОПФ: «… «ТБАНК» (АО «ТБАНК»…)» -> «… «ТБАНК»»,
            # «ББР Банк (акционерное общество)» -> «ББР Банк».
            creditor = re.split(r"\s*\(", creditor, maxsplit=1)[0].strip(" ,;")
            cl = creditor.lower()
            # Отсекаем мусор: маркеры шаблона [12]/[987], boilerplate-фразы, описания.
            has_marker = bool(re.search(r"\[\d", creditor))
            boilerplate = any(w in cl for w in [
                'имеет право', 'потребовать', 'судебном порядке', 'должник', 'ответчик',
                'требовани', 'утвердить', 'просит', 'в размере', 'из числа', ' руб',
            ])
            # Должно быть похоже на кредитора: банк/общество/ФНС/инспекция/служба/ОПФ.
            looks_creditor = bool(re.search(
                r'банк|общество|фнс|росси|инспекц|служб|\bАО\b|\bООО\b|\bПАО\b|\bОАО\b|\bЗАО\b',
                creditor, re.IGNORECASE))
            if creditor and 3 < len(creditor) < 150 and not has_marker and not boilerplate and looks_creditor:
                return creditor

        # Фолбэк 2: кредитор назван в просительной части — «(включить) требование
        # кредитора <Банк/Общество …>» (без шапки-метки). Берём название с ОПФ.
        m2 = re.search(
            r"(?:требовани\w*\s+)?кредитора\s+"
            r"((?:Банк\w*\s+)?(?:ВТБ|Сбербанк|[А-ЯЁ][А-ЯЁа-яё«»\"-]+)"
            r"[^,\n]{0,60}?(?:\([^)]*обществ[^)]*\)|«[^»]+»))",
            text, re.IGNORECASE,
        )
        if m2:
            creditor = self.clean_extracted_value(m2.group(1)).strip(" ,;")
            cl = creditor.lower()
            looks_cred = bool(re.search(r"банк|общество|\bАО\b|\bПАО\b|\bООО\b|\bОАО\b|\bЗАО\b", creditor, re.IGNORECASE))
            bad = any(w in cl for w in ("банкротств", "финансирован", "процедур", "должник", "требовани"))
            if creditor and 3 < len(creditor) < 150 and looks_cred and not bad:
                return creditor
        return None

    def _extract_creditor_block(self, text: str) -> Optional[str]:
        """Извлекает блок текста с реквизитами кредитора.

        Якорь — «Заявитель (кредитор)» / «Истец:» / «Кредитор:». Метка может стоять
        как на отдельной строке («Истец:\nООО …»), так и инлайн («Истец: ООО …»):
        в обоих случаях блок начинается со строки-метки и обрезается по началу блока
        должника, чтобы не захватить его реквизиты (ИНН/ОГРН/адрес должника).
        """
        if not text:
            return None
        header = text[:4500]
        for start_pattern in [
            r"Заявитель\s*\(кредитор\)\s*:?\s*",
            r"Истец\s*:\s*",
            r"Кредитор\s*:\s*",
            # «Заявитель Акционерное общество …» — без «(кредитор)» и двоеточия.
            r"Заявитель\s+(?=(?:Акционерн|Публичн|Общество|ООО|АО|ПАО|ЗАО|ОАО|ИП|ФНС|«))",
        ]:
            m = re.search(start_pattern, header, re.IGNORECASE)
            if m:
                # Включаем строку-метку (имя кредитора на той же или следующей строке).
                block_start = m.start()
                block_end = min(block_start + 1200, len(header))
                block = header[block_start:block_end]
                # Обрезаем по началу блока должника / третьего лица / управляющего,
                # чтобы адрес/ИНН/ОГРН брались только из секции кредитора.
                cut = re.search(
                    r"\n\s*(?:Должник|Ответчик|Треть[ие]\s+лиц|"
                    r"(?:Финансов|Временн|Конкурсн)\w+\s+управляющ)",
                    block, re.IGNORECASE,
                )
                if cut:
                    block = block[: cut.start()]
                if re.search(r"ИНН|ОГРН|адрес|место\s+нахождения", block, re.IGNORECASE):
                    return block
        return None


    def _clean_creditor_address(self, addr: str) -> str:
        """Очищает юр-адрес кредитора от постороннего: скобочных пометок и хвостов."""
        addr = re.sub(r"\s*\([^)]*\)", "", addr)  # «(не для направления …)» и пр.
        # Обрезаем всё после адреса: почтовый/фактический адрес, телефон, реквизиты.
        # Пробел между словами может отсутствовать (слипшийся текст из docx):
        # «д. 19Почтовыйадресдля» — поэтому \s* (не \s+).
        addr = re.split(
            r"\s*(?:Почтов\w*\s*адрес|Фактическ\w*\s*адрес|Адрес\s*для|[Тт]елефон|[Тт]ел\.|"
            r"e-?mail|эл\.?\s*почт|ОГРН|ИНН|КПП|БИК|Дата\s+гос|р/с|к/с|корр)",
            addr, flags=re.IGNORECASE,
        )[0]
        addr = re.sub(r"\s+", " ", addr).strip().strip(",;. ")
        return addr

    def _extract_creditor_address(self, text: str) -> Optional[str]:
        """Извлекает ТОЛЬКО юридический адрес кредитора (без почтового и мусора)."""
        block = self._extract_creditor_block(text)
        if not block:
            return None
        # Приоритет — явные метки юр-адреса; «почтовый/фактический адрес» исключаем.
        for addr_pattern in [
            r"(?:место\s+нахождения|юридическ\w+\s+адрес)[:\s]*([0-9]{6}[,\s]+[^\n]+)",
            r"(?:место\s+нахождения|юридическ\w+\s+адрес)[:\s]*([^\n]+)",
            # Плоская метка «Адрес:» в начале строки (индекс + продолжение на след. строке).
            r"(?:^|\n)\s*адрес[:\s]*([0-9]{6}[,\s]+[^\n]+(?:\n[^\n]+)?)",
        ]:
            addr_m = re.search(addr_pattern, block, re.IGNORECASE)
            if addr_m:
                addr = self._clean_creditor_address(self.clean_extracted_value(addr_m.group(1).strip()))
                # Должно быть похоже на адрес (индекс/город/улица), без почтовых меток.
                if addr and 10 <= len(addr) <= 200 and re.search(r"\d{6}|город|\bг\.|ул\.|улиц|пр-?кт|проспект", addr, re.IGNORECASE):
                    return addr
        # Фолбэк: адрес без метки — первая строка блока кредитора, начинающаяся
        # с почтового индекса (6 цифр). Блок уже обрезан по началу секции должника,
        # поэтому это адрес именно кредитора. Почтовый/фактический адрес исключаем.
        lines = [ln.strip() for ln in block.split("\n")]
        for i, line in enumerate(lines):
            if re.match(r"^\d{6}[,\s]", line) and not re.match(
                r"^\d{6}[,\s].*(?:почтов|фактическ|а/я|абонентск)", line, re.IGNORECASE
            ):
                parts = [line]
                # Дособираем продолжение адреса: иногда между строками адреса
                # вклинивается «Исх. №…/Дата…» — такие строки пропускаем, а строки
                # с адресными токенами (наб/ул/д./стр/…) приклеиваем.
                for nxt in lines[i + 1:i + 5]:
                    if not nxt:
                        break
                    if re.match(r"^(?:Исх\b|Дата\b|№|тел|e-?mail|на\s+№)", nxt, re.IGNORECASE):
                        continue
                    if re.search(r"(?:\bнаб\b|\bул\b|улиц|\bд\.|\bстр\b|\bпер\b|пр-?кт|проспект|шоссе|корп|\bпом\b|\bкв\b|\bоф\b|\bзд\b|литер)", nxt, re.IGNORECASE):
                        parts.append(nxt)
                        continue
                    break
                addr = self._clean_creditor_address(self.clean_extracted_value(" ".join(parts)))
                if addr and 10 <= len(addr) <= 200:
                    return addr
        return None

    def _extend_address_from_text(self, text: str, address: Optional[str]) -> Optional[str]:
        if not text or not address:
            return None

        address_clean = address.strip()
        if not address_clean:
            return None

        pattern = re.compile(re.escape(address_clean), re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return None

        start_idx = text.rfind('\n', 0, match.start())
        line_start = start_idx + 1 if start_idx != -1 else match.start()
        end_idx = text.find('\n', match.end())
        line_end = end_idx if end_idx != -1 else min(len(text), match.end() + 150)
        extended_line = text[line_start:line_end].strip()
        if len(extended_line) > len(address_clean):
            extended = self.clean_extracted_value(extended_line)
            # Расширение до всей строки могло вернуть ведущий ярлык
            # («Юридический адрес: …»). Отрезаем его.
            extended = re.sub(
                r"^\s*(?:юридическ\w*\s*адрес|адрес\w*\s*регистрации|"
                r"адрес\w*\s*прописки|мест\w*\s*нахождени\w*|"
                r"мест\w*\s*жительства|адрес)\s*:?\s*",
                "", extended, flags=re.IGNORECASE
            ).strip(" ,;:")
            return extended or None
        return None

    def _normalize_mortgage_interface_fields(self, fields: Dict[str, Any], text: str):
        def _strip_procedure_phrase(name: Optional[str]) -> Optional[str]:
            if not name:
                return name
            cleaned = re.sub(r"\s*должника\s+введена\s+процедура.*$", "", name, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*введена\s+процедура\s+наблюдения.*$", "", cleaned, flags=re.IGNORECASE)
            return cleaned.strip()

        # Для competition_collateral специально извлекаем название должника из шапки после "Должник:" на следующей строке
        source_doc_type = fields.get("sourceDocumentType", "").lower()
        if source_doc_type == "competition_collateral":
            # Ищем блок "Должник:" и извлекаем название на следующей строке
            debtor_match = re.search(
                r"Должник[:\s]*\n\s*((?:ООО|ОАО|ПАО|ЗАО|АО|Обществ[ао]\s+с\s+ограниченной\s+ответственностью)[^\n]{0,200}?)(?=\n|$|ИНН|ОГРН|адрес|телефон)",
                text,
                re.IGNORECASE | re.MULTILINE
            )
            if debtor_match:
                debtor_name = debtor_match.group(1).strip()
                # Очищаем от лишних символов и обрезаем до разумной длины
                debtor_name = re.sub(r"\s+", " ", debtor_name)
                debtor_name = debtor_name[:200].strip()
                if debtor_name and len(debtor_name) > 5:
                    # Удаляем префикс ООО/ОАО и т.д. если нужно
                    cleaned_name = self._strip_ooo_prefix(debtor_name)
                    if cleaned_name and "суд" not in cleaned_name.lower():
                        fields["applicantName"] = cleaned_name
                        fields["debtorName"] = cleaned_name
                        fields["mortgageDebtorName"] = cleaned_name
                        logger.info(f"Извлечено название должника для competition_collateral: {cleaned_name}")

        fields["mortgageDebtorName"] = _strip_procedure_phrase(self._strip_ooo_prefix(fields.get("mortgageDebtorName")))
        fields["debtorName"] = _strip_procedure_phrase(self._strip_ooo_prefix(fields.get("debtorName")))
        # Для applicantName сохраняем ОПФ (ООО, АО и т.д.) для маркеров [2], [2.1], [2.2]
        fields["applicantName"] = _strip_procedure_phrase(fields.get("applicantName"))

        name_candidates = [
            fields.get("mortgageDebtorName"),
            fields.get("debtorName"),
            fields.get("applicantName")
        ]
        proper_name = None
        for candidate in name_candidates:
            if candidate and "суд" not in candidate.lower():
                proper_name = self._capitalize_full_name(candidate)
                break

        if proper_name:
            fields["mortgageDebtorName"] = proper_name
            fields["debtorName"] = proper_name
            fields["applicantName"] = proper_name

            genitive = fields.get("applicantNameGenitive")
            if not genitive or "суд" in genitive.lower():
                genitive_name = self._convert_full_name_case(proper_name, "gent")
                if genitive_name:
                    fields["applicantNameGenitive"] = self._capitalize_full_name(genitive_name)

            dative = fields.get("mortgageDebtorNameDative")
            if not dative:
                dative_name = self._convert_full_name_case(proper_name, "datv")
                if dative_name:
                    fields["mortgageDebtorNameDative"] = self._capitalize_full_name(dative_name)

        # Пробрасываем общие кредитные поля в специальные ипотечные маркеры [111]-[114],
        # если они не были извлечены прямо.
        credit_amount = fields.get("mortgageCreditAmount111") or fields.get("creditAmount")
        if credit_amount and not fields.get("mortgageCreditAmount111"):
            fields["mortgageCreditAmount111"] = credit_amount

        credit_term = fields.get("mortgageCreditTerm112") or fields.get("creditTermMonths")
        if credit_term and not fields.get("mortgageCreditTerm112"):
            fields["mortgageCreditTerm112"] = credit_term

        interest_rate = fields.get("mortgageInterestRate113") or fields.get("creditInterestRate")
        if interest_rate and not fields.get("mortgageInterestRate113"):
            fields["mortgageInterestRate113"] = interest_rate

        penalty_rate = fields.get("mortgagePenaltyRate114") or fields.get("creditPenaltyRate")
        if penalty_rate and not fields.get("mortgagePenaltyRate114"):
            fields["mortgagePenaltyRate114"] = penalty_rate

        principal_amount = fields.get("mortgagePrincipalAmount11")
        if principal_amount:
            fields["principalDebt"] = principal_amount
            fields.setdefault("principalDebt13", principal_amount)

        interest_amount = fields.get("mortgageInterestAmount12")
        if interest_amount:
            fields["interest"] = interest_amount
            fields.setdefault("interest14", interest_amount)

        creditor_name = fields.get("creditorName", "")
        if (
            not creditor_name
            or len(creditor_name) > 80
            or "имеет право" in creditor_name.lower()
            or "досрочного" in creditor_name.lower()
        ):
            new_creditor = self._extract_creditor_name_from_text(text)
            if new_creditor:
                fields["creditorName"] = new_creditor

        address = fields.get("applicantAddress")
        extended_address = self._extend_address_from_text(text, address)
        if extended_address:
            fields["applicantAddress"] = extended_address

    def _extract_mortgage_collateral_block(self, text: str) -> Optional[str]:
        """
        Пытается извлечь описание предмета залога для маркера [1221], даже если нет явных маркеров.
        Ищет текст после фраз о залоге или кредите.
        Возвращает строку с описанием (может содержать несколько предметов залога).
        """
        if not text:
            return None

        marker = "[1221]"
        marker_idx = text.find(marker)
        search_end = marker_idx if marker_idx != -1 else len(text)

        # Пытаемся найти предложение с описанием предмета залога
        # Вариант 1: После фразы о залоге "что подтверждается договором залога № ... от ... :"
        collateral_pattern1 = re.compile(
            r"что\s+подтверждается\s+договором\s+залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*",
            re.IGNORECASE | re.DOTALL
        )
        phrase_match = collateral_pattern1.search(text, 0, search_end)

        # Вариант 2: После фразы "В качестве обеспечения... что подтверждается договором залога"
        if not phrase_match:
            collateral_pattern2 = re.compile(
                r"В\s+качестве\s+обеспечения[^.]*?что\s+подтверждается\s+договором\s+залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*",
                re.IGNORECASE | re.DOTALL
            )
            phrase_match = collateral_pattern2.search(text, 0, search_end)

        # Вариант 3: После фразы "Кредит ... выдавался/предоставлялся ..."
        if not phrase_match:
            phrase_pattern = re.compile(
                r"кредит[^\n]{0,120}?(?:выдава[лс][ась]|предоставля[лс][ась]|предоставлен)[^:\n]*:\s*",
                re.IGNORECASE
            )
            phrase_match = phrase_pattern.search(text, 0, search_end)

        # Вариант 4: После фразы "предоставил в залог"
        if not phrase_match:
            collateral_pattern3 = re.compile(
                r"предоставил\s+в\s+залог[^:\n]*:\s*",
                re.IGNORECASE
            )
            phrase_match = collateral_pattern3.search(text, 0, search_end)

        if phrase_match:
            segment_start = phrase_match.end()
        else:
            # Если не нашли начало по фразам, ищем ближайший разрыв строки перед маркером
            prev_break = text.rfind("\n\n", 0, search_end)
            if prev_break == -1:
                prev_break = text.rfind('\n', 0, search_end)
            segment_start = prev_break if prev_break != -1 else max(0, search_end - 600)

        if segment_start >= search_end:
            return None

        segment = text[segment_start:search_end]

        # Ограничиваем блок следующими служебными абзацами/маркерами
        # Для залоговых заявлений также останавливаемся на "Наличие заложенного имущества"
        stop_pattern = re.search(
            r"\n{2,}(?=(?:По\s+состоянию|В\s+результате|ПРОСИТ|Просит|Суд|Определил|Установить|Взыскать|Сообщение|Кредитор|Должник|Наличие\s+заложенного))",
            segment,
            re.IGNORECASE
        )
        if stop_pattern:
            segment = segment[:stop_pattern.start()]

        # Также останавливаемся на фразе "Наличие заложенного имущества подтверждается выпиской из ЕГРН"
        stop_collateral = re.search(
            r"Наличие\s+заложенного\s+имущества\s+подтверждается\s+выпиской\s+из\s+ЕГРН",
            segment,
            re.IGNORECASE
        )
        if stop_collateral:
            segment = segment[:stop_collateral.start()]

        marker_inside = re.search(r"\[\d{1,4}\]", segment)
        if marker_inside:
            segment = segment[:marker_inside.start()]

        segment = segment.strip(" \n\r\t•-")
        if not segment or len(segment) < 10:
            return None

        # Не считаем залогом фразы вида "Кому выдана [ФИО]" — это указание получателя кредита/доверенности, не предмет залога
        if re.match(r"^Кому\s+выдана\s+[А-ЯЁа-яё\s]{5,80}", segment, re.IGNORECASE):
            return None
        if re.match(r"^[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+\.\.\.)?\s*$", segment.strip()) and "залог" not in segment.lower() and "недвижим" not in segment.lower() and "авто" not in segment.lower():
            return None

        segment = re.sub(r'\s{3,}', '\n\n', segment)
        segment = re.sub(r'[ \t]+', ' ', segment)

        return segment.strip()

    def _split_collateral_items(self, description: str) -> List[str]:
        """
        Разделяет описание предметов залога на отдельные предметы.

        ВАЖНО: по вашему описанию каждый предмет залога
        оформлен отдельной строкой (визуально — отдельный абзац).
        Поэтому правило максимально простое и предсказуемое:

        - каждая непустая строка = отдельный предмет залога.
        """
        if not description:
            return []

        # Нормализуем переводы строк (Windows / Unix)
        text = description.replace("\r\n", "\n").replace("\r", "\n")

        # Разбиваем на строки и считаем каждую непустую строку отдельным предметом
        raw_lines = [line.strip() for line in text.split("\n")]

        items: List[str] = [line for line in raw_lines if line and len(line) >= 10]

        # Если ничего не получилось, пробуем вернуть весь текст как один предмет
        if not items:
            cleaned = text.strip()
            if cleaned and len(cleaned) >= 10:
                items = [cleaned]

        logger.info(f"Разделено предметов залога (по строкам): {len(items)}")
        for i, item in enumerate(items):
            logger.info(f"  Предмет {i + 1}: {item[:100]}...")

        return items

    def _clean_court_name(self, value: str) -> str:
        """Очищает название суда от лишнего текста"""
        if not value:
            return value

        # Убираем лишние слова, которые не относятся к названию суда (обрезка хвоста)
        stop_words = [
            "возникает",
            "у конкурсного",
            "по денежным",
            "обязательствам",
            "с даты",
            "вступления",
            "в законную",
            "силу",
            "решения",
            "суда",
            "арбитражного",
            "или",
            "третейского",
            "о взыскании",
            "с должника",
            "денежных",
            "средств"
        ]

        value_lower = value.lower()
        for stop_word in stop_words:
            if stop_word in value_lower:
                # Обрезаем текст до первого вхождения стоп-слова
                idx = value_lower.find(stop_word)
                value = value[:idx].strip()
                break

        # Ограничиваем длину названия суда (обычно не более 100 символов)
        if len(value) > 100:
            # Пытаемся найти естественную границу (точка, запятая, или конец предложения)
            for delimiter in ['.', ',', '\n']:
                idx = value.find(delimiter)
                if 20 < idx < 100:
                    value = value[:idx].strip()
                    break
            else:
                # Если не нашли естественную границу, просто обрезаем до 100 символов
                value = value[:100].strip()

        return value.strip()



    def extract_legal_entity_short_name(self, text: Optional[str]) -> Optional[str]:
        """
        Извлекает краткое наименование юридического лица (без организационно-правовой формы).
        """
        if not text:
            return None

        normalized = self.clean_extracted_value(text)
        if not normalized:
            return None

        patterns = [
            r"(?:ООО|ОАО|ПАО|ЗАО|АО|Обществ[ао]\s+с\s+ограниченной\s+ответственностью)\s*[«\"]?([^«»\"\n,]+)",
            r"(?:компания\s+с\s+ограниченной\s+ответственностью)\s*[«\"]?([^«»\"\n,]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                short = match.group(1)
                return self.clean_extracted_value(short.strip('«»" '))

        return None


    def _entity_from_text(self, text: str) -> Optional[str]:
        """Тип должника КФХ/ИП из ТЕКСТА (для определений суда без блока «Должник:»).

        Смотрит описание должника СРАЗУ после «несостоятельным (банкротом) …» —
        там тип указан словами («индивидуального предпринимателя Главы КФХ …»).
        Возвращает только kfh/ip (legal не определяем по тексту — рядом часто
        стоит ЮЛ-кредитор, можно ошибиться).
        """
        if not text:
            return None
        m = re.search(
            r"несостоятельн\w*\s*\(?\s*банкрот\w*\s*\)?\s*([^\n.]{0,70})",
            text, re.IGNORECASE,
        )
        if not m:
            return None
        ctx = m.group(1).lower()
        if ("глав" in ctx and "кфх" in ctx) or "крестьянск" in ctx or "к(ф)х" in ctx:
            return "kfh"
        if "индивидуальн" in ctx and "предпринимател" in ctx:
            return "ip"
        return None

    # Канонический формат номера судебного дела. Структура:
    #   [опц. буква][цифры региона/типа][опц. буква] - [цифры номера] / ГОД
    # Покрывает все суды:
    #   • Арбитражные:  А53-2222/2024  (А=арбитражный, 53=регион, 2222=№, 2024=год)
    #   • СОЮ (гражд./угол./админ.): 2-1234/2024, 1-123/2024, 5-67/2024
    #   • КАС / апелляция / кассация (буква ПОСЛЕ цифры): 2а-1234/2024, 33а-456/2024
    # Обязательны дефис перед номером и «/ГОД» (19xx/20xx) в конце — это отсекает
    # доверенности (ЮЗБ/415-Д, ЮЗБ-РД/158-Д), договоры и прочие №… без года.
    _CASE_NUMBER_RE = re.compile(
        r"^[А-ЯA-Z]?\d{1,4}[А-ЯA-Z]?[-–]\d{1,15}/(?:19|20)\d{2}$"
    )

    def _is_valid_case_number(self, value: Optional[str]) -> bool:
        """True, если строка похожа на реальный номер судебного дела (любой суд)."""
        if not value:
            return False
        # Без учёта пробелов, регистра и Ё (буквы дел приводим к верхнему регистру)
        v = re.sub(r"\s+", "", str(value)).strip().upper().replace("Ё", "Е")
        return bool(self._CASE_NUMBER_RE.match(v))

    def _extract_prior_court_decision(self, text: str) -> Dict[str, Any]:
        """Распознаёт РАНЕЕ вынесенное решение ДРУГОГО суда (взыскание до банкротства).

        Пример: «…23.06.2025 Ворошиловским районным судом г.Ростова-на-Дону по делу
        №2-2523/2025 с должника взыскана сумма задолженности в размере ___» либо
        «Вступившим в законную силу решением … по делу №… взыскана …». Возвращает
        priorCourtName / priorCaseNumber / priorAmount / priorDecisionDate (что нашлось).
        Формулировка может отличаться — опираемся на якорь «по делу №<дело>» рядом со
        словами вступивш/вынесен/взыскан/решени.
        """
        if not text:
            return {}
        flat = re.sub(r"[ \t]+", " ", text)
        for m in re.finditer(r"по\s+делу\s*№\s*([А-ЯЁA-Z0-9/–\-]{3,30})", flat, re.IGNORECASE):
            case_raw = m.group(1).strip(" .,;")
            if not self._is_valid_case_number(case_raw):
                continue
            win = flat[max(0, m.start() - 220): min(len(flat), m.end() + 220)]
            win_low = win.lower()
            # Контекст должен говорить о ранее вынесенном/вступившем решении/взыскании.
            if not re.search(r"взыскан|вступивш|вынесен\w*\s+решени|решени\w+\s+суд", win_low):
                continue
            result: Dict[str, Any] = {"priorCaseNumber": case_raw}
            # Суд — фраза «[прилагательные] суд[падеж] [город/область]» БЛИЖАЙШАЯ
            # перед «по делу» (после «суд» может идти локация: «судом г.Ростова-на-Дону»,
            # «суда Ростовской области»).
            before = flat[max(0, m.start() - 160): m.start()]
            court_matches = list(re.finditer(
                r"((?:[А-ЯЁ][а-яё]+(?:им|ым|ого|ой|ом|ому|ыми)\s+){1,3}"
                r"суд(?:ом|а|е|у)?"
                r"(?:\s+(?:г\.?\s*[А-ЯЁ][А-Яа-яё\-]+|[А-ЯЁ][а-яё]+\s+(?:области|края|республики|округа|город\w*)))?)",
                before, re.IGNORECASE,
            ))
            if court_matches:
                court = re.sub(r"\s+", " ", court_matches[-1].group(1)).strip(" ,.;")
                if 5 <= len(court) <= 120:
                    result["priorCourtName"] = court
            # Сумма — «взыскан… в размере <сумма>» (может отсутствовать: «___»).
            am = re.search(
                r"взыскан\w*[^\n]{0,140}?в\s+размере\s*([0-9][0-9   .,]*)",
                win, re.IGNORECASE,
            )
            if am:
                v = self._fin_amount(am.group(1))
                if v > 0:
                    result["priorAmount"] = self._fin_fmt(v)
            # Госпошлина по ПРОШЛОМУ делу (если упомянута рядом с прежним решением).
            _gmoney = r"([0-9][0-9   .,]*)"
            gm = re.search(r"(?:госпошлин\w*|государственн\w+\s+пошлин\w*)[^\d]{0,40}?" + _gmoney + r"\s*(?:\[\d+\])?\s*руб", win, re.IGNORECASE)
            if not gm:
                gm = re.search(_gmoney + r"\s*(?:\[\d+\])?\s*руб[^\d]{0,40}?(?:госпошлин\w*|государственн\w+\s+пошлин\w*)", win, re.IGNORECASE)
            if gm:
                gv = self._fin_amount(gm.group(1))
                if gv > 0:
                    result["priorStateDuty"] = self._fin_fmt(gv)
            # Дата решения: приоритет дате ПЕРЕД судом/«по делу» (это дата решения,
            # а не дата кредитного договора, идущая дальше по тексту).
            dm = re.search(r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})", before)
            if not dm:
                dm = re.search(r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})", win)
            if dm:
                result["priorDecisionDate"] = dm.group(1).replace(",", ".")
            return result
        return {}


    def _apply_stacked_party_layout(self, fields: Dict[str, Any], text: str) -> None:
        """Формат ВТБ «реестр Nл»: метки сторон идут СТОПКОЙ, значения — ниже.

        Шапка выглядит так:
            КРЕДИТОР:
            ДОЛЖНИК:
            ФИНАНСОВЫЙ
            УПРАВЛЯЮЩИЙ:
            Банк ВТБ (ПАО) … ОГРН … ИНН …            ← значение КРЕДИТОРА
            Горина Юлия Игоревна … ИНН … адрес …      ← значение ДОЛЖНИКА
            Удодов Сергей Александрович (ИНН …)        ← значение УПРАВЛЯЮЩЕГО

        Обычный построчный разбор берёт метку «ФИНАНСОВЫЙ» за ФИО должника и
        реквизиты банка — за должника. Здесь переустанавливаем стороны по порядку.
        """
        if not text:
            return
        sig = re.search(
            r"КРЕДИТОР\s*:\s*\n\s*ДОЛЖНИК\s*:\s*\n\s*ФИНАНСОВ\w*\s*\n?\s*УПРАВЛЯЮЩ\w*\s*:",
            text, re.IGNORECASE,
        )
        if not sig:
            return
        region = text[sig.end():]
        cut = re.search(r"РАЗМЕР\s+ТРЕБОВАНИЙ|\bдело\s*№|\bЗАЯВЛЕНИЕ\b", region, re.IGNORECASE)
        if cut:
            region = region[:cut.start()]

        # ФИО физлиц на отдельных строках — это начала блоков ДОЛЖНИК и УПРАВЛЯЮЩИЙ
        # (кредитор-юрлицо идёт первым, до первого ФИО).
        # ФИО физлица в начале строки; после него допускается «(ИНН …)» или
        # конец строки («Тимченко Павел Иванович (ИНН …)» и «Анисимов Роман Сергеевич»).
        fio_re = re.compile(
            r"(?m)^[ \t]*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)[ \t]*(?=\(|\n|$)"
        )
        fios = list(fio_re.finditer(region))
        if len(fios) < 2:
            return

        cred_block = region[: fios[0].start()]
        debtor_block = region[fios[0].start(): fios[1].start()]
        manager_block = region[fios[1].start():]

        def _inn(s):
            m = re.search(r"ИНН[:\s]*([0-9]{10,12})\b", s)
            return m.group(1) if m else None

        def _ogrn(s):
            m = re.search(r"ОГРН[:\s]*([0-9]{13,15})\b", s)
            return m.group(1) if m else None

        # --- КРЕДИТОР (юрлицо) ---
        cred_name = ""
        for ln in cred_block.splitlines():
            ln = ln.strip()
            if ln:
                cred_name = re.split(r"\s*-{3,}|\bОГРН\b|\bИНН\b", ln)[0].strip()
                break
        if cred_name:
            fields["creditorName"] = cred_name
        if _inn(cred_block):
            fields["creditorInn"] = _inn(cred_block)
        if _ogrn(cred_block):
            fields["creditorOgrn"] = _ogrn(cred_block)
        ca = re.search(
            r"(?:Юридическ\w*\s+адрес|адрес)[:\s]*\n?\s*([0-9]{6}[^\n]+)",
            cred_block, re.IGNORECASE,
        )
        if ca:
            fields["creditorAddress"] = ca.group(1).strip()

        # --- ДОЛЖНИК (физлицо) ---
        fields["applicantName"] = fios[0].group(1).strip()
        fields["entityType"] = "individual"
        fields.pop("companyInn", None)
        fields.pop("ogrn", None)
        if _inn(debtor_block):
            fields["inn"] = _inn(debtor_block)
        bd = re.search(
            r"Дата\s+рождения[:\s]*([0-3]?\d[.,][01]?\d[.,]\d{4})",
            debtor_block, re.IGNORECASE,
        )
        if bd:
            fields["birthDate"] = bd.group(1).replace(",", ".")
        bp = re.search(r"Место\s+рождения[:\s]*([^\n]+)", debtor_block, re.IGNORECASE)
        if bp:
            fields["birthPlace"] = bp.group(1).strip().rstrip(" .,;")
        # Адрес должника может быть и без индекса («Ростовская обл., г. Шахты, …»),
        # и многострочным — берём всё после метки «Адрес …:» до конца блока.
        da = re.search(
            r"Адрес\s+(?:регистрации|проживания|места\s+жительства)?\s*:\s*([\s\S]+)",
            debtor_block, re.IGNORECASE,
        )
        if da:
            addr = re.sub(r"\s+", " ", da.group(1)).strip().rstrip(" ,;")
            addr = re.split(r"\b(?:ИНН|ОГРН|СНИЛС|КПП)\b", addr, flags=re.IGNORECASE)[0].strip().rstrip(" ,;")
            if re.search(r"[А-Яа-яЁё]{3}", addr):
                fields["applicantAddress"] = addr

        # --- ФИНАНСОВЫЙ УПРАВЛЯЮЩИЙ (физлицо) ---
        fields["managerName"] = fios[1].group(1).strip()
        if _inn(manager_block):
            fields["managerInn"] = _inn(manager_block)
        ma = re.search(r"(\b\d{6}\b\s*,[^\n]+(?:\n[^\n]+)?)", manager_block)
        if ma:
            addr = re.sub(r"\s*\n\s*", " ", ma.group(1)).strip().rstrip(" ,;")
            addr = re.sub(r"\s*-{3,}\s*", " ", addr).strip()
            fields["managerAddress"] = addr
        else:
            # Иначе остаётся мусор от общего разбора («…609391, ИНН 7702070139»).
            fields.pop("managerAddress", None)
        logger.info(
            "Раскладка ВТБ (метки стопкой): должник=%s, кредитор=%s, управляющий=%s"
            % (fields.get("applicantName"), fields.get("creditorName"), fields.get("managerName"))
        )

    _STACKED_SIG_RE = re.compile(
        r"КРЕДИТОР\s*:\s*\n\s*ДОЛЖНИК\s*:\s*\n\s*ФИНАНСОВ\w*\s*\n?\s*УПРАВЛЯЮЩ\w*\s*:",
        re.IGNORECASE,
    )

    def _fix_truncated_creditor_name(self, fields: Dict[str, Any], text: str) -> None:
        """Имя кредитора, обрезанное переносом строки внутри названия
        («Публичное Акционерное Общество "МТС-\\nБанк"»), дотягиваем по тексту до
        закрывающей кавычки."""
        name = fields.get("creditorName")
        if not name or not text:
            return
        base = name.rstrip()
        # Триггер: имя кончается дефисом или открытой (непарной) кавычкой.
        unbalanced = base.count('"') % 2 == 1 or base.count("«") > base.count("»")
        if not (base.endswith("-") or unbalanced):
            return
        m = re.search(re.escape(base) + r"\s*\n?\s*([A-Za-zА-Яа-яЁё][^\n]*?[»\"])", text)
        if not m:
            return
        tail = m.group(1).strip()
        joiner = "" if base.endswith("-") else " "
        fixed = re.sub(r"\s+", " ", (base + joiner + tail)).strip()
        fields["creditorName"] = fixed

    def _apply_table_breakdown_finances(self, fields: Dict[str, Any], text: str) -> None:
        """Табличная разбивка задолженности: столбцы «Структура задолженности |
        Значение | RUR» по одному/нескольким договорам (значения суммируются).
        Гейт по сигнатуре таблицы; валидация суммы компонентов = «ОБЩАЯ
        ЗАДОЛЖЕННОСТЬ»/итог, иначе ничего не перекрываем."""
        if not text:
            return
        low = text.lower()
        if "структура" not in low or "rur" not in low:
            return
        tm = re.search(
            r"ОБЩАЯ\s+ЗАДОЛЖЕННОСТЬ[:\s]*(\d[\d   ]*(?:[.,]\d{1,2})?)",
            text, re.IGNORECASE,
        )
        if not tm:
            return
        total = self._fin_amount(tm.group(1))
        if total <= 0:
            return
        money = r"(\d[\d   ]*(?:[.,]\d{1,2})?)"
        pr = it = fo = pen = ld = 0.0
        n = 0
        seen = set()  # таблица в тексте бывает задвоена — дедуп по (категория, значение)
        for m in re.finditer(
            r"(основн\w*\s+долг\w*|процент\w*|неустойк\w*|\bпени\b|штраф\w*|госпошлин\w*)"
            r"\s*\n\s*" + money + r"\s*\n?\s*(?:RUR|руб)",
            text, re.IGNORECASE,
        ):
            cat = m.group(1).lower()
            val = self._fin_amount(m.group(2))
            if val <= 0:
                continue
            _grp = ("forfeit" if ("неустой" in cat or "пени" in cat)
                    else "penalty" if "штраф" in cat
                    else "interest" if "процент" in cat
                    else "loan_duty" if "госпошл" in cat
                    else "principal")
            if (_grp, round(val, 2)) in seen:
                continue
            seen.add((_grp, round(val, 2)))
            if "штраф" in cat:
                pen += val
            elif "неустой" in cat or "пени" in cat:
                fo += val
            elif "процент" in cat:
                it += val
            elif "госпошл" in cat:
                ld += val
            else:
                pr += val
            n += 1
        comp = pr + it + fo + pen + ld
        if n == 0 or abs(comp - total) > 1.5:
            return
        fields["principalDebt"] = self._fin_fmt(pr)
        fields["principalDebt13"] = fields["principalDebt"]
        fields["interest"] = self._fin_fmt(it)
        fields["interest14"] = fields["interest"]
        fields["forfeit"] = self._fin_fmt(fo)
        fields["forfeit15"] = fields["forfeit"]
        fields["penalties"] = self._fin_fmt(pen)
        if ld > 0:
            fields["loanStateDuty17"] = self._fin_fmt(ld)
        fields["totalDebt"] = self._fin_fmt(total)
        fields["debtAmount"] = fields["totalDebt"]
        # Банкротная госпошлина — «Взыскать … в размере NN (прописью) рублей».
        gm = re.search(
            r"(?:гос)?пошлин\w*[^\d]{0,120}?в\s*размере\s*" + money + r"\s*(?:\([^)]*\))?\s*руб",
            text, re.IGNORECASE,
        )
        if gm:
            duty = self._fin_fmt(self._fin_amount(gm.group(1)))
            fields["stateDuty16"] = duty
            fields["stateDuty"] = duty
        logger.info(
            "Финансы из таблицы: осн=%s проц=%s неуст=%s ссуд.гп=%s итог=%s"
            % (fields["principalDebt"], fields["interest"], fields["forfeit"],
               fields.get("loanStateDuty17"), fields["totalDebt"])
        )

    def _clear_garbage_bankruptcy_duty(self, fields: Dict[str, Any]) -> None:
        """Банкротная госпошлина [16], совпавшая с итогом/осн.долгом — это мусор
        (отдельной банкротной госпошлины в документе нет). Удаляем поле."""
        amt = self._fin_amount
        bankr = amt(fields.get("stateDuty16") or fields.get("stateDuty"))
        if bankr <= 0:
            return
        total = amt(fields.get("totalDebt") or fields.get("debtAmount"))
        principal = amt(fields.get("principalDebt") or fields.get("principalDebt13"))
        if (total > 0 and abs(bankr - total) < 1) or (principal > 0 and abs(bankr - principal) < 1):
            fields.pop("stateDuty16", None)
            fields.pop("stateDuty", None)
            logger.info("Удалена мусорная банкротная госпошлина (совпала с итогом/осн.долгом)")

    def _fill_creditor_nlp(self, fields: Dict[str, Any], text: str) -> None:
        """Второстепенная NLP-сеть для кредитора: срабатывает ТОЛЬКО когда основной
        label-anchored парсер и реестр не дали имени. Берём из NER первую организацию
        по шапке, отсекая суд/должника и требуя признак организации (ОПФ/кавычки/
        налоговый орган). Роль (это кредитор) задаёт позиция-шапка, а не сам NER.
        Verbatim-срез обеспечивает `find_orgs`. Цель — не «сломаться» на незнакомой
        раскладке будущих документов, где нет привычной метки «Кредитор:/Заявитель:»."""
        if not text or (fields.get("creditorName") or "").strip():
            return
        for cand in _nlp.find_orgs(text[:1200]):
            low = cand.lower()
            # Отсев суда и явного не-кредитора.
            if re.search(r"\bсуд\b|арбитражн\w+\s+суд", low):
                continue
            # Признак организации: ОПФ / банк / налоговый орган / кавычки-название.
            looks_org = bool(re.search(
                r"\b(?:ООО|АО|ПАО|ЗАО|ОАО|ПКО|НАО|Банк)\b|банк|общество|"
                r"налогов|ифнс|\bфнс\b|инспекц|служб|[«\"]",
                cand, re.IGNORECASE))
            if looks_org and 3 < len(cand) < 150:
                fields["creditorName"] = cand
                return

    # Регион в любом регистре: «Ростовской области», «Республике Башкортостан»,
    # «ПО РОСТОВСКОЙ ОБЛАСТИ» и т.п. Нормализуется в _norm_fns_region.
    _FNS_REGION = (r"(?:Республик\w+\s+[А-Яа-яЁё][А-Яа-яЁё-]+|"
                   r"[А-Яа-яЁё]+(?:ой|ому)\s+(?:области|краю|округу|АО))")

    @staticmethod
    def _norm_fns_region(region: str) -> str:
        """ЗАГЛАВНЫЙ/смешанный регион → канонический вид: «РОСТОВСКОЙ ОБЛАСТИ» →
        «Ростовской области», «РЕСПУБЛИКЕ БАШКОРТОСТАН» → «Республике Башкортостан».
        Гео-тип (области/краю/округу) со строчной, названия — с заглавной."""
        lower_words = {"области", "краю", "округу", "ао", "автономному"}
        out = []
        for w in re.sub(r"\s+", " ", region).strip().split(" "):
            out.append(w.lower() if w.lower() in lower_words else w[:1].upper() + w[1:].lower())
        return " ".join(out)

    def _build_fns_creditor(self, text: str) -> str:
        """Имя налогового органа по слоям шаблонов (приоритет — конкретной инспекции).

        Слои (первый сработавший): 1) «в лице Межрайонной ИФНС России № N по <регион>»;
        2) скобка «(Межрайонная ИФНС России № N по <регион>)»; 3) заглавная полная форма
        «МЕЖРАЙОННАЯ ИНСПЕКЦИЯ ФНС № N ПО <РЕГИОН>»; 4) управление «УФНС/УПРАВЛЕНИЕ ФНС
        по <регион>». Если ни один — общий «ФНС России» (безопасная деградация, не мусор).
        Возвращает всегда verbatim-нормализованное юр-имя.
        """
        rg = self._FNS_REGION
        # Слои с конкретной инспекцией: (№ инспекции, регион).
        insp_layers = [
            rf"в\s+лице\s+Межрайонн\w+\s+ИФНС\s+России\s+№?\s*(\d+)\s+по\s+({rg})",
            rf"\(\s*Межрайонн\w+\s+ИФНС\s+России\s+№?\s*(\d+)\s+по\s+({rg})\s*\)",
            rf"Межрайонн\w+\s+инспекци\w+\s+федеральн\w+\s+налогов\w+\s+служб\w+"
            rf"\s+№?\s*(\d+)\s+по\s+({rg})",
        ]
        for pat in insp_layers:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return (f"ФНС России в лице Межрайонной ИФНС России № {m.group(1)} "
                        f"по {self._norm_fns_region(m.group(2))}")
        # Уровень управления по субъекту (без номера инспекции).
        for pat in (rf"УФНС\s+России\s+по\s+({rg})",
                    rf"управлени\w+\s+федеральн\w+\s+налогов\w+\s+служб\w+\s+по\s+({rg})"):
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return f"ФНС России в лице УФНС России по {self._norm_fns_region(m.group(1))}"
        return "ФНС России"

    def _apply_fns_authority(self, fields: Dict[str, Any], text: str) -> None:
        """Заявления уполномоченного органа (ФНС) о банкротстве/включении в РТК.

        В таких заявлениях кредитор и заявитель — налоговый орган (ФНС России /
        Межрайонная ИФНС), указанный в шапке-бланке БЕЗ метки «Кредитор:/Заявитель:»,
        поэтому общий label-anchored парсер его не берёт, а заявителем ошибочно
        становится должник-физлицо (из «…требований кредитора … <ФИО должника>»).
        Детектор срабатывает ТОЛЬКО при бланке ФНС в шапке; должника не трогает.
        """
        if not text:
            return
        # Признак заявления ФНС — налоговый БЛАНК в самом начале (первые ~400 симв.),
        # а не упоминание закона/органа в теле: «…ФЕДЕРАЛЬНАЯ НАЛОГОВАЯ СЛУЖБА…» или
        # заголовок «Заявление уполномоченного органа …». Тело («Федерального закона»,
        # «требования … уполномоченного органа») сигналом НЕ считаем.
        if not (
            re.search(r"НАЛОГОВ\w+\s+СЛУЖБ", text[:400], re.IGNORECASE)
            or re.search(r"ЗАЯВЛЕНИ\w+\s+УПОЛНОМОЧЕНН\w+\s+ОРГАН", text[:700], re.IGNORECASE)
        ):
            return
        # Не трогаем заявления с уже распознанным кредитором-компанией (банк/ООО/АО…):
        # налоговый бланк мог оказаться штампом суда, а кредитор — реальная организация.
        # ОПФ по границе слова (не подстрокой: «банк» ⊂ «банкротстве» давало ложняк).
        _OPF = r"\b(?:ООО|АО|ПАО|ЗАО|ОАО|ПКО|НАО|Банк)\b"
        cur_cred = fields.get("creditorName") or ""
        if "фнс" not in cur_cred.lower() and re.search(_OPF, cur_cred, re.IGNORECASE):
            return

        # Имя налогового органа собираем слоями (см. _build_fns_creditor); если ни
        # один шаблон инспекции/управления не сработал — безопасный общий «ФНС России».
        creditor = self._build_fns_creditor(text)

        # Кредитор: ставим налоговый орган, если он ещё не распознан как ФНС; либо
        # АПГРЕЙДИМ короткое «ФНС России» до полной формы «…в лице Межрайонной ИФНС
        # № N по <регион>», когда инспекция найдена (единообразие всех ФНС-заявлений).
        built_full = "в лице" in creditor.lower()
        if "фнс" not in cur_cred.lower() or (built_full and "в лице" not in cur_cred.lower()):
            fields["creditorName"] = creditor
        cred_now = fields.get("creditorName") or ""
        # ДОЛЖНИК остаётся в applicant* — генератор акта берёт эти поля как ДОЛЖНИКА
        # (applicantNameDative = «…требований кредиторов ДОЛЖНИКА»). ФНС держим ТОЛЬКО
        # в creditor*. Если общий парсер/ранняя версия затёрли applicantName на ФНС
        # (или пусто), а debtorName — физлицо, восстанавливаем должника в applicantName
        # и ПЕРЕСЧИТЫВАЕМ падежи под него: иначе в акт уйдёт «должник = ФНС», а часть
        # падежей окажется смешанной («ФНС Россию» в винительном при физлице в родительном).
        appl = fields.get("applicantName") or ""
        debt_name = (fields.get("debtorName") or "").strip()
        if (debt_name and debt_name != appl and "фнс" not in debt_name.lower()
                and is_person_name(debt_name)):
            fields["applicantName"] = debt_name
            base = re.sub(self._NAME_PREFIX_RE, "", debt_name, flags=re.IGNORECASE).strip() or debt_name
            for case_key, conv in (
                ("applicantNameGenitive", self._convert_name_to_genitive),
                ("applicantNameDative", self._convert_name_to_dative),
                ("applicantNameAccusative", self._convert_name_to_accusative),
                ("applicantNameInstrumental", self._convert_name_to_instrumental),
            ):
                try:
                    fields[case_key] = conv(base) or debt_name
                except Exception:
                    fields[case_key] = debt_name
        # Адреса ФНС-заявления. У заявителя-ФНС нет метки «Адрес:», поэтому общий
        # парсер кладёт в applicantAddress адрес ДОЛЖНИКА (или суда) — разводим их:
        #   • debtorAddress ← «Должник … Адрес: …», иначе — из applicantAddress (общий
        #     парсер часто кладёт туда именно адрес должника);
        #   • applicantAddress ← юр-адрес инспекции из шапки (перед Телефон/www.nalog).
        _STREET = r"ул|пр\.|просп|проспект|пер|переул|д\.|дом|улиц|ст-ца|стан|мкр|кв\."

        def _clean_addr(s: str) -> str:
            s = re.sub(r"\s+", " ", s).strip(" ,;")
            return re.split(r"\b(?:ИНН|ОГРН|ОГРНИП|СНИЛС|КПП)\b", s, flags=re.IGNORECASE)[0].strip(" ,;")

        debt_addr = None
        dm = re.search(
            r"Должник\w*[:\s][\s\S]{0,90}?\bАдрес[:\s]*([0-9А-ЯЁ][^\n]+)",
            text, re.IGNORECASE,
        )
        # Без метки «Адрес» адрес должника в бланке ФНС идёт голой строкой/фрагментом
        # с индексом в блоке под меткой «Должник:». Индекс может стоять в начале строки
        # (Чернов: «…ИНН …\n346414, Ростовская обл…Харьковская ул,47») или в одну строку
        # после «ФИО ИНН ОГРНИП» (Зайцев: «…ОГРНИП 318… 346630, РОСТОВСКАЯ ОБЛ…ЛЕВЧЕНКО
        # ПЛ,46»). Якоримся на метку «Должник:» с ДВОЕТОЧИЕМ (а не на слово «должника»
        # в тексте) и берём первый индекс-адрес в пределах 200 символов после неё.
        dm_bare = None
        if not dm:
            dm_bare = re.search(
                r"Должник\w*\s*:\s*[\s\S]{0,200}?(\d{6}\s*,\s*[А-ЯЁ][^\n]+)",
                text, re.IGNORECASE,
            )
        # ВАЛИДАТОР: принятое значение должно ВЫГЛЯДЕТЬ как адрес, а не как набор слов /
        # фрагмент закона. Так regex, случайно поймавший прозу («…руководствуясь ст. 71,
        # приложены к заявлению…»), отбраковывается и уступает место сети/пустому
        # значению. Признак адреса: индекс ИЛИ уличный маркер + наличие цифры; при этом
        # нет юридической прозы (стоп-слова заявления). Пусто лучше мусора.
        def _is_addr(s: str) -> bool:
            s = (s or "").strip()
            if not (8 <= len(s) <= 160) or not re.search(r"\d", s):
                return False
            # Стоп-слова заявления: если есть — это проза, а не адрес.
            if re.search(r"руководству|федеральн\w+\s+закон|уведомл|задолженност|приложен|"
                         r"направлен|уплач|несостоятельн|банкротств|\bстать\w+|\bст\.?\s*\d",
                         s, re.IGNORECASE):
                return False
            # 1) Почтовый индекс — однозначный признак адреса (покрывает большинство).
            if re.search(r"\b\d{6}\b", s):
                return True
            # 2) Тип адресного объекта из ШИРОКОГО спектра (улицы/площади/наб/шоссе/туп/
            #    аллея/линия/проезд/тракт/квартал/мкр + типы НП). Все токены ≥2 симв. и
            #    адресо-специфичны, поэтому в прозе почти не встречаются; форма «тип
            #    Название, Номер» ловится (номер не обязан примыкать к типу).
            if re.search(r"\b(?:ул|улиц\w*|пер|переул\w*|пр-кт|пр-т|просп\w*|проспект|б-р|"
                         r"бульвар|наб|набережн\w*|пл|площад\w*|шоссе|туп|тупик|алле\w*|"
                         r"лини\w*|проезд|тракт|кв-л|квартал|мкр|микрорайон|городок|"
                         r"пос|пос[её]лок|село|сельсовет|деревн\w*|станиц\w*|ст-ца|хутор|"
                         r"аул|слобод\w*|город|гор|пгт|снт|днп)\b", s, re.IGNORECASE):
                return True
            # 3) Дом/строение/корпус/квартира с номером вплотную («д. 5», «дом 14»,
            #    «стр 3», «кв. 43») — адресный хвост без явного типа улицы/НП.
            return bool(re.search(r"\b(?:д|дом|влд|владени\w*|стр|строени\w*|корп|корпус|к|кв|"
                                  r"уч|участок)\b\.?\s*\d", s, re.IGNORECASE))

        cur_aa = (fields.get("applicantAddress") or "").strip()
        cand = None
        if dm:
            cand = _clean_addr(dm.group(1))
        elif dm_bare:
            cand = _clean_addr(dm_bare.group(1))
        if cand and _is_addr(cand):
            debt_addr = cand
        # ПОДСТРАХОВКА (гибрид): regex промахнулся ИЛИ вернул не-адрес → достаём адрес
        # морфологически через Natasha AddrExtractor из окна блока «Должник:». Работает
        # независимо от раскладки (индекс в начале строки / после ОГРНИП / без метки),
        # т.е. страхует от невиданных макетов — чего конечным числом регулярок не выразить.
        if not debt_addr:
            _dblk = re.search(r"Должник\w*\s*:", text, re.IGNORECASE)
            if _dblk:
                nat = _nlp.complete_address(text[_dblk.end(): _dblk.end() + 300])
                if nat:
                    nat = _clean_addr(nat)
                    if _is_addr(nat):
                        debt_addr = nat
        if (not debt_addr and cur_aa and re.search(r"\b\d{6}\b", cur_aa)
                and re.search(_STREET, cur_aa, re.IGNORECASE)
                and not re.search(r"Неглинн|Станиславског", cur_aa, re.IGNORECASE)):
            # Метки «Должник Адрес:» нет, но в applicantAddress лежит адрес с улицей и
            # индексом (не центральный ФНС, не суд) — это фактически адрес должника.
            debt_addr = cur_aa
        if debt_addr and not (fields.get("debtorAddress") or "").strip():
            fields["debtorAddress"] = debt_addr

        # НОВОЕ (справочник ФНС): выверенный юр-адрес КРЕДИТОРА в блок «Данные о
        # кредиторе» → поле creditorAddress. Заполняем ТОЛЬКО его и ТОЛЬКО когда
        # кредитор — налоговый орган; адресов заявителя/должника не касаемся (иначе
        # юр-адрес инспекции подмешивается в адрес должника). Справочник fns_registry
        # находит адрес по имени органа — он инвариантен к тому, как оформлена шапка
        # конкретного заявления (и работает, даже если адреса в шапке нет).
        # Подсказка для дизамбигуации ТОРМ (один № инспекции обслуживает несколько
        # городов): шапка ДО блока «Должник», чтобы город/индекс инспекции не спутать
        # с городом должника — реестр выберет кандидата по городу/индексу из шапки.
        if "фнс" in (cred_now or "").lower():
            _dpos = re.search(r"Должник", text, re.IGNORECASE)
            _hint = text[: _dpos.start()] if _dpos else text[:1800]
            reg_addr = None
            try:
                reg_addr = _fns_reg.resolve_address(cred_now, _hint)
            except Exception as exc:  # справочник недоступен — тихо пропускаем
                logger.warning(f"Реестр ФНС не ответил: {exc}")
            if reg_addr:
                fields["creditorAddress"] = reg_addr

        # applicantAddress — это АДРЕС ДОЛЖНИКА (генератор берёт его как адрес должника;
        # юр-адрес ФНС живёт в creditorAddress). Ставим сюда адрес должника; если он не
        # извлёкся — вычищаем из applicantAddress чужое (адрес ФНС/суда/проза или совпадение
        # с юр-адресом ФНС), чтобы в акт не попал адрес инспекции как адрес должника.
        if debt_addr:
            fields["applicantAddress"] = debt_addr
        else:
            aa = (fields.get("applicantAddress") or "").strip()
            creda = (fields.get("creditorAddress") or "").strip()
            if aa and (not _is_addr(aa) or (creda and aa == creda)
                       or re.search(r"Неглинн|Станиславског|www\.nalog|Адрес\s+для", aa, re.IGNORECASE)):
                fields.pop("applicantAddress", None)

    def _resolve_manager_sro(self, fields: Dict[str, Any], text: str) -> None:
        """Сопоставляет извлечённое упоминание СРО (`sroName`) с реестром (`sro_data`)
        и заменяет его каноничным полным именем (NAIM_FULL). Работает только когда
        `sroName` уже извлечён основным парсером и уверенно опознан в реестре; иначе
        поле не трогаем (не изобретаем СРО из общего текста, чтобы не плодить ложные)."""
        from sro_registry import resolve_sro

        full = resolve_sro(fields.get("sroName"))
        if full:
            fields["sroName"] = full

    def _fill_manager_address(self, fields: Dict[str, Any], text: str) -> None:
        """Фолбэк адреса управляющего: «… управляющий: <ФИО, м.б. в 2 строки>
        Адрес регистрации: <многострочный адрес>». Срабатывает только если адрес
        ещё не найден; схлопывает переносы строк и обрезает реквизиты."""
        if not text:
            return
        # Уже есть нормальный адрес (с индексом и без реквизитов) — не трогаем.
        _ex = fields.get("managerAddress")
        if _ex and re.search(r"\b\d{6}\b", _ex) and not re.search(r"\b(?:ИНН|СНИЛС|ОГРН|КПП)\b", _ex, re.IGNORECASE):
            return
        m = re.search(
            r"(?:финансов\w+|временн\w+|конкурсн\w+|арбитражн\w+)\s+управляющ\w+"
            r"[\s\S]{0,80}?адрес\s+регистрации[:\s]*([0-9]{6}[\s\S]{0,160}?)"
            r"(?=\n\s*(?:Дело|Тел|Исх|ЗАЯВЛЕНИЕ|ИНН|ОГРН|СНИЛС|№)|\n\s*\n|$)",
            text, re.IGNORECASE,
        )
        if not m:
            # Без метки «Адрес регистрации»: адрес-индекс сразу после реквизитов
            # управляющего («…управляющий: ФИО ИНН… СНИЛС…\n350012, …»).
            m = re.search(
                r"(?:финансов\w+|временн\w+|конкурсн\w+|арбитражн\w+)\s+управляющ\w+"
                r"[\s\S]{0,120}?СНИЛС[^\n]*\n\s*([0-9]{6}[\s\S]{0,140}?)"
                r"(?=\n\s*(?:Реквизиты|Дело|Тел|Исх|ЗАЯВЛЕНИЕ|ИНН|ОГРН|№|член)|\n\s*\n|$)",
                text, re.IGNORECASE,
            )
        if not m and (fields.get("managerName") or "").strip():
            # Простая метка «Адрес:» после якоря «…управляющий: <ФИО>» —
            # ФИО может переноситься на 2 строки (word-wrap docx), поэтому между
            # якорем и меткой допускаем окно из нескольких строк. Метка должна
            # стоять в НАЧАЛЕ строки — иначе цепляем «Почтовый/Электронный адрес»
            # контактов банка (форма Сбербанка «Финансовых управляющих: … Почтовый
            # адрес: …»). Гейт по managerName: без названного управляющего адрес
            # ему не принадлежит.
            m = re.search(
                r"(?:финансов\w+|временн\w+|конкурсн\w+|арбитражн\w+)\s+управляющ\w+"
                r"[:\s]*[\s\S]{0,120}?(?:^|\n)\s*адрес[^:\n]*:\s*([0-9]{6}[\s\S]{0,160}?)"
                r"(?=\n\s*(?:Дело|Тел|Исх|ЗАЯВЛЕНИЕ|ИНН|ОГРН|СНИЛС|№|Размер|Государственн)|\n\s*\n|$)",
                text, re.IGNORECASE | re.MULTILINE,
            )
        if not m:
            return
        addr = re.sub(r"\s+", " ", m.group(1)).strip()
        addr = re.split(r"\b(?:ИНН|ОГРН|ОГРНИП|СНИЛС|КПП)\b", addr, flags=re.IGNORECASE)[0]
        addr = addr.strip().rstrip(" ,;")
        if re.search(r"[А-Яа-яЁё]{3}", addr):
            fields["managerAddress"] = addr

    # Метка → (якорь роли, стоп-метки других сторон) для NLP-достройки адреса.
    # Окно берём ПОСЛЕ якоря и ОБРЫВАЕМ на метке следующей стороны — иначе окно
    # перепрыгивает через контакты роли (напр. «Адрес для корреспонденции: email»)
    # в блок другой стороны и хватает чужой адрес (адрес должника вместо управляющего).
    _ADDR_ROLE_ANCHORS = (
        ("managerAddress",
         r"(?:финансов\w+|временн\w+|конкурсн\w+|арбитражн\w+)\s+управляющ\w+",
         r"Должник|Кредитор|Заявител|Ответчик|Взыскател|Третье\s+лицо|ЗАЯВЛЕНИЕ|Требование|Дело\s*№|В\s+производств"),
        ("applicantAddress",
         r"Заявител\w+\s*[:\-]",
         r"Должник|Кредитор|управляющ|Ответчик|Взыскател|Третье\s+лицо|ЗАЯВЛЕНИЕ|Требование|Дело\s*№|В\s+производств"),
    )

    def _refine_addresses_nlp(self, fields: Dict[str, Any], text: str) -> None:
        """Второстепенный слой: Natasha достраивает адрес по окну роли.

        Срабатывает КОНСЕРВАТИВНО, чтобы не портить рабочий regex:
        - поле пустое → заполняем адресом из окна роли;
        - поле есть, но обрезано → заменяем ТОЛЬКО если кандидат Natasha строго
          длиннее и текущее значение — его префикс (тогда не теряем нестандартный
          хвост «а/я»/литеру, который AddrExtractor склонен отбрасывать).
        Роль/принадлежность определяет якорь-метка, не NER. VERBATIM-срез исходного
        текста обеспечивает сам `complete_address`.
        """
        if not text:
            return

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", s or "").strip().lower()

        for field, anchor, stop in self._ADDR_ROLE_ANCHORS:
            # Адрес управляющего заполняем ТОЛЬКО при названном управляющем: в
            # заявлениях о признании банкротом управляющий ещё не назначен, а
            # «финансового управляющего … адрес: …» указывает на адрес СРО
            # (из числа членов которой его утвердят) — это НЕ адрес управляющего.
            if field == "managerAddress" and not (fields.get("managerName") or "").strip():
                continue
            am = re.search(anchor, text, re.IGNORECASE)
            if not am:
                continue
            # Окно роли: до 400 символов после якоря, обрываем на пустой строке
            # и на метке следующей стороны (чтобы не захватить чужой адрес).
            win = text[am.end():am.end() + 400]
            win = re.split(r"\n\s*\n", win, maxsplit=1)[0]
            sm = re.search(stop, win, re.IGNORECASE)
            if sm:
                win = win[:sm.start()]
            cand = _nlp.complete_address(win)
            if not cand:
                continue
            cand = re.sub(r"\s+", " ", cand).strip()  # схлопываем переносы внутри адреса
            # Гейт полноты: AddrExtractor склонен обрезать хвост (а/я/индекс), а
            # расплывчатый «регион, город» без дома/индекса нарушает принцип «текст
            # как в документе». Заполняем только достаточно конкретным адресом.
            if not re.search(r"\b\d{6}\b", cand) and not re.search(r"\bд\.?\s*\d", cand, re.IGNORECASE):
                continue
            cur = (fields.get(field) or "").strip()
            if not cur:
                fields[field] = cand
            elif len(_norm(cand)) > len(_norm(cur)) and _norm(cand).startswith(_norm(cur)):
                fields[field] = cand

    def _sanitize_address_fields(self, fields: Dict[str, Any]) -> None:
        """Адресные поля не должны содержать реквизиты (ИНН/ОГРН/ОГРНИП/СНИЛС/КПП):
        обрезаем хвост по первому такому маркеру; если осмысленного адреса (букв)
        не осталось — поле было мусором, удаляем."""
        for k in ("applicantAddress", "creditorAddress", "managerAddress",
                  "thirdPartyAddress", "debtorAddress"):
            v = fields.get(k)
            if not v or not isinstance(v, str):
                continue
            cleaned = re.split(
                r"\b(?:ИНН|ОГРНИП|ОГРН|СНИЛС|КПП)\b", v, flags=re.IGNORECASE
            )[0].strip().rstrip(" ,;-")
            if not re.search(r"[А-Яа-яЁё]{3}", cleaned):
                fields.pop(k, None)
            elif cleaned != v:
                fields[k] = cleaned

    def _apply_stacked_finances(self, fields: Dict[str, Any], text: str) -> None:
        """Финансы формата ВТБ «реестр Nл» (сигнатура меток стопкой).

        Просительная: «…в общем размере TOTAL руб … из которых: – AMT руб – КАТ;
        – AMT руб – КАТ». Госпошлина — в шапке «ГОСПОШЛИНА: NN руб» (банкротная,
        в долг не входит). Срабатывает ТОЛЬКО при сигнатуре — не трогает общий парсер.
        """
        if not text or not self._STACKED_SIG_RE.search(text):
            return
        money = r"(\d[\d   ]*[.,]\d{2})"
        # Разбивку берём из ПРОСИТЕЛЬНОЙ части («ПРОШУ:/ПРОСИТ:»), а не из тела,
        # где есть отдельные разбивки по каждому обязательству.
        _pr = re.search(r"\bПРОШУ\s*:|\bПРОСИТ\s*:", text, re.IGNORECASE)
        search_text = text[_pr.start():] if _pr else text
        pm = re.search(
            r"в\s+(?:\w+\s+){0,2}размере\s*" + money + r"\s*руб[^\n]{0,80}?из\s+котор\w+\s*:?(.{0,500})",
            search_text, re.IGNORECASE | re.DOTALL,
        )
        if not pm:
            return
        total = self._fin_amount(pm.group(1))
        body = pm.group(2)
        pr = it = fo = 0.0
        found = False
        for am in re.finditer(money + r"\s*руб[^–\-\n]*[–\-]\s*([^\n;]+)", body):
            val = self._fin_amount(am.group(1))
            lbl = am.group(2).lower()
            if val <= 0:
                continue
            # «основной долг (кредит, проценты)» — это долг (скобки не делают его процентами).
            if "неустой" in lbl or "пени" in lbl:
                fo += val
            elif "основн" in lbl or "долг" in lbl or "ссудн" in lbl:
                pr += val
            elif "процент" in lbl:
                it += val
            else:
                continue
            found = True
        if not found:
            return
        comp_sum = pr + it + fo
        if total <= 0 or abs(comp_sum - total) > 1.5:
            # Разбивка не сошлась с общим размером — не перекрываем (страховка).
            return
        fields["principalDebt"] = self._fin_fmt(pr)
        fields["principalDebt13"] = fields["principalDebt"]
        fields["interest"] = self._fin_fmt(it)
        fields["interest14"] = fields["interest"]
        fields["forfeit"] = self._fin_fmt(fo)
        fields["forfeit15"] = fields["forfeit"]
        fields["penalties"] = self._fin_fmt(0.0)
        fields["totalDebt"] = self._fin_fmt(total)
        fields["debtAmount"] = fields["totalDebt"]
        # Банкротная госпошлина из шапки «ГОСПОШЛИНА: NN руб».
        gm = re.search(r"ГОСПОШЛИНА[:\s]*" + money + r"\s*руб", text, re.IGNORECASE)
        if gm:
            duty = self._fin_fmt(self._fin_amount(gm.group(1)))
            fields["stateDuty16"] = duty
            fields["stateDuty"] = duty
        logger.info(
            "Финансы ВТБ (стопка): осн=%s проц=%s неуст=%s итог=%s пошлина=%s"
            % (fields["principalDebt"], fields["interest"], fields["forfeit"],
               fields["totalDebt"], fields.get("stateDuty16"))
        )

    def extract_fields(self, text: str, document_type: str) -> Dict[str, Any]:
        """
        Извлекает поля на основе паттернов
        """
        extracted_fields = {}
        logger.info(f"Начинаем извлечение полей для типа документа: {document_type}")
        logger.info(f"Длина текста: {len(text)} символов")

        if document_type not in self.patterns:
            logger.warning(f"Тип документа {document_type} не найден в паттернах")
            return extracted_fields

        patterns = self.patterns[document_type]
        logger.info(f"Найдено {len(patterns)} паттернов для извлечения")

        # Поля, которые нужно суммировать из всех обязательств
        summable_fields = ['principalDebt', 'loanDebt', 'interest', 'penalties', 'forfeit', 'totalDebt']

        # Поля, которые могут иметь множественные значения (договоры)
        multiple_fields = ['contractNumber', 'contractDate', 'obligationType']

        # Собираем все обязательства
        obligations = []

        for pattern_info in patterns:
            field_name = pattern_info["name"]
            field_patterns = pattern_info["patterns"]
            logger.info(f"Обрабатываем поле: {field_name} с {len(field_patterns)} паттернами")

            if field_name in summable_fields:
                # Суммируемое поле (суммы из паттернов)
                if self._extract_summable_field(extracted_fields, text, field_name, field_patterns):
                    continue
            elif field_name in multiple_fields:
                # Поле с множественными значениями (договоры)
                self._extract_multiple_field(extracted_fields, text, field_name, field_patterns)
            else:
                # Для обычных полей ищем первое вхождение
                # Специальная обработка для ИНН, ОГРН и companyInn - используем ту же логику, что и в реструктуризации!
                # Ищем ТОЛЬКО в блоке "Должник:" или "Ответчик:" (приоритет "Должник:")
                if field_name in ["inn", "ogrn", "ogrnip", "companyInn"]:
                    # ИНН/ОГРН/ОГРНИП должника из блока «Должник:»/«Ответчик:»
                    self._extract_party_inn_ogrn(extracted_fields, text, field_name)
                    continue

                # Приоритетная обработка адреса должника/ответчика.
                # Для ЮЛ адрес часто идет как "Юридический адрес:" внутри блока "Ответчик:",
                # и общий fallback может ошибочно забрать технические номера (CP-Case и т.п.).
                if field_name == "applicantAddress":
                    # Адрес должника из блока «Должник:»/«Ответчик:»
                    if self._extract_party_address(extracted_fields, text, field_name):
                        continue

                # ВАЖНО: Для ИНН, ОГРН, ОГРНИП и companyInn мы уже обработали выше, пропускаем общие паттерны
                if field_name in ["inn", "ogrn", "ogrnip", "companyInn"]:
                    logger.info(f"⚠️ Пропускаем общие паттерны для {field_name}, так как уже обработали в специальной логике")
                    continue

                for i, pattern in enumerate(field_patterns):
                    logger.info(f"  Паттерн {i+1} для {field_name}: {pattern}")

                    # Специальная обработка для courtName: приоритетно ищем в шапке (первые 2500 символов),
                    # чтобы не подхватить фрагмент из тела документа (юрлицо/ФЛ)
                    if field_name == "courtName":
                        text_header = text[:2500]
                        matches = re.findall(pattern, text_header, re.IGNORECASE)
                        if not matches:
                            matches = re.findall(pattern, text, re.IGNORECASE)
                        for match in matches:
                            if isinstance(match, tuple):
                                match_value = next((part for part in match if part), "")
                            else:
                                match_value = match

                            match_value = (match_value or "").strip()
                            if not match_value:
                                continue

                            # Очищаем название суда от лишнего текста
                            cleaned_value = self._clean_court_name(match_value)
                            if not cleaned_value or len(cleaned_value) < 10:
                                continue
                            cl = cleaned_value.lower()
                            # Должно быть явное "суд" или "арбитражн"
                            if "суд" not in cl and "арбитражн" not in cl:
                                continue
                            # Отбрасываем ссылки на закон: "Согласно п. 2 ст. 7...", "право на обращение в арбитражный суд"
                            if any(cl.startswith(p) or p in cl for p in ("согласно", "п. ", "ст. ", "закона право", "право на обращение")):
                                continue
                            # Название суда должно содержать указание региона (области, края, республики и т.д.)
                            region_words = ("области", "края", "республики", "города", "автономного округа", "автономной области")
                            if not any(r in cl for r in region_words):
                                continue
                            extracted_fields[field_name] = cleaned_value
                            logger.info(f"Extracted {field_name}: {cleaned_value}")
                            break

                        if field_name in extracted_fields:
                            break
                        continue
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        # Проверяем, есть ли группы захвата в паттерне
                        if match.groups():
                            value = match.group(1).strip()
                        else:
                            # Если групп нет, используем весь найденный текст
                            value = match.group(0).strip()
                        logger.info(f"  Найдено совпадение: '{value}'")
                        if value and len(value) > 2 and value.strip():  # Фильтруем слишком короткие значения и пустые строки
                            # Очищаем значение от звездочек
                            cleaned_value = self.clean_extracted_value(value)

                            # Специальная обработка для названия суда
                            if field_name == "courtName" and cleaned_value:
                                # Проверяем, является ли это процедурой "умерший"
                                procedure_type = extracted_fields.get('procedureType', '').lower()
                                procedure_raw = extracted_fields.get('procedureTypeRaw', '').lower()
                                is_deceased = (procedure_type == 'deceased' or
                                             any(keyword in procedure_raw for keyword in ["умер", "умерший", "смерть", "смерти"]))

                                if is_deceased:
                                    # Специальная очистка для процедуры "умерший"
                                    cleaned_value = self._clean_court_name_deceased(cleaned_value)
                                else:
                                    cleaned_value = self._clean_court_name(cleaned_value)

                                if not cleaned_value:
                                    continue

                            # Специальная обработка только для адреса заявителя
                            if field_name == "applicantAddress" and cleaned_value:
                                # Убираем [9] из адреса
                                cleaned_value = re.sub(r'\s*\[9\]\s*\.?', '', cleaned_value)
                                cleaned_value = re.sub(r'\s+', ' ', cleaned_value).strip()

                                # Убираем лишний текст про банкротство - более агрессивная очистка
                                cleaned_value = re.sub(r'\([^)]*родительный[^)]*\)', '', cleaned_value)
                                cleaned_value = re.sub(r'\[2\][^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'банкрот[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'процедур[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'реализац[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'имуществ[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'опубликов[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'сайт[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'Единого[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'федерального[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'реестр[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'сведений[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'банкротств[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'сообщение[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'№\s*[0-9]+[^0-9]*', '', cleaned_value)
                                cleaned_value = re.sub(r'\d{1,2}[.,]\d{1,2}[.,]\d{4}[^0-9]*', '', cleaned_value)

                                # Дополнительная очистка - убираем всё, что не является адресом
                                # Если в адресе есть почтовый индекс (6 цифр) — считаем, что он должен идти первым
                                if re.search(r'\b\d{6}\b', cleaned_value):
                                    cleaned_value = re.sub(r'^[^0-9]*', '', cleaned_value)  # Убираем всё до первого числа (индекса)
                                else:
                                    # Адрес без индекса (как в шапке: "Адрес регистрации: Ростовская область, ...") —
                                    # удаляем только служебные слова "Адрес", "адрес регистрации", "место жительства"
                                    cleaned_value = re.sub(
                                        r'^(Адрес|адрес|адрес\s+регистрации|место\s+жительства|место\s+регистрации)\s*[:\-–—]*\s*',
                                        '',
                                        cleaned_value,
                                        flags=re.IGNORECASE
                                    )
                                # Оставляем только цифры, запятые, пробелы, дефисы и русские буквы
                                cleaned_value = re.sub(r'[^0-9,\s\-а-яёА-ЯЁ\.]+', '', cleaned_value)

                                cleaned_value = re.sub(r'\s+', ' ', cleaned_value).strip()

                                # Агрессивная очистка - убираем все лишнее
                                # Сначала убираем все после первого упоминания банкротства
                                cleaned_value = re.sub(r'банкрот.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'процедур.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'реализац.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'имуществ.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'опубликов.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'сайт.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'Единого.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'федерального.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'реестр.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'сведений.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'банкротств.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'родительный.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'падеж.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'\[2\].*$', '', cleaned_value)
                                cleaned_value = re.sub(r'\[9\].*$', '', cleaned_value)
                                cleaned_value = re.sub(r'сообщение.*$', '', cleaned_value, flags=re.IGNORECASE)
                                cleaned_value = re.sub(r'01\.02\.1883.*$', '', cleaned_value)

                                # Убираем имена и лишний текст
                                cleaned_value = re.sub(r'\([^)]*\)', '', cleaned_value)  # Убираем скобки и их содержимое

                                # Убираем все до первого числа (индекса)
                                cleaned_value = re.sub(r'^[^0-9]*', '', cleaned_value)

                                # Оставляем только адресные данные
                                cleaned_value = re.sub(r'[^0-9,\s\-а-яёА-ЯЁ\.]', '', cleaned_value)
                                cleaned_value = re.sub(r'\s+', ' ', cleaned_value).strip()

                                # Если адрес слишком короткий, ищем полный адрес
                                if len(cleaned_value) < 20:
                                    # Ищем полный адрес в тексте
                                    address_patterns = [
                                        r'([0-9]{6}[,\s]+[^,\n]+(?:[,\s]+[^,\n]+)*?)(?:\n|$|[,\[]|(?:телефон|дата|огрн|инн|снилс|паспорт|серия|номер|банкрот|процедур|реализац|имуществ|опубликов|сайт|Единого|федерального|реестр|сведений|банкротств|родительный|падеж|\[2\]|\[9\]))',
                                        r'([0-9]{6}[,\s]+[А-ЯЁ][^,\n]+(?:[,\s]+[^,\n]+)*?)(?:\n|$|[,\[]|(?:телефон|дата|огрн|инн|снилс|паспорт|серия|номер))'
                                    ]

                                    for pattern in address_patterns:
                                        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
                                        if matches:
                                            # Берем первый найденный адрес
                                            full_address = matches[0].strip()
                                            # Очищаем его
                                            full_address = re.sub(r'банкрот.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'процедур.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'реализац.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'имуществ.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'опубликов.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'сайт.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'Единого.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'федерального.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'реестр.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'сведений.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'банкротств.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'родительный.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'падеж.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'\[2\].*$', '', full_address)
                                            full_address = re.sub(r'\[9\].*$', '', full_address)
                                            full_address = re.sub(r'сообщение.*$', '', full_address, flags=re.IGNORECASE)
                                            full_address = re.sub(r'01\.02\.1883.*$', '', full_address)
                                            full_address = re.sub(r'\([^)]*\)', '', full_address)
                                            full_address = re.sub(r'[^0-9,\s\-а-яёА-ЯЁ\.]', '', full_address)
                                            full_address = re.sub(r'\s+', ' ', full_address).strip()

                                        if len(full_address) > len(cleaned_value):
                                            cleaned_value = full_address
                                        break

                        # Не сохраняем creditorName, если подставился мусор ("кредиторов принимаются в установленном законом порядке")
                        if field_name == "creditorName" and cleaned_value and ("принимаются" in cleaned_value or "установленном законом" in cleaned_value):
                            logger.info(f"  Пропуск creditorName (мусорное значение): {cleaned_value[:60]}...")
                            continue
                        extracted_fields[field_name] = cleaned_value
                        logger.info(f"Extracted {field_name}: {cleaned_value}")
                        break
                    else:
                        logger.info(f"  Совпадений не найдено")

        # Fallback: пытаемся извлечь предмет залога [1221] для всех типов документов, если он не был найден
        if "mortgageCollateralDescription1221" not in extracted_fields or not extracted_fields.get("mortgageCollateralDescription1221"):
            logger.info("🔍 Предмет залога [1221] не найден в основных паттернах, пробуем fallback метод...")
            collateral_block = self._extract_mortgage_collateral_block(text)
            if collateral_block:
                extracted_fields["mortgageCollateralDescription1221"] = collateral_block
                logger.info(f"✅ Извлечено mortgageCollateralDescription1221 через fallback метод: {collateral_block[:150]}...")

        # Разделяем описание предметов залога на отдельные предметы и создаем массив collaterals
        collateral_description = extracted_fields.get("mortgageCollateralDescription1221")
        if collateral_description and re.match(r"^Кому\s+выдана\s+", collateral_description.strip(), re.IGNORECASE):
            # "Кому выдана [ФИО]" — не описание залога, а указание получателя; убираем ложное значение
            del extracted_fields["mortgageCollateralDescription1221"]
            collateral_description = None
            logger.info("Удалено ложное описание залога (Кому выдана ...)")
        if collateral_description:
            collateral_items = self._split_collateral_items(collateral_description)
            if collateral_items:
                collaterals_list = [self._make_collateral_obj(idx, item_desc)
                                    for idx, item_desc in enumerate(collateral_items)]
                # Сохраняем массив в extracted_fields для передачи во frontend
                extracted_fields["collaterals"] = collaterals_list
                logger.info(f"✅ Создано {len(collaterals_list)} предметов залога")

        # Теперь создаем отдельные обязательства
        obligations = self.extract_obligations(text, extracted_fields)
        if obligations:
            extracted_fields['obligations'] = obligations
            logger.info(f"Добавлено {len(obligations)} обязательств")

            def _fmt_sum(value: float) -> str:
                return f"{value:,.2f}".replace(",", " ").replace(".", ",")

            # Сумма всех обязательств -> totalDebt ([12])
            total_obligation_sum = sum(o.get('amountValue', 0.0) or 0.0 for o in obligations)
            if total_obligation_sum > 0:
                if document_type == "rtk_application":
                    # Для РТК не переопределяем totalDebt, чтобы не ломать сумму из блока "ПРОСИТ СУД".
                    extracted_fields["obligationsTotalDebt"] = _fmt_sum(total_obligation_sum)
                    logger.info(
                        f"Сумма всех обязательств (obligationsTotalDebt, только для справки): {extracted_fields['obligationsTotalDebt']}"
                    )
                else:
                    extracted_fields['totalDebt'] = _fmt_sum(total_obligation_sum)
                    logger.info(f"Сумма всех обязательств (totalDebt/[12]): {extracted_fields['totalDebt']}")

            # Сумма залоговых обязательств -> [0007]
            collateral_sum = sum(o.get('amountValue', 0.0) or 0.0 for o in obligations if o.get('isCollateral'))
            if collateral_sum > 0:
                extracted_fields['ipCollateralClaimAmount'] = _fmt_sum(collateral_sum)
                logger.info(f"Сумма залоговых обязательств ([0007]): {extracted_fields['ipCollateralClaimAmount']}")

            # Сумма неустоек залоговых обязательств -> [0071]
            collateral_penalty_sum = sum(o.get('penalty0071Value', 0.0) or 0.0 for o in obligations if o.get('isCollateral'))
            if collateral_penalty_sum > 0:
                extracted_fields['penalty0071'] = _fmt_sum(collateral_penalty_sum)
                logger.info(f"Сумма неустоек залоговых обязательств ([0071]): {extracted_fields['penalty0071']}")

            ordered_contract_numbers = []
            ordered_contract_dates = []

            # Сохраняем исходный contractNumber, если он был извлечен и содержит буквы (более полный)
            original_contract_number = extracted_fields.get('contractNumber', '')
            has_letters_in_original = bool(original_contract_number and re.search(r'[A-Za-zА-ЯЁ]', original_contract_number))

            for obligation in obligations:
                number = obligation.get('contractNumber')
                date = obligation.get('contractDate')

                if number and number not in ordered_contract_numbers:
                    # Если исходный номер содержит буквы и текущий номер - только цифры,
                    # проверяем, не является ли текущий номер частью исходного
                    if has_letters_in_original and number and not re.search(r'[A-Za-zА-ЯЁ]', number):
                        # Если исходный номер содержит текущий номер как подстроку, используем исходный
                        if number in original_contract_number:
                            continue  # Пропускаем короткий номер
                    ordered_contract_numbers.append(number)
                if date and date not in ordered_contract_dates:
                    ordered_contract_dates.append(date)

            # Если исходный номер содержит буквы и более полный, используем его вместо номеров из обязательств
            if has_letters_in_original and original_contract_number:
                # Проверяем, есть ли в обязательствах номера, которые являются частью исходного
                all_obligation_numbers_are_substrings = all(
                    not re.search(r'[A-Za-zА-ЯЁ]', num) and num in original_contract_number
                    for num in ordered_contract_numbers if num
                ) if ordered_contract_numbers else False

                if all_obligation_numbers_are_substrings or not ordered_contract_numbers:
                    # Используем исходный полный номер
                    extracted_fields['contractNumber'] = original_contract_number
                    logger.info(f"Используем исходный полный номер договора: {extracted_fields['contractNumber']}")
                else:
                    # Объединяем: сначала исходный, потом остальные уникальные
                    all_numbers = [original_contract_number] + [n for n in ordered_contract_numbers if n not in original_contract_number]
                    extracted_fields['contractNumber'] = ", ".join(all_numbers)
                    logger.info(f"Сводный список номеров договоров (с приоритетом исходного): {extracted_fields['contractNumber']}")
            elif ordered_contract_numbers:
                extracted_fields['contractNumber'] = ", ".join(ordered_contract_numbers)
                logger.info(f"Сводный список номеров договоров: {extracted_fields['contractNumber']}")

            if ordered_contract_dates:
                extracted_fields['contractDate'] = ", ".join(ordered_contract_dates)
                logger.info(f"Сводный список дат договоров: {extracted_fields['contractDate']}")

            # Подставляем реальные номера договоров в обязательства с плейсхолдером "Договор_1", "Договор_2" и т.д.
            contract_number_raw = extracted_fields.get('contractNumber', '')
            if contract_number_raw and obligations:
                parts = [p.strip() for p in re.split(r'[,;]', contract_number_raw)]
                real_numbers = [
                    p for p in parts
                    if p and p.lower() not in ('заключен', 'заключенный', 'далее')
                    and not re.match(r'^Договор_\d+$', p, re.IGNORECASE)
                    and len(p) >= 2
                ]
                for idx, obl in enumerate(obligations):
                    if not isinstance(obl, dict):
                        continue
                    current = (obl.get('contractNumber') or '').strip()
                    if re.match(r'^Договор_\d+$', current, re.IGNORECASE) and idx < len(real_numbers):
                        obl['contractNumber'] = real_numbers[idx]
                        logger.info(f"Подставлен реальный номер договора в обязательство {idx + 1}: {real_numbers[idx]}")

        # Приоритет: используем debtAmount, если requirementsSum = 0 или отсутствует
        if 'requirementsSum' in extracted_fields and extracted_fields['requirementsSum']:
            requirements_sum_value = str(extracted_fields['requirementsSum']).strip()
            # Проверяем, что это не "0,00" или пустое значение
            if requirements_sum_value and requirements_sum_value not in ["0", "0,00", "0.00", ""]:
                if 'totalDebt' not in extracted_fields or not extracted_fields['totalDebt'] or str(extracted_fields['totalDebt']).strip() in ["0", "0,00", "0.00", ""]:
                    extracted_fields['totalDebt'] = extracted_fields['requirementsSum']
                    logger.info(f"Используем сумму требований как общую сумму долга: {extracted_fields['requirementsSum']}")

        # Дополнительный разбор сложной формулировки:
        # "на сумму 32952 руб., из которой: сумма основного долга 15000 руб.,
        #  сумма долга по процентам 3264 руб., сумма задолженности по просроченным процентам 14688 руб.,
        #  расходы по оплате госпошлины – 2000 руб, ИТОГО – 34952 руб"
        try:
            breakdown_pattern = re.compile(
                r"на\s+сумму\s+([0-9\s,]+)\s*руб[\s\S]{0,200}?из\s+которой[:\s]*"
                r"сумма\s+основного\s+долга\s+([0-9\s,]+)\s*руб"
                r"[\s\S]{0,120}?сумма\s+долга\s+по\s+процентам\s+([0-9\s,]+)\s*руб"
                r"[\s\S]{0,120}?сумма\s+задолженности\s+по\s+просроченным\s+процентам\s+([0-9\s,]+)\s*руб"
                r"[\s\S]{0,160}?расход[аов]*\s+по\s+оплате\s+госпошл[ины]{3}\s*[–—-]?\s*([0-9\s,]+)\s*руб"
                r"[\s\S]{0,80}?(?:ИТОГО\s*[–—-]?\s*([0-9\s,]+)\s*руб)?",
                re.IGNORECASE,
            )
            breakdown_match = breakdown_pattern.search(text)
            if breakdown_match:
                base_sum, principal_b, interest_b, overdue_b, duty_b, total_b = breakdown_match.groups()
                principal_b = self.normalize_amount_value(principal_b or "")
                interest_b = self.normalize_amount_value(interest_b or "")
                overdue_b = self.normalize_amount_value(overdue_b or "")
                duty_b = self.normalize_amount_value(duty_b or "")
                if principal_b:
                    extracted_fields["principalDebt"] = principal_b
                if interest_b:
                    extracted_fields["interest"] = interest_b
                if overdue_b:
                    extracted_fields["forfeit"] = overdue_b
                if duty_b:
                    extracted_fields["stateDuty"] = duty_b
                if total_b:
                    extracted_fields["totalDebt"] = self.normalize_amount_value(total_b)
                logger.info(
                    f"Разобрана сложная формулировка сумм: principal={principal_b}, interest={interest_b}, "
                    f"overdue={overdue_b}, duty={duty_b}, total={extracted_fields.get('totalDebt')}"
                )
        except Exception as e:
            logger.debug(f"Ошибка при разборе сложной формулировки сумм: {e}")

        # Дополнительный разбор сложной формулировки:
        # "на сумму 32952 руб., из которой: сумма основного долга 15000 руб.,
        #  сумма долга по процентам 3264 руб., сумма задолженности по просроченным процентам 14688 руб.,
        #  расходы по оплате госпошлины – 2000 руб, ИТОГО – 34952 руб"
        try:
            breakdown_pattern = re.compile(
                r"на\s+сумму\s+([0-9\s,]+)\s*руб[^.]*?из\s+которой[:\s]*"
                r"сумма\s+основного\s+долга\s+([0-9\s,]+)\s*руб[^,]*,"
                r"\s*сумма\s+долга\s+по\s+процентам\s+([0-9\s,]+)\s*руб[^,]*,"
                r"\s*сумма\s+задолженности\s+по\s+просроченным\s+процентам\s+([0-9\s,]+)\s*руб[^,]*,"
                r"\s*расходы\s+по\s+оплате\s+госпошлин[ыа]\s*[–—-]?\s*([0-9\s,]+)\s*руб[^.]*?"
                r"(?:ИТОГО\s*[–—-]?\s*([0-9\s,]+)\s*руб)?",
                re.IGNORECASE | re.DOTALL,
            )
            breakdown_match = breakdown_pattern.search(text)
            if breakdown_match:
                base_sum, principal_b, interest_b, overdue_b, duty_b, total_b = breakdown_match.groups()
                principal_b = self.normalize_amount_value(principal_b or "")
                interest_b = self.normalize_amount_value(interest_b or "")
                overdue_b = self.normalize_amount_value(overdue_b or "")
                duty_b = self.normalize_amount_value(duty_b or "")
                if principal_b:
                    extracted_fields["principalDebt"] = principal_b
                if interest_b:
                    extracted_fields["interest"] = interest_b
                if overdue_b:
                    extracted_fields["forfeit"] = overdue_b
                if duty_b:
                    extracted_fields["stateDuty"] = duty_b
                if total_b:
                    extracted_fields["totalDebt"] = self.normalize_amount_value(total_b)
                else:
                    # если "ИТОГО" нет, общая сумма = базовая сумма + госпошлина
                    try:
                        base_f = float(self.normalize_amount_value(base_sum or "0").replace(" ", "").replace(",", "."))
                        duty_f = float(self.normalize_amount_value(duty_b or "0").replace(" ", "").replace(",", "."))
                        total_calc = base_f + duty_f
                        formatted_total = f"{total_calc:,.2f}".replace(",", " ").replace(".", ",")
                        extracted_fields["totalDebt"] = formatted_total
                    except Exception:
                        pass
                logger.info(
                    f"Разобрана сложная формулировка сумм: principal={principal_b}, interest={interest_b}, "
                    f"overdue={overdue_b}, duty={duty_b}, total={extracted_fields.get('totalDebt')}"
                )
        except Exception as e:
            logger.debug(f"Ошибка при разборе сложной формулировки сумм: {e}")

        # Попытка дополнительно вытащить суммы из "табличных" форматов,
        # когда название и сумма разбиты по разным строкам (как в таблице)
        try:
            if document_type == "rtk_application" and text:
                lines = text.splitlines()

                def _extract_amount_near_index(start_index: int) -> Optional[str]:
                    """
                    Ищет сумму в этой или ближайших строках ниже (типичный случай: название в одной ячейке, сумма в соседней).
                    """
                    n = len(lines)
                    for j in range(start_index, min(n, start_index + 3)):
                        line_j = lines[j]
                        m = re.search(r"([0-9][0-9\s\u00a0\u202f.,]+)", line_j)
                        if m:
                            return self.normalize_amount_value(m.group(1))
                    return None

                # principalDebt из таблиц
                if not extracted_fields.get("principalDebt"):
                    for idx, line in enumerate(lines):
                        ll = line.lower()
                        if (
                            "сумма основного долга" in ll
                            or ("основной долг" in ll and "просроч" not in ll)
                            or "тело долга" in ll
                        ):
                            val = _extract_amount_near_index(idx)
                            if val:
                                extracted_fields["principalDebt"] = val
                                logger.info(f"principalDebt извлечён из табличного блока: {val}")
                                break

                # interest из таблиц
                if not extracted_fields.get("interest"):
                    for idx, line in enumerate(lines):
                        ll = line.lower()
                        if "сумма долга по процентам" in ll or "проценты" in ll:
                            val = _extract_amount_near_index(idx)
                            if val:
                                extracted_fields["interest"] = val
                                logger.info(f"interest извлечён из табличного блока: {val}")
                                break

                # forfeit (просроченные проценты) из таблиц
                if not extracted_fields.get("forfeit"):
                    for idx, line in enumerate(lines):
                        ll = line.lower()
                        if "задолженности по просроченным процентам" in ll or "просроченным процентам" in ll:
                            val = _extract_amount_near_index(idx)
                            if val:
                                extracted_fields["forfeit"] = val
                                logger.info(f"forfeit извлечён из табличного блока: {val}")
                                break

                # stateDuty из таблиц (строка с госпошлиной)
                if not extracted_fields.get("stateDuty"):
                    for idx, line in enumerate(lines):
                        ll = line.lower()
                        if "госпошлин" in ll or "государственной пошл" in ll:
                            val = _extract_amount_near_index(idx)
                            if val:
                                extracted_fields["stateDuty"] = val
                                logger.info(f"stateDuty извлечена из табличного блока: {val}")
                                break
        except Exception as e:
            logger.debug(f"Ошибка при попытке извлечь суммы из табличного формата: {e}")

        # Если totalDebt отсутствует или равен 0, пытаемся собрать его из составных частей
        if 'totalDebt' not in extracted_fields or not extracted_fields['totalDebt'] or str(extracted_fields['totalDebt']).strip() in ["0", "0,00", "0.00", ""]:
            principal = self._safe_amount_field(extracted_fields.get("principalDebt"))
            interest = self._safe_amount_field(extracted_fields.get("interest"))
            forfeit_val = self._safe_amount_field(extracted_fields.get("forfeit"))
            loan_debt = self._safe_amount_field(extracted_fields.get("loanDebt"))

            composite_total = 0.0
            if loan_debt > 0:
                composite_total += loan_debt
            if principal > 0:
                composite_total += principal
            if interest > 0:
                composite_total += interest
            if forfeit_val > 0:
                composite_total += forfeit_val

            if composite_total > 0:
                formatted_total = f"{composite_total:,.2f}".replace(',', ' ').replace('.', ',')
                extracted_fields['totalDebt'] = formatted_total
                logger.info(f"Собрана общая сумма долга из частей: {formatted_total}")
            elif 'debtAmount' in extracted_fields and extracted_fields['debtAmount']:
                extracted_fields['totalDebt'] = extracted_fields['debtAmount']
                logger.info(f"Используем debtAmount как общую сумму долга: {extracted_fields['debtAmount']}")

        # Для rtk_application: если debtAmount явно равен только основному долгу,
        # а проценты и просроченные проценты уже найдены — корректируем суммы.
        if document_type == "rtk_application":
            try:
                principal = self._safe_amount_field(extracted_fields.get("principalDebt"))
                interest = self._safe_amount_field(extracted_fields.get("interest"))
                forfeit_val = self._safe_amount_field(extracted_fields.get("forfeit"))
                composite = principal + interest + forfeit_val
                current_debt = self._safe_amount_field(extracted_fields.get("debtAmount"))
                if composite > 0 and current_debt > 0:
                    # Если debtAmount практически совпадает с principalDebt и явно меньше суммы компонентов —
                    # считаем это ошибкой извлечения и подменяем.
                    if abs(current_debt - principal) < 1 and current_debt < composite:
                        formatted = f"{composite:,.2f}".replace(",", " ").replace(".", ",")
                        old_debt = extracted_fields.get("debtAmount")
                        extracted_fields["debtAmount"] = formatted
                        total_str = (extracted_fields.get("totalDebt") or "").strip()
                        total_val = self._safe_amount_field(total_str) if total_str else 0.0
                        if not total_val or abs(total_val - self._safe_amount_field(old_debt)) < 1:
                            extracted_fields["totalDebt"] = formatted
                        logger.info(f"Скорректирована сумма требований: debtAmount/totalDebt = {formatted} (principal+interest+forfeit)")
            except Exception as e:
                logger.debug(f"Ошибка при корректировке суммы требований: {e}")

        # Для rtk_application: суммы берём ИЗ БЛОКА "ПРОСИТ СУД"
        if document_type == "rtk_application":
            # Суммы/госпошлина/публикация из блока «ПРОСИТ СУД»
            self._extract_claim_block_amounts(extracted_fields, text)

        # Согласование сумм долга (principal/interest/forfeit/total/loanDebt)
        self._reconcile_debt_amounts(extracted_fields, text, document_type)

        # Согласование госпошлины/requirementsSum
        self._reconcile_state_duty(extracted_fields, text, document_type)

        # Если ссудная госпошлина явно не указана, но есть общая госпошлина,
        # используем её как ссудную (чтобы в шаблонах [17] не оставался пустым).
        # Для rtk_application это правило НЕ применяется: отсутствие [17] в заявлении
        # должно приводить к удалению соответствующего маркера и текста в акте.
        if document_type != "rtk_application" and not extracted_fields.get("loanStateDuty17"):
            if extracted_fields.get("stateDuty16"):
                extracted_fields["loanStateDuty17"] = extracted_fields["stateDuty16"]
            elif extracted_fields.get("stateDuty"):
                extracted_fields["loanStateDuty17"] = extracted_fields["stateDuty"]


        # Реквизиты ЮЛ из блока «Должник:» (debtor_block)
        debtor_block = self._extract_legal_entity_requisites(extracted_fields, text)

        procedure_type, procedure_raw = self.determine_procedure_type(text)
        if procedure_type:
            extracted_fields['procedureType'] = procedure_type
            logger.info(f"Определен тип процедуры: {procedure_type}")
        if procedure_raw:
            extracted_fields['procedureTypeRaw'] = procedure_raw
            logger.info(f"Оригинальное описание процедуры: {procedure_raw}")

        # Пост-обработка процедуры и managerInn
        self._normalize_procedure_and_manager(extracted_fields, text, procedure_type)

        debtor_name_raw = extracted_fields.get("debtorName")
        applicant_name_raw = extracted_fields.get("applicantName")
        applicant_name_genitive_raw = extracted_fields.get("applicantNameGenitive")
        applicant_name_instrumental_raw = extracted_fields.get("applicantNameInstrumental")
        debtor_clean = None
        if debtor_name_raw:
            # Отклоняем значения, которые явно являются описанием процедуры, а не именем должника
            if re.search(r"^введена\s+процедура|процедура\s+наблюдения", debtor_name_raw, re.IGNORECASE):
                debtor_name_raw = None
        if debtor_name_raw:
            debtor_clean = re.sub(r"\[.*?\]", "", debtor_name_raw)
            debtor_clean = self.clean_extracted_value(debtor_clean)
            debtor_clean = debtor_clean.strip('«»" ')
            debtor_clean = re.sub(r"^\s*фио\s+", "", debtor_clean, flags=re.IGNORECASE)
            # Удаляем фразы типа "должника введена процедура"
            debtor_clean = re.sub(r"\s*должника\s+введена\s+процедура.*$", "", debtor_clean, flags=re.IGNORECASE)
            debtor_clean = re.sub(r"\s*введена\s+процедура\s+наблюдения.*$", "", debtor_clean, flags=re.IGNORECASE)
            debtor_clean = debtor_clean.strip()
            # Дополнительная проверка: отклоняем если осталось только "а" или другие короткие обрывки
            if debtor_clean and len(debtor_clean) > 3 and not re.match(r"^[а-яё]\s*\.?$", debtor_clean, re.IGNORECASE):
                extracted_fields["debtorName"] = debtor_clean
            else:
                extracted_fields.pop("debtorName", None)
        else:
            extracted_fields.pop("debtorName", None)
        # ВАЖНО: всю дополнительную очистку имени должника выше мы применяем ко всем типам документов.
        # Для юр. инициирования ниже есть отдельная логика, которая аккуратно переустанавливает имя
        # должника из шапки документа и не влияет на остальные типы.

        applicant_clean = None
        if applicant_name_raw:
            # Отклоняем значения, которые явно являются описанием процедуры, а не именем должника
            if re.search(r"^[а-яё]\s+введена\s+процедура|^введена\s+процедура|процедура\s+наблюдения|соответствует\s+признак|признак\w*\s+банкрот", applicant_name_raw, re.IGNORECASE):
                applicant_name_raw = None
        if applicant_name_raw:
            applicant_clean = re.sub(r"\[.*?\]", "", applicant_name_raw)
            applicant_clean = self.clean_extracted_value(applicant_clean)
            applicant_clean = applicant_clean.strip('«»" ')
            applicant_clean = re.sub(r"^\s*фио\s+", "", applicant_clean, flags=re.IGNORECASE)
            applicant_clean = re.sub(r"\s*должника\s+введена\s+процедура.*$", "", applicant_clean, flags=re.IGNORECASE)
            applicant_clean = re.sub(r"\s*введена\s+процедура\s+наблюдения.*$", "", applicant_clean, flags=re.IGNORECASE)
            applicant_clean = applicant_clean.strip()
            # Дополнительная проверка: отклоняем если осталось только "а" или другие короткие обрывки
            if applicant_clean and len(applicant_clean) > 3 and not re.match(r"^[а-яё]\s*\.?$", applicant_clean, re.IGNORECASE):
                extracted_fields["applicantName"] = applicant_clean
            else:
                extracted_fields.pop("applicantName", None)
        else:
            extracted_fields.pop("applicantName", None)
        # Если не извлекли имя, пробуем короткое наименование по тексту/блоку должника
        if "applicantName" not in extracted_fields:
            legal_fallback_source = debtor_block or debtor_name_raw or applicant_name_raw or text[:1200]
            legal_short = self.extract_legal_entity_short_name(legal_fallback_source)
            if legal_short:
                extracted_fields["applicantName"] = legal_short

        if applicant_name_genitive_raw:
            # Отклоняем значения, которые явно являются описанием процедуры, а не именем должника
            if re.search(r"^введена\s+процедура|процедура\s+наблюдения", applicant_name_genitive_raw, re.IGNORECASE):
                applicant_name_genitive_raw = None
        if applicant_name_genitive_raw:
            genitive_clean = re.sub(r"\[.*?\]", "", applicant_name_genitive_raw)
            genitive_clean = self.clean_extracted_value(genitive_clean)
            genitive_clean = genitive_clean.strip('«»" ')
            genitive_clean = re.sub(r"^\s*фио\s+", "", genitive_clean, flags=re.IGNORECASE)
            # Убираем префиксы "ГЛАВА КФХ ИП" для родительного падежа
            genitive_clean = re.sub(
                r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                '',
                genitive_clean,
                flags=re.IGNORECASE
            ).strip()
            # Удаляем фразы типа "введена процедура наблюдения"
            genitive_clean = re.sub(r"\s*введена\s+процедура\s+наблюдения.*$", "", genitive_clean, flags=re.IGNORECASE)
            genitive_clean = genitive_clean.strip()
            # Дополнительная проверка: отклоняем если осталось только "а" или другие короткие обрывки
            if genitive_clean and len(genitive_clean) > 3 and not re.match(r"^[а-яё]\s*\.?$", genitive_clean, re.IGNORECASE):
                extracted_fields["applicantNameGenitive"] = genitive_clean
            else:
                extracted_fields.pop("applicantNameGenitive", None)
        else:
            extracted_fields.pop("applicantNameGenitive", None)

        # Для КФХ используем kfhHeadName для генерации падежных форм (без префиксов)
        is_kfh = extracted_fields.get("isKfh", False)
        # Падежные формы должника [2.1]-[2.4]
        self._generate_debtor_case_forms(extracted_fields, text, applicant_clean, is_kfh, applicant_name_instrumental_raw)

        # Короткое имя ЮЛ и донастройка initiation_legal
        debtor_clean = self._tune_legal_entity_naming(extracted_fields, text, debtor_clean, applicant_clean, applicant_name_raw, debtor_block, debtor_name_raw)

        # Валидация и фолбэки адреса должника
        self._resolve_debtor_address(extracted_fields, text, debtor_block)

        if extracted_fields.get("ogrn"):
            extracted_fields["ogrn"] = re.sub(r"\D", "", extracted_fields["ogrn"])

        if extracted_fields.get("companyInn"):
            extracted_fields["companyInn"] = re.sub(r"\D", "", extracted_fields["companyInn"])

        # Санити кредитных параметров (срок/ставка)
        self._sanitize_credit_params(extracted_fields, text)

        # Финализация типа должника и финуправляющего
        self._finalize_debtor_type(extracted_fields, text, debtor_clean)

        # Финальная нормализация блока «Финансовые данные»: неустойка/штраф,
        # даты платёжных поручений (депозит/госпошлина), банкротная/ссудная
        # госпошлина, общая сумма долга. Запускается последней — перекрывает
        # ошибки ранних путей извлечения высоконадёжными формулировками.
        self._normalize_financial_block(extracted_fields, text)

        # Защита D: убрать даты договоров/решений, которые в тексте встречаются
        # только в ссылках на закон/постановление Пленума (дата ФЗ != дата договора).
        self._drop_law_context_dates(extracted_fields, text)

        logger.info(f"Итоговые извлеченные поля: {extracted_fields}")
        return extracted_fields

    _LAW_DATE_FIELDS = ("contractDate", "courtDecisionDate", "priorDecisionDate")

    def _extract_kommersant_publication(self, extracted_fields, text):
        """[67]/[68] — номер и дата публикации в газете «Коммерсантъ» (вынесено из extract_fields)."""
        # [68] — дата газеты «Коммерсантъ» (не путать с [11] ЕФРСБ)
        # Приоритет: типичная формулировка "в газете «Коммерсантъ» № 123 от 27.12.2025"
        kommersant_date_match = re.search(
            r"(?:газет[аы]\s+)?[«\"]?Коммерсант[ъ\"»']?[»\"]?\s*№\s*[0-9\-\/]+\s*от\s*(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
            text,
            re.IGNORECASE,
        )
        if not kommersant_date_match:
            # Вариант "в газете «Коммерсантъ» от 27.12.2025" — без номера
            kommersant_date_match = re.search(
                r"в[\s\u00a0\u202f]+газет[аы][\s\u00a0\u202f]+«?Коммерсант[\"ъ»']?»?\s*[^0-9]{0,40}?от[\s\u00a0\u202f]*(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
                text,
                re.IGNORECASE,
            )
        if not kommersant_date_match:
            # Вариант "27.12.2025 в газете «Коммерсантъ»" — дата стоит ПЕРЕД упоминанием газеты
            kommersant_date_match = re.search(
                r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})[\s\u00a0\u202f]+в[\s\u00a0\u202f]+газет[аы][\s\u00a0\u202f]+«?Коммерсант[\"ъ»']?»?",
                text,
                re.IGNORECASE,
            )
        if not kommersant_date_match:
            # Формулировка из скобок:
            # "(опубликована на сайте официального издания газеты «Коммерсантъ» ... от 27.12.2025)"
            # Между "Коммерсантъ" и "от" может быть большой фрагмент текста, поэтому даём большой допуск.
            kommersant_date_match = re.search(
                r"официальн[а-яё\s]+издан[а-яё\s]+газет[аы]\s+«?Коммерсант[\"ъ»']?»?[^0-9]{0,400}?от\s*(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
                text,
                re.IGNORECASE,
            )
        if not kommersant_date_match:
            # Самый общий вариант: рядом с упоминанием "Коммерсант" есть дата.
            # Сначала пробуем классический паттерн,
            # затем — полный проход по всем датам с поиском ближайшей к слову "Коммерсант".
            kommersant_date_match = re.search(
                r"Коммерсант[ъ\"»']?\s*[^0-9]{0,200}?(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
                text,
                re.IGNORECASE,
            )
            if not kommersant_date_match and re.search(r"Коммерсант", text, re.IGNORECASE):
                date_pattern = re.compile(r"(\d{1,2}[.,]\d{1,2}[.,]\d{4})")
                best_match = None
                best_date = None  # сравниваем реальные даты, чтобы не брать старый закон 2002 года
                for m in date_pattern.finditer(text):
                    start, end = m.start(), m.end()
                    window_start = max(0, start - 150)
                    window_end = min(len(text), end + 150)
                    window = text[window_start:window_end]
                    if re.search(r"Коммерсант", window, re.IGNORECASE):
                        date_str = m.group(1).replace(",", ".")
                        try:
                            day, month, year = map(int, date_str.split("."))
                            # Грубая фильтрация нереалистичных годов
                            if year < 1990 or year > 2100:
                                continue
                            from datetime import date as _date
                            cur_date = _date(year, month, day)
                        except Exception:
                            continue
                        if best_date is None or cur_date > best_date:
                            best_date = cur_date
                            best_match = m
                if best_match:
                    kommersant_date_match = best_match
        if kommersant_date_match:
            kommersant_date = kommersant_date_match.group(1).strip().replace(",", ".")
            extracted_fields["kommersantDate"] = kommersant_date
            logger.info(f"Дата газеты «Коммерсантъ» [68]: {kommersant_date}")
        # [67] — номер газеты «Коммерсантъ» (только при явном «№ …», не путать с [9] ЕФРСБ)
        kommersant_number_match = re.search(
            r"(?:газет[аы]\s+)?[«\"]?Коммерсант[ъ\"»']?[»\"]?\s*№\s*([0-9\-\/]+)",
            text,
            re.IGNORECASE,
        )
        if kommersant_number_match:
            extracted_fields["kommersantNumber"] = kommersant_number_match.group(1).strip()
            logger.info(f"Номер газеты «Коммерсантъ» [67]: {extracted_fields['kommersantNumber']}")







    def _generate_debtor_case_forms(self, extracted_fields, text, applicant_clean, is_kfh, applicant_name_instrumental_raw):
        """Падежные формы имени должника [2.1] род., [2.3] твор., [2.4] вин., [2.2] дат.: очистка raw-значений и автогенерация склонений (КФХ — по ФИО без префиксов). Вынесено из extract_fields."""
        kfh_head_name = extracted_fields.get("kfhHeadName", "")
        name_for_inflection = applicant_clean

        if is_kfh and kfh_head_name:
            # Для КФХ используем только ФИО без префиксов
            name_for_inflection = kfh_head_name
            logger.info(f"🔧 КФХ: используем kfhHeadName '{kfh_head_name}' для генерации падежных форм")

        if "applicantNameGenitive" not in extracted_fields and name_for_inflection:
            genitive_auto = self._convert_name_to_genitive(name_for_inflection)
            if genitive_auto:
                extracted_fields["applicantNameGenitive"] = genitive_auto

        # Творительный падеж для должника (маркер [2.3])
        if applicant_name_instrumental_raw:
            instr_clean = re.sub(r"\[.*?\]", "", applicant_name_instrumental_raw)
            instr_clean = self.clean_extracted_value(instr_clean)
            instr_clean = instr_clean.strip('«»" ')
            instr_clean = re.sub(r"^\s*фио\s+", "", instr_clean, flags=re.IGNORECASE)
            # Убираем префиксы "ГЛАВА КФХ ИП" для творительного падежа
            instr_clean = re.sub(
                r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                '',
                instr_clean,
                flags=re.IGNORECASE
            ).strip()
            instr_clean = re.sub(r"\s*введена\s+процедура\s+наблюдения.*$", "", instr_clean, flags=re.IGNORECASE)
            instr_clean = instr_clean.strip()
            if instr_clean and len(instr_clean) > 3:
                extracted_fields["applicantNameInstrumental"] = instr_clean
            else:
                extracted_fields.pop("applicantNameInstrumental", None)

        if "applicantNameInstrumental" not in extracted_fields and name_for_inflection:
            instr_auto = self._convert_name_to_instrumental(name_for_inflection)
            if instr_auto:
                extracted_fields["applicantNameInstrumental"] = instr_auto

        # Обработка винительного падежа [2.4]
        applicant_name_accusative_raw = extracted_fields.get("applicantNameAccusative")
        if applicant_name_accusative_raw:
            accs_clean = re.sub(r"\[.*?\]", "", applicant_name_accusative_raw)
            accs_clean = self.clean_extracted_value(accs_clean)
            accs_clean = accs_clean.strip('«»" ')
            accs_clean = re.sub(r"^\s*фио\s+", "", accs_clean, flags=re.IGNORECASE)
            # Убираем префиксы "ГЛАВА КФХ ИП" для винительного падежа
            accs_clean = re.sub(
                r'^(ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+|ИП\s+ГЛАВА\s+КФХ\s+)',
                '',
                accs_clean,
                flags=re.IGNORECASE
            ).strip()
            accs_clean = re.sub(r"\s*введена\s+процедура\s+наблюдения.*$", "", accs_clean, flags=re.IGNORECASE)
            accs_clean = accs_clean.strip()
            if accs_clean and len(accs_clean) > 3:
                # Отклоняем значения, которые явно являются описанием процедуры
                if not re.search(r"^введена\s+процедура|процедура\s+наблюдения", accs_clean, re.IGNORECASE):
                    extracted_fields["applicantNameAccusative"] = accs_clean
            else:
                extracted_fields.pop("applicantNameAccusative", None)

        if "applicantNameAccusative" not in extracted_fields and name_for_inflection:
            # Для КФХ используем правильное склонение с одушевленностью (кого?)
            accs_auto = self._convert_name_to_accusative(name_for_inflection)
            if accs_auto:
                extracted_fields["applicantNameAccusative"] = accs_auto

        # Дательный падеж для должника (маркер [2.2]) - везде это имя должника в дательном падеже, кроме ипотеки
        # НЕ генерируем дательный падеж, если name_for_inflection содержит "суд" (это название суда, а не имя должника)
        if "applicantNameDative" not in extracted_fields and name_for_inflection:
            # Проверяем, что это не название суда
            if "суд" not in name_for_inflection.lower():
                # Убираем префикс "ИП" перед склонением (как для других падежей)
                name_for_dative = re.sub(
                    r'^(ИП\s+|ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+)',
                    '',
                    name_for_inflection,
                    flags=re.IGNORECASE
                ).strip()
                if not name_for_dative:
                    name_for_dative = name_for_inflection

                dative_auto = self._convert_name_to_dative(name_for_dative)
                if dative_auto:
                    extracted_fields["applicantNameDative"] = dative_auto
                    logger.info(f"Сгенерирован дательный падеж для [2.2]: {dative_auto}")
            else:
                logger.warning(f"Пропущена генерация дательного падежа - name_for_inflection содержит 'суд': {name_for_inflection}")

    def _normalize_procedure_and_manager(self, extracted_fields, text, procedure_type):
        """Пост-обработка процедуры и управляющего: чистка названия суда для «умерший», фолбэк процедуры «наблюдение» по raw-описанию, валидация managerInn по контрольной сумме. Вынесено из extract_fields."""
        # Специальная обработка названия суда для процедуры "умерший"
        if procedure_type == 'deceased' and extracted_fields.get('courtName'):
            court_name = extracted_fields['courtName']
            cleaned_court_name = self._clean_court_name_deceased(court_name)
            if cleaned_court_name != court_name:
                extracted_fields['courtName'] = cleaned_court_name
                logger.info(f"Очищено название суда для процедуры 'умерший': '{court_name}' -> '{cleaned_court_name}'")

        # Фолбэк: если тип процедуры явно не нормализовался, но по "сырому" описанию видно "наблюдение" —
        # считаем, что это процедура наблюдения.
        if not extracted_fields.get("procedureType"):
            raw_lower = (extracted_fields.get("procedureTypeRaw") or "").lower()
            if any(token in raw_lower for token in ["наблюден", "наблюдения", "наблюдение"]):
                extracted_fields["procedureType"] = "observation"
                logger.info("Процедура по умолчанию установлена как 'observation' на основании procedureTypeRaw")

        manager_inn = extracted_fields.get("managerInn")
        if manager_inn:
            normalized_inn = re.sub(r"\D", "", manager_inn)
            # Отсеиваем мусор, не проходящий контрольную сумму (например, 689768767676),
            # чтобы в поле не подставлялся заведомо ложный ИНН.
            if normalized_inn and is_valid_inn(normalized_inn):
                extracted_fields["managerInn"] = normalized_inn
            else:
                logger.debug(f"managerInn '{manager_inn}' отброшен: не прошёл контрольную сумму")
                extracted_fields.pop("managerInn", None)







    def _extract_multiple_field(self, extracted_fields, text, field_name, field_patterns):
        """Поля с множественными значениями (contractNumber/contractDate/obligationType): сбор всех вхождений по паттернам, защита C (закон != договор), фильтры мусора, дедуп с сохранением порядка. Вынесено из pattern-цикла."""
        # Для полей с множественными значениями собираем все вхождения
        found_values = []
        for pattern in field_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                value = match.strip()
                if value and len(value) > 2:
                    # Очищаем значение от звездочек
                    cleaned_value = self.clean_extracted_value(value)
                    if not cleaned_value:  # Если после очистки ничего не осталось
                        continue

                    # Фильтруем мусорные значения
                    if field_name == 'contractNumber':
                        # Защита C: «№ 353-ФЗ» — ссылка на закон, не номер договора.
                        if looks_like_law_ref(cleaned_value):
                            logger.info(f"Пропуск contractNumber (ссылка на закон): {cleaned_value}")
                        elif not any(word in cleaned_value.lower() for word in ['считается', 'поручительства', 'возникшим', 'которые', 'согласно', 'установленную', 'принятые', 'договор', 'кредитный', 'путем', 'подписания', 'далее']) and len(cleaned_value.strip()) >= 2:
                            found_values.append(cleaned_value)
                            logger.info(f"Found {field_name}: {cleaned_value}")
                    elif field_name == 'obligationType':
                        if not any(word in cleaned_value.lower() for word in ['возникшим', 'которые', 'согласно', 'установленную', 'принятые']):
                            found_values.append(cleaned_value)
                            logger.info(f"Found {field_name}: {cleaned_value}")
                    else:
                        found_values.append(cleaned_value)
                        logger.info(f"Found {field_name}: {cleaned_value}")

        if found_values:
            # Удаляем дубликаты, сохраняя порядок появления
            unique_values = []
            seen_values = set()
            for value in found_values:
                normalized = value.lower()
                if normalized in seen_values:
                    continue
                seen_values.add(normalized)
                unique_values.append(value)

            if unique_values:
                # Объединяем все найденные значения через запятую
                extracted_fields[field_name] = ", ".join(unique_values)
                logger.info(f"All {field_name}: {extracted_fields[field_name]}")

    def _detect_kfh_head(self, text):
        """Ранняя детекция КФХ по тексту («ГЛАВА КФХ ИП ФИО»). Возвращает (is_kfh_detected, kfh_head_name). Вынесено из analyze."""
        # РАННЕЕ ОПРЕДЕЛЕНИЕ КФХ: автоматически определяем по словам "ГЛАВА КФХ ИП"
        # Ищем в любом месте документа, не только в блоке должника
        kfh_patterns = [
            r"глава\s+кфх\s+ип\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})",  # "ГЛАВА КФХ ИП ФИО"
            r"кфх\s+ип\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})",  # "КФХ ИП ФИО"
            r"глава\s+кфх\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})",  # "ГЛАВА КФХ ФИО"
        ]

        is_kfh_detected = False
        kfh_head_name = None

        for pattern in kfh_patterns:
            kfh_match = re.search(pattern, text, re.IGNORECASE)
            if kfh_match:
                is_kfh_detected = True
                kfh_head_name = kfh_match.group(1).strip()
                logger.info(f"✅ КФХ обнаружено по паттерну '{pattern}': глава КФХ - {kfh_head_name}")
                break
        return is_kfh_detected, kfh_head_name

    def _regenerate_ip_dative(self, extracted_fields, text, ip_specific_fields):
        """Перегенерация дательного падежа [2.2] для должника-ИП: выбор корректного ФИО (приоритет ip_specific/extracted, фильтр «не суд»), снятие префиксов, склонение. Вынесено из analyze."""
        # Перегенерируем дательный падеж [2.2] с правильным именем должника
        # Используем правильное имя из ip_specific_fields или extracted_fields
        correct_name_for_dative = None

        # Функция для проверки, что это полное ФИО (3 слова) и не название суда
        def is_valid_name(name):
            if not name or "суд" in name.lower():
                return False
            # Проверяем, что это похоже на ФИО (минимум 2 слова, максимум 4 слова с префиксами)
            words = name.strip().split()
            if len(words) < 2 or len(words) > 4:
                return False
            # Проверяем, что слова начинаются с заглавной буквы (кроме префиксов)
            valid_words = [w for w in words if w.upper() not in ["ИП", "ГЛАВА", "КФХ"]]
            if len(valid_words) < 2:
                return False
            return True

        # Приоритет 1: applicantName из ip_specific_fields
        if ip_specific_fields.get("applicantName") and is_valid_name(ip_specific_fields.get("applicantName")):
            correct_name_for_dative = ip_specific_fields.get("applicantName")
            logger.info(f"Используем applicantName из ip_specific_fields для [2.2]: {correct_name_for_dative}")

        # Приоритет 2: debtorName из ip_specific_fields
        if not correct_name_for_dative and ip_specific_fields.get("debtorName") and is_valid_name(ip_specific_fields.get("debtorName")):
            correct_name_for_dative = ip_specific_fields.get("debtorName")
            logger.info(f"Используем debtorName из ip_specific_fields для [2.2]: {correct_name_for_dative}")

        # Приоритет 3: applicantName из extracted_fields
        if not correct_name_for_dative and extracted_fields.get("applicantName") and is_valid_name(extracted_fields.get("applicantName")):
            correct_name_for_dative = extracted_fields.get("applicantName")
            logger.info(f"Используем applicantName из extracted_fields для [2.2]: {correct_name_for_dative}")

        # Приоритет 4: debtorName из extracted_fields
        if not correct_name_for_dative and extracted_fields.get("debtorName") and is_valid_name(extracted_fields.get("debtorName")):
            correct_name_for_dative = extracted_fields.get("debtorName")
            logger.info(f"Используем debtorName из extracted_fields для [2.2]: {correct_name_for_dative}")

        # Если нашли правильное имя, генерируем дательный падеж
        if correct_name_for_dative:
            # Убираем префикс "ИП" перед склонением
            name_for_dative = re.sub(
                r'^(ИП\s+|ГЛАВА\s+КФХ\s+ИП\s+|ГЛАВА\s+КФХ\s+|КФХ\s+ИП\s+)',
                '',
                correct_name_for_dative,
                flags=re.IGNORECASE
            ).strip()
            if name_for_dative:
                dative_auto = self._convert_name_to_dative(name_for_dative)
                if dative_auto:
                    extracted_fields["applicantNameDative"] = dative_auto
                    logger.info(f"✅ Перегенерирован дательный падеж для [2.2]: {dative_auto} (из имени: {correct_name_for_dative})")
                else:
                    logger.warning(f"⚠️ Не удалось сгенерировать дательный падеж для: {name_for_dative}")
            else:
                logger.warning(f"⚠️ После удаления префиксов имя стало пустым: {correct_name_for_dative}")
        else:
            logger.warning(f"⚠️ Не найдено правильное имя должника для генерации дательного падежа [2.2]")
            logger.warning(f"  applicantName (ip_specific): {ip_specific_fields.get('applicantName')}")
            logger.warning(f"  debtorName (ip_specific): {ip_specific_fields.get('debtorName')}")
            logger.warning(f"  applicantName (extracted): {extracted_fields.get('applicantName')}")
            logger.warning(f"  debtorName (extracted): {extracted_fields.get('debtorName')}")



    def _maybe_upgrade_to_observation_collateral(self, extracted_fields, text, document_type, text_lower):
        """Доп. проверка после извлечения: ЮЛ + залог + наблюдение -> тип observation_collateral (+ поля залога). Возвращает (возможно обновлённый) document_type. Вынесено из analyze."""
        # Дополнительная проверка для observation_collateral после извлечения полей
        # Если это юридическое лицо с залогом и процедура наблюдения, но тип еще не определен
        if document_type == "rtk_application":
            entity_type = extracted_fields.get("entityType", "").lower()

            # ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА: документ считается залоговым ТОЛЬКО если есть формулировка "обеспеченное залогом"
            required_collateral_phrases = [
                r"обеспеченное\s+залогом",
                r"обеспечено\s+залогом",
                r"обеспечен\s+залогом",
                r"обеспечена\s+залогом",
                r"обеспечены\s+залогом",
                r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                r"обязательство.*обеспечен.*залогом",
                r"обязательства.*обеспечен.*залогом"
            ]
            has_required_collateral_phrase = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in required_collateral_phrases)

            # Дополнительные индикаторы залога (только если есть обязательная формулировка)
            has_collateral = False
            if has_required_collateral_phrase:
                has_collateral = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in [
                    r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                    r"что\s+подтверждается\s+договором\s+залога",
                    r"договор\s+залога\s+№"
                ])

            is_observation = any(keyword in text_lower for keyword in ["наблюден", "наблюдения", "процедура наблюдения"]) or \
                            entity_type == "legal" or \
                            (extracted_fields.get("procedureType") or "").lower() == "observation"

            # Не повышаем до observation_collateral, если в тексте есть явное «ИП ФИО»
            # в имени должника (та же проверка, что и при первичной классификации).
            has_ip_name = self._detect_ip_debtor_name(text)

            if entity_type == "legal" and has_collateral and is_observation and not has_ip_name:
                document_type = "observation_collateral"
                logger.info("Определен тип документа: observation_collateral (Наблюдение с залогом для ЮЛ после извлечения полей)")
                # Дополняем полями залога
                collateral_fields = self.extract_physical_collateral_fields(text)
                for key, value in collateral_fields.items():
                    if value:
                        extracted_fields[key] = value

                # Если предмет залога [1221] не найден, пытаемся извлечь через fallback метод
                if "mortgageCollateralDescription1221" not in extracted_fields or not extracted_fields.get("mortgageCollateralDescription1221"):
                    logger.info("🔍 Предмет залога [1221] не найден для observation_collateral, пробуем fallback метод...")
                    collateral_block = self._extract_mortgage_collateral_block(text)
                    if collateral_block:
                        extracted_fields["mortgageCollateralDescription1221"] = collateral_block
                        logger.info(f"✅ Извлечено mortgageCollateralDescription1221 через fallback метод: {collateral_block[:150]}...")

                extracted_fields["observationHasCollateral"] = "true"
        return document_type

    def _postprocess_mortgage_and_case_number(self, extracted_fields, text, document_type):
        """Постобработка ипотеки/залога (корректировка интерфейсных значений) и валидация номера дела («/ГОД» в конце, отсев доверенностей/договоров). Вынесено из analyze."""
        # Постобработка данных для ипотеки и документов с залогом - приводим интерфейс к корректным значениям
        if document_type == "mortgage_claim" or document_type == "competition_collateral":
            self._normalize_mortgage_interface_fields(extracted_fields, text)
            # Для конкурсного производства с залогом явно считаем должника юридическим лицом
            if document_type == "competition_collateral":
                extracted_fields["entityType"] = "legal"
            # Если есть ИНН финуправляющего — добавляем его в отображаемое имя
            manager_name_cc = extracted_fields.get("managerName")
            manager_inn_cc = extracted_fields.get("managerInn")
            if manager_name_cc and manager_inn_cc and "инн" not in manager_name_cc.lower():
                extracted_fields["managerName"] = f"{manager_name_cc.strip()} (ИНН {manager_inn_cc})"

        # Тип лица: текстовый фолбэк для определений суда без блока «Должник:»
        # (например, «…банкротом индивидуального предпринимателя Главы КФХ …»),
        # где имя должника — плейсхолдер. Делаем ДО рекомендаций, чтобы они
        # использовали уже скорректированный тип лица.
        if extracted_fields.get("entityType") not in ("kfh", "ip", "legal"):
            text_entity = self._entity_from_text(text)
            if text_entity:
                extracted_fields["entityType"] = text_entity
                if text_entity == "kfh":
                    extracted_fields["isKfh"] = True

        # Номер дела: оставляем только если это реальный номер судебного дела
        # («/ГОД» в конце). Отсекаем доверенности (№ЮЗБ/415-Д), договоры и пр.,
        # которые могли попасть жадными паттернами. В ипотечных исках на момент
        # подачи дела ещё нет — поле должно остаться пустым.
        _cn = extracted_fields.get("caseNumber")
        if _cn and not self._is_valid_case_number(_cn):
            # Хвост мог прилипнуть без пробела («…/2026Исх. Док.») — жадный класс
            # захватил заглавную букву после года. Спасаем канонический номер.
            _core = re.search(
                r"[А-ЯA-Z]?\d{1,4}[А-ЯA-Z]?[-–]\d{1,15}/(?:19|20)\d{2}",
                str(_cn).upper().replace("Ё", "Е"),
            )
            if _core:
                extracted_fields["caseNumber"] = _core.group(0)
            else:
                extracted_fields.pop("caseNumber", None)







    def _analyze_ip_collection(self, text, document_type):
        """Ветка анализа ИП-взыскания: extract_fields + слияние ip_specific_fields (без перезаписи ИНН/сумм), залог авто [1221], дательный падеж, обязательства. Возвращает extracted_fields. Вынесено из analyze."""
        # Используем основной extract_fields для ИП, чтобы получить все поля
        extracted_fields = self.extract_fields(text, "rtk_application")  # Используем rtk_application как базовый тип

        # Дополняем специфичными полями для ИП из extract_ip_enforcement_fields
        ip_specific_fields = self.extract_ip_enforcement_fields(text)
        logger.info(f"Извлеченные специфичные поля для ИП (взыскание): {list(ip_specific_fields.keys())}")
        logger.info(f"🔍 Значения полей [1000], [1001], [1004]:")
        logger.info(f"  creditAmount [1000]: {ip_specific_fields.get('creditAmount')}")
        logger.info(f"  creditTermMonths [1001]: {ip_specific_fields.get('creditTermMonths')}")
        logger.info(f"  debtSnapshotDate [1004]: {ip_specific_fields.get('debtSnapshotDate')}")

        for key, value in ip_specific_fields.items():
            if value:
                # ВАЖНО: Не перезаписываем ИНН и ОГРН, если они уже были извлечены из блока "Ответчик:" в основном цикле
                if key in ["inn", "ogrnip", "ogrn"]:
                    if key in extracted_fields and extracted_fields[key]:
                        logger.info(f"⚠️ Пропускаем перезапись {key} из ip_specific_fields (уже извлечен из блока Ответчик: {extracted_fields[key]})")
                        continue
                # Не перезаписываем уже найденные денежные поля основного извлечения,
                # чтобы не заносить шум из fallback-паттернов ip_specific_fields.
                if key in ["principalDebt13", "interest14", "forfeit15", "principalDebt", "interest", "forfeit", "totalDebt", "stateDuty16", "stateDuty"]:
                    if key in extracted_fields and extracted_fields[key]:
                        # Для госпошлины разрешаем обновить 0,00 -> ненулевое значение.
                        if key in ["stateDuty16", "stateDuty"]:
                            existing_amount = self._safe_amount_field(extracted_fields.get(key))
                            incoming_amount = self._safe_amount_field(value)
                            if existing_amount <= 0 < incoming_amount:
                                logger.info(
                                    f"🔁 Обновляем {key}: текущее значение {extracted_fields[key]} заменяется на ненулевое {value}"
                                )
                            else:
                                logger.info(f"⚠️ Пропускаем перезапись {key} из ip_specific_fields (уже есть корректное значение: {extracted_fields[key]})")
                                continue
                        else:
                            logger.info(f"⚠️ Пропускаем перезапись {key} из ip_specific_fields (уже есть корректное значение: {extracted_fields[key]})")
                            continue
                extracted_fields[key] = value
                logger.info(f"Установлено поле ИП {key}: {value}")

        # Для «Взыскание ИП залог авто» [1221] — описание авто (марка, модель, год, VIN и т.д.)
        if document_type == "ip_collection_collateral_auto":
            car_1221 = self._extract_car_collateral_1221(text)
            if car_1221:
                extracted_fields["mortgageCollateralDescription1221"] = car_1221
                logger.info(f"✅ Установлено mortgageCollateralDescription1221 (залог авто): {car_1221[:80]}...")

        # Перегенерация дательного падежа [2.2] (ИП)
        self._regenerate_ip_dative(extracted_fields, text, ip_specific_fields)

        # Извлекаем обязательства для ИП
        obligations = self.extract_obligations(text, extracted_fields)
        if obligations:
            extracted_fields['obligations'] = obligations
            logger.info(f"Добавлено {len(obligations)} обязательств для ИП (взыскание)")
        return extracted_fields

    def _analyze_legal_collection(self, text, document_type):
        """Ветка анализа взыскания с ЮЛ: extract_fields + данные о залоге (без перезаписи сумм), дательный падеж, обязательства. Возвращает extracted_fields. Вынесено из analyze."""
        # Используем основной extract_fields для ЮЛ, чтобы получить все поля
        extracted_fields = self.extract_fields(text, "rtk_application")  # Используем rtk_application как базовый тип

        # Для типов с залогом извлекаем только данные о залоге (НЕ перезаписываем суммы долга/процентов)
        if document_type in ("legal_collection_collateral", "legal_collection_collateral_auto"):
            # Извлекаем данные о залоге (аналогично ИП), но используем только нужные поля
            ip_specific_fields = self.extract_ip_enforcement_fields(text)
            logger.info(f"Извлеченные специфичные поля для ЮЛ с залогом: {list(ip_specific_fields.keys())}")

            # Только поля, связанные с залогом, которые нужно добавить для ЮЛ
            collateral_fields = [
                "ipCollateralContractNumber", "ipCollateralContractDate", "ipCollateralClaimAmount",
                "mortgageCollateralDescription1221", "contractNumber", "contractDate",
                "creditAmount", "creditTermMonths", "creditInterestRate", "creditPenaltyRate",
                "debtSnapshotDate", "courtName", "creditorName", "debtAmount"
            ]

            # Поля, которые НИКОГДА не перезаписываем для ЮЛ (они уже правильно извлечены в основном цикле)
            fields_to_preserve = [
                "inn", "ogrnip", "ogrn", "principalDebt13", "interest14", "forfeit15",
                "interest", "principalDebt", "totalDebt", "stateDuty16"
            ]

            for key, value in ip_specific_fields.items():
                if value:
                    # ВАЖНО: Не перезаписываем важные поля сумм, если они уже были извлечены в основном цикле
                    if key in fields_to_preserve:
                        if key in extracted_fields and extracted_fields[key]:
                            # Для госпошлины разрешаем обновление 0,00 -> ненулевое значение.
                            if key == "stateDuty16":
                                existing_amount = self._safe_amount_field(extracted_fields.get(key))
                                incoming_amount = self._safe_amount_field(value)
                                if existing_amount <= 0 < incoming_amount:
                                    logger.info(
                                        f"🔁 Обновляем {key} для ЮЛ с залогом: текущее значение "
                                        f"{extracted_fields[key]} заменяется на ненулевое {value}"
                                    )
                                else:
                                    logger.info(
                                        f"⚠️ Пропускаем перезапись {key} из ip_specific_fields "
                                        f"(уже извлечен в основном цикле: {extracted_fields[key]})"
                                    )
                                    continue
                            else:
                                logger.info(f"⚠️ Пропускаем перезапись {key} из ip_specific_fields (уже извлечен в основном цикле: {extracted_fields[key]})")
                                continue
                    # Госпошлину для ЮЛ с залогом сохраняем отдельно (может приходить из ip_specific_fields
                    # как корректное ненулевое значение, даже если в основном цикле было 0,00).
                    if key == "stateDuty16":
                        extracted_fields["stateDuty16"] = value
                        # Синхронизируем общее поле госпошлины с [16], чтобы генератор не получил 0,00.
                        extracted_fields["stateDuty"] = value
                        logger.info(f"Установлено поле ЮЛ с залогом {key}: {value}")
                    # Добавляем только поля, связанные с залогом или договором
                    elif key in collateral_fields:
                        extracted_fields[key] = value
                        logger.info(f"Установлено поле ЮЛ с залогом {key}: {value}")
                    else:
                        logger.debug(f"Пропущено поле {key} (не относится к залогу для ЮЛ)")

            # Для «Взыскание ЮЛ залог авто» [1221] — описание авто (марка, модель, год, VIN и т.д.)
            if document_type == "legal_collection_collateral_auto":
                car_1221 = self._extract_car_collateral_1221(text)
                if car_1221:
                    extracted_fields["mortgageCollateralDescription1221"] = car_1221
                    logger.info(f"✅ Установлено mortgageCollateralDescription1221 (залог авто): {car_1221[:80]}...")

            # Специальное извлечение процентов для ЮЛ с залогом: "просроченные проценты" или "проценты" после тире или без него
            interest_patterns = [
                r"просроченные\s+проценты\s*[–—-]\s*([0-9\s\u00a0\u202f,]+(?:[.,][0-9]+)?)\s*(?:руб(?:\.|лей)?|₽|р\.?)?",  # просроченные проценты – X
                r"просроченные\s+проценты[:\s]+([0-9\s,]+(?:[.,][0-9]+)?)\s*(?:руб|рублей|₽|р\.?)?",  # просроченные проценты: X или просроченные проценты X
                r"проценты\s*[–—-]\s*([0-9\s\u00a0\u202f,]+(?:[.,][0-9]+)?)\s*(?:руб(?:\.|лей)?|₽|р\.?)?",  # проценты – X
                r"проценты[:\s]+([0-9\s,]+(?:[.,][0-9]+)?)\s*(?:руб|рублей|₽|р\.?)?",  # проценты: X или проценты X
                r"([0-9\s,]+(?:[.,][0-9]+)?)\s*(?:руб|рублей|₽|р\.?)?\s*[–—-]\s*просроченные\s+проценты",  # X – просроченные проценты
                r"([0-9\s,]+(?:[.,][0-9]+)?)\s*(?:руб|рублей|₽|р\.?)?\s*[–—-]\s*проценты",  # X – проценты
            ]

            for pattern in interest_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    interest_value = match.group(1).strip()
                    # Очищаем от пробелов и форматируем
                    interest_value = re.sub(r'\s+', ' ', interest_value)
                    if interest_value:
                        extracted_fields["interest14"] = interest_value
                        extracted_fields["interest"] = interest_value
                        logger.info(f"✅ Перезаписано interest14 для ЮЛ с залогом из паттерна '{pattern[:50]}...': {interest_value}")
                        break

        # Извлекаем обязательства для ЮЛ
        obligations = self.extract_obligations(text, extracted_fields)
        if obligations:
            extracted_fields['obligations'] = obligations
            logger.info(f"Добавлено {len(obligations)} обязательств для ЮЛ (взыскание)")
        return extracted_fields

    def _analyze_ip_enforcement(self, text, document_type):
        """Ветка анализа ИП-исполнения (взыскание/реализация/реструктуризация): extract_fields + ip_specific, умерший, дательный падеж, обязательства. Возвращает extracted_fields. Вынесено из analyze."""
        # Используем основной extract_fields для ИП, чтобы получить все поля
        # Затем дополняем специфичными полями для ИП
        extracted_fields = self.extract_fields(text, "rtk_application")  # Используем rtk_application как базовый тип

        # Дополняем специфичными полями для ИП из extract_ip_enforcement_fields
        ip_specific_fields = self.extract_ip_enforcement_fields(text)
        logger.info(f"Извлеченные специфичные поля для ИП: {list(ip_specific_fields.keys())}")

        # Проверяем, является ли это процедурой "умерший" (проверяем текст напрямую)
        text_lower = text.lower()
        is_deceased = any(keyword in text_lower for keyword in ["умер", "умерший", "смерть", "смерти"])

        for key, value in ip_specific_fields.items():
            if value:
                # ВАЖНО: Не перезаписываем ИНН и ОГРН, если они уже были извлечены из блока "Ответчик:" в основном цикле
                if key in ["inn", "ogrnip", "ogrn"]:
                    if key in extracted_fields and extracted_fields[key]:
                        logger.info(f"⚠️ Пропускаем перезапись {key} из ip_specific_fields (уже извлечен из блока Ответчик: {extracted_fields[key]})")
                        continue
                # Специальная обработка для courtName в процедуре "умерший"
                if key == 'courtName' and is_deceased:
                    cleaned_value = self._clean_court_name_deceased(value)
                    if cleaned_value:
                        extracted_fields[key] = cleaned_value
                        logger.info(f"Установлено поле ИП {key} (очищено для умершего): {cleaned_value}")
                    else:
                        logger.info(f"Поле ИП {key} очищено до пустого значения, пропускаем")
                else:
                    # Всегда перезаписываем специфичные поля для ИП, даже если они уже есть
                    extracted_fields[key] = value
                    logger.info(f"Установлено поле ИП {key}: {value}")

        # Определяем наличие залога для ИП
        if document_type in ["ip_enforcement_statement_collateral", "ip_enforcement_realization_collateral",
                             "ip_enforcement_restructuring_collateral"]:
            extracted_fields["ipHasCollateral"] = "true"
        else:
            collateral_detected = self.detect_ip_collateral(text)
            extracted_fields["ipHasCollateral"] = "true" if collateral_detected else "false"

        # Извлекаем обязательства для ИП
        obligations = self.extract_obligations(text, extracted_fields)
        if obligations:
            extracted_fields['obligations'] = obligations
            logger.info(f"Добавлено {len(obligations)} обязательств для ИП")
        return extracted_fields

    def _analyze_physical_collateral(self, text, document_type):
        """Ветка анализа ФЛ/ЮЛ с залогом (реализация/реструктуризация/наблюдение/конкурс): extract_fields + поля залога, обязательства. Возвращает extracted_fields. Вынесено из analyze."""
        # Для ФЛ/ЮЛ с залогом в реализации/реструктуризации/наблюдении используем extract_fields и дополняем полями залога
        extracted_fields = self.extract_fields(text, "rtk_application")

        # Извлекаем поля залога (аналогично ИП, но без префикса ИП)
        collateral_fields = self.extract_physical_collateral_fields(text)
        logger.info(f"Извлеченные поля залога: {list(collateral_fields.keys())}")
        for key, value in collateral_fields.items():
            if value:
                extracted_fields[key] = value
                logger.info(f"Установлено поле залога {key}: {value}")

        # Если предмет залога [1221] не найден, пытаемся извлечь через fallback метод
        if "mortgageCollateralDescription1221" not in extracted_fields or not extracted_fields.get("mortgageCollateralDescription1221"):
            logger.info("🔍 Предмет залога [1221] не найден в extract_physical_collateral_fields, пробуем fallback метод...")
            collateral_block = self._extract_mortgage_collateral_block(text)
            if collateral_block:
                extracted_fields["mortgageCollateralDescription1221"] = collateral_block
                logger.info(f"✅ Извлечено mortgageCollateralDescription1221 через fallback метод: {collateral_block[:150]}...")

        if document_type == "observation_collateral":
            extracted_fields["observationHasCollateral"] = "true"
        else:
            extracted_fields["physicalHasCollateral"] = "true"

        # Извлекаем обязательства
        obligations = self.extract_obligations(text, extracted_fields)
        if obligations:
            extracted_fields['obligations'] = obligations
            logger.info(f"Добавлено {len(obligations)} обязательств для {document_type}")
        return extracted_fields


    def _drop_law_context_dates(self, fields: Dict[str, Any], text: str) -> None:
        """Удаляет даты, которые в исходном тексте стоят ТОЛЬКО в ссылках на закон/Пленум.

        Дата рождения и иные поля не затрагиваются. Если у даты есть хотя бы одно
        вхождение вне законного контекста — она сохраняется.
        """
        if not text:
            return
        for fname in self._LAW_DATE_FIELDS:
            val = fields.get(fname)
            if not val or not isinstance(val, str):
                continue
            dates = [d.strip() for d in val.split(",") if d.strip()]
            if not dates:
                continue
            kept = []
            for d in dates:
                occ = [m.start() for m in re.finditer(re.escape(d), text)]
                if occ and all(date_in_law_context(text, s, s + len(d)) for s in occ):
                    logger.info(f"Пропуск {fname} (дата в ссылке на закон): {d}")
                    continue
                kept.append(d)
            if kept:
                fields[fname] = ", ".join(kept)
            else:
                fields.pop(fname, None)










    # Типы ТС (многословные — раньше однословных, чтобы «грузовой тягач» не срезался
    # до «грузовой»). «автомобиль» тут НЕ тип, а метка предмета — не берём.
    _VEHICLE_TYPE_RE = (
        r"седельн\w+\s+тягач\w*|грузов\w+\s+тягач\w*|бортов\w+\s+грузов\w+|"
        r"грузов\w+|легков\w+|полуприцеп\w*|прицеп\w*|тягач\w*|автобус\w*|"
        r"самосвал\w*|фургон\w*|мотоцикл\w*|трактор\w*|экскаватор\w*|погрузчик\w*"
    )

    def _extract_vehicle_type(self, desc: str) -> Optional[str]:
        """Вид ТС (грузовой/полуприцеп/прицеп/тягач/…) для наименования залога-авто."""
        m = re.search(r"(" + self._VEHICLE_TYPE_RE + r")", desc, re.IGNORECASE)
        if m:
            t = re.sub(r"\s+", " ", m.group(1).strip().lower())
            return t[0].upper() + t[1:]
        return None

    def _extract_collateral_brand_model(self, desc: str) -> Optional[str]:
        """Марка+модель авто. Поддержка меток «Марка/Модель [ТС]:» и OCR «Мо дель»."""
        d = re.sub(r"мо\s+дель", "модель", desc, flags=re.IGNORECASE)  # OCR-склейка
        mk = re.search(r"марк[аиуе](?:\s*тс)?\s*[:：]\s*([A-Za-zА-Яа-яЁё0-9\- ]{1,30}?)\s*(?=[,;.]|модел|год|vin|кузов|$)", d, re.IGNORECASE)
        md = re.search(r"модел[ьи](?:\s*тс)?\s*[:：]\s*([A-Za-zА-Яа-яЁё0-9\- ]{1,30}?)\s*(?=[,;.]|год|vin|кузов|рама|$)", d, re.IGNORECASE)
        parts = []
        if mk and mk.group(1).strip():
            parts.append(mk.group(1).strip())
        if md and md.group(1).strip():
            parts.append(md.group(1).strip())
        return " ".join(parts) or None

    def _extract_freeform_make_model(self, desc: str, vtype: Optional[str], year: Optional[str]) -> Optional[str]:
        """Марка/модель без меток: «…, Грузовой ИЖ 27175 2009.» → «ИЖ 27175».
        Берём текст сразу после вида ТС до года/знака препинания."""
        if not vtype:
            return None
        m = re.search(
            re.escape(vtype) + r"\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9\- ]{1,40}?)"
            r"(?=\s*(?:19\d{2}|20[0-3]\d)\b|[,;.]|$)",
            desc, re.IGNORECASE,
        )
        if not m:
            return None
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        # Не марка, если это метка или сам вид ТС.
        if not s or re.match(r"(?i)марк|модел|vin|год|тс\b", s):
            return None
        return s

    def _extract_collateral_address(self, desc: str) -> Optional[str]:
        """Извлекает ПОЛНЫЙ адрес объекта недвижимости из описания залога.

        Берёт всё после метки адреса и обрезает хвост (кадастр, стоимость,
        год постройки, площадь и пр.), чтобы в адресе не было постороннего.
        """
        m = re.search(
            r"(?:по\s+адресу|адрес[уе]?|расположен\w*\s+по\s+адресу|местонахожд\w*)\s*[:：,]?\s*([^\n]+)",
            desc, re.IGNORECASE,
        )
        if not m:
            return None
        addr = re.sub(r"\s+", " ", m.group(1)).strip()
        # Обрезаем хвост: кадастр, стоимость, год постройки, площадь, этажность, VIN.
        addr = re.split(
            r"\s*,?\s*(?:\d{2}:\d{2}:\d{6,7}:\d+|кадастров\w+|залогов\w+\s+стоим|оценочн\w+\s+стоим|"
            r"рыночн\w+\s+стоим|начальн\w+\s+(?:продажн\w+\s+)?цен|стоимост\w+|год\s+постройки|"
            r"площад\w+|\d+[\s-]*этажн|\bVIN\b)",
            addr, flags=re.IGNORECASE,
        )[0]
        addr = addr.strip().rstrip(",;. ")
        return addr if len(addr) >= 6 else None

    def _extract_car_year(self, desc: str) -> Optional[str]:
        """Год выпуска авто: «год выпуска: 2011», «Год: 2020», «Год выпуска ТС: 1992»,
        «2011 г.в.» / «2011 года выпуска» либо хвостовой год «ИЖ 27175 2009.»."""
        m = re.search(r"год\w*(?:\s+выпуска)?(?:\s*тс)?\s*[:：]?\s*(19\d{2}|20[0-3]\d)", desc, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"\b(19\d{2}|20[0-3]\d)\s*(?:г\.?\s*в\.?|года?\s+выпуска)", desc, re.IGNORECASE)
        if m:
            return m.group(1)
        # Хвостовой год в свободном описании: «…ИЖ 27175 2009.» (без метки/«г.в.»).
        m = re.search(r"(?<!\d)(19\d{2}|20[0-3]\d)(?!\d)\s*[.;,]?\s*$", desc.strip())
        if m:
            return m.group(1)
        return None

    def _extract_plate(self, desc: str) -> Optional[str]:
        """Гос. рег. знак авто. Метка в любом виде: грз / гсз / г/н / гос (рег.) знак /
        государственный (регистрационный) знак / гос. номер / рег. знак."""
        m = re.search(
            r"(?:\bгрз\b|\bгсз\b|\bг\.?\s*/?\s*н\.?|"
            r"гос(?:ударственн\w+)?\.?\s*(?:рег(?:истрационн\w+)?\.?\s*)?(?:знак|номер)|"
            r"рег(?:истрационн\w+)?\.?\s*знак)"
            r"\s*[:：№]?\s*([А-ЯЁA-Z]{1,3}\s?\d{2,4}\s?[А-ЯЁA-Z]{0,3}\s?\d{0,3})",
            desc, re.IGNORECASE,
        )
        if m and re.search(r"\d", m.group(1)) and re.search(r"[А-ЯЁA-Z]", m.group(1)):
            return re.sub(r"\s+", "", m.group(1)).upper()
        return None

    def _extract_collateral_value(self, desc: str) -> Optional[str]:
        """Извлекает залоговую стоимость предмета залога (число)."""
        m = re.search(
            r"(?:залогов\w+\s+стоимост\w+|оценочн\w+\s+стоимост\w+|рыночн\w+\s+стоимост\w+|"
            r"стоимост\w+\s+(?:предмета\s+)?залога|начальн\w+\s+(?:продажн\w+\s+)?цен\w+|стоимост\w+)"
            r"\s*(?:залога|объекта)?\s*[:：]?\s*(?:в\s+размере\s+)?"
            r"([0-9][0-9\s  .,]*[0-9]|[0-9])\s*(?:руб|₽|р\.)",
            desc, re.IGNORECASE,
        )
        if m:
            num = re.sub(r"[\s  ]", "", m.group(1))
            return num
        return None

    # Фраза залоговой стоимости (для вырезания из описания «иного» залога).
    _VALUE_PHRASE_RE = (
        r"[,;.]?\s*(?:общ\w+\s+)?(?:залогов\w+\s+стоимост\w+|оценочн\w+\s+стоимост\w+|рыночн\w+\s+стоимост\w+|"
        r"стоимост\w+\s+(?:предмета\s+)?залога|начальн\w+\s+(?:продажн\w+\s+)?цен\w+|стоимост\w+)"
        r"\s*(?:залога|объекта)?\s*[:：]?\s*(?:в\s+размере\s+)?[0-9][0-9\s.,]*[0-9]?\s*(?:руб\w*|₽|р\.)"
    )

    def _strip_value_phrase(self, text: str) -> str:
        """Убирает фразу залоговой стоимости из текста (чтобы не дублировать в описании)."""
        return re.sub(self._VALUE_PHRASE_RE, "", text, flags=re.IGNORECASE).strip(" ,;.-—–")

    def _extract_other_object_name(self, desc: str) -> Optional[str]:
        """Наименование «иного» предмета залога: до первой запятой/двоеточия (там
        обычно начинаются атрибуты — «, страна изготовления:», «, находящееся по
        адресу:») либо по ключевому слову вида."""
        m = re.match(r"\s*([^:：,\n]{2,100}?)\s*[:：,]", desc)
        if m:
            name = m.group(1)
        else:
            km = re.search(
                r"(ценн\w+\s+бумаг\w*|акци\w+|облигаци\w+|вексел\w+|"
                r"дол[яюи]\s+в\s+уставн\w+\s+капитал\w*|дол[яюи]\s+в\s+праве\w*|"
                r"оборудовани\w*|товар\w*\s+в\s+оборот\w*|имуществ\w+\s+прав\w*\s+требовани\w*|"
                r"имуществ\w+\s+прав\w*|прав\w*\s+требовани\w*|\bпа[йи]\b)",
                desc, re.IGNORECASE,
            )
            name = km.group(1) if km else desc.split(",")[0][:40]
        name = self._strip_value_phrase(name).strip(" -—–,;.")
        return (name[0].upper() + name[1:]) if name else None

    def _extract_collateral_object_name(self, desc: str) -> Optional[str]:
        """Извлекает вид объекта недвижимости (дом / земельный участок / квартира …).

        Здание/помещение/дом и т.п. — если есть, это САМ объект (земельный участок
        под ним фигурирует лишь как «расположенное на земельном участке …»). Поэтому
        строения ищем первым проходом, землю — вторым."""
        m = re.search(
            r"(жил\w+\s+дом|нежил\w+\s+(?:помещени\w+|здани\w+)|"
            r"квартир\w+|комнат\w+|машино-?мест\w*|гараж\w*|нежил\w+\s+здани\w+|"
            r"здани\w+|строени\w+|сооружени\w+|помещени\w+|\bдом\b)",
            desc, re.IGNORECASE,
        )
        if not m:
            m = re.search(r"(земельн\w+\s+участ\w+)", desc, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            return name[0].upper() + name[1:]
        return None

    def _extract_all_collateral_items(self, text: str) -> List[str]:
        """Сканирует ВЕСЬ документ и собирает описания всех предметов залога.

        Залоги бывают у нескольких обязательств. Берём:
          - маркированные строки «- <дом/квартира/земельный участок/Автомобиль/марка …>»;
          - инлайн «…автотранспортное средство: <описание>».
        Каждое описание — до конца строки (со всеми атрибутами: VIN, год, грз, стоимость).
        """
        if not text:
            return []
        norm = text.replace("\xa0", " ").replace(" ", " ")
        items: List[str] = []
        bullet_re = re.compile(
            r"[-–—•]\s*((?:Автомобил\w*|марк[аи]\s*[:：]|жил\w*\s*дом|\bдом\b|квартир\w*|"
            r"земельн\w+\s+участ\w*|нежил\w*|помещени\w*|здани\w*|гараж\w*|машино-?мест\w*|"
            r"комнат\w*|строени\w*|сооружени\w*|"
            # «иное»: ценные бумаги, доли, оборудование, товары, имущественные права и т.п.
            r"ценн\w+\s+бумаг\w*|акци\w+|облигаци\w+|вексел\w+|дол[яюи]\s+в\s+(?:уставн|праве)|"
            r"оборудовани\w*|товар\w*\s+в\s+оборот\w*|имуществ\w+\s+прав\w*|прав\w*\s+требовани\w*|"
            r"\bпа[йи]\b)[^\n]*)",
            re.IGNORECASE,
        )
        for m in bullet_re.finditer(norm):
            s = m.group(1).strip().rstrip(" .,;")
            if len(s) >= 8:
                items.append(s)
        for m in re.finditer(r"(?:авто)?транспортн\w+\s+средств\w*\s*[:：]\s*([^\n]+)", norm, re.IGNORECASE):
            s = m.group(1).strip().rstrip(" .,;")
            if len(s) >= 8:
                items.append(s)
        # Формат договоров залога/ипотеки без буллетов: «…в залог передано следующее
        # [движимое] имущество: <предмет1 … стоимостью N руб.> <предмет2 … стоимостью
        # N руб.> Общая стоимость … составляет N руб.». Каждый предмет — до своей
        # «стоимостью N руб.»; строка «Общая стоимость … составляет …» — это итог, не
        # предмет (не содержит «стоимостью <число>» вплотную), поэтому не попадает.
        items.extend(self._extract_pledge_block_items(norm))
        return items

    def _extract_pledge_block_items(self, norm: str) -> List[str]:
        """Предметы залога из блоков «в залог передано следующее имущество: …».
        Возвращает описания предметов (каждое оканчивается на «стоимостью N руб.»)."""
        _val = r"стоимост\w+\s+[0-9][0-9\s.,]*[0-9]\s*руб"
        items: List[str] = []
        for bm in re.finditer(r"в\s+залог\s+переда\w+\s+", norm, re.IGNORECASE):
            head = norm[bm.end(): bm.end() + 5000]
            # Итемизированный список: «следующее [движимое] имущество: <предметы>».
            lm = re.match(r"следующее\s+[^:\n]{0,40}?имуществ\w*\s*[:：]", head, re.IGNORECASE)
            if lm:
                block = head[lm.end():]
                # Конец блока — итоговая строка «Общая стоимость … составляет … руб».
                endm = re.search(r"Общая\s+стоимост\w+.*?составляет.*?руб", block,
                                 re.IGNORECASE | re.DOTALL)
                if endm:
                    block = block[:endm.start()]
                buf = ""
                for line in block.split("\n"):
                    buf += " " + line.strip()
                    if re.search(_val, buf, re.IGNORECASE):
                        s = re.sub(r"\s+", " ", buf).strip(" .,;")
                        if len(s) >= 12 and "общая стоимост" not in s.lower():
                            items.append(s)
                        buf = ""
                continue
            # Сводная форма без перечня: «…[движимое] имущество … общей стоимостью N
            # руб.» (предметы вынесены в Приложение) — одна карточка «Иное».
            sm = re.match(
                r"([^:\n]{0,25}?имуществ\w*.{0,240}?общ\w+\s+" + _val + r")",
                head, re.IGNORECASE | re.DOTALL,
            )
            if sm:
                s = re.sub(r"\s+", " ", sm.group(1)).strip(" .,;")
                if len(s) >= 12:
                    items.append(s)
        return items

    def _collateral_dedupe_key(self, obj: Dict[str, Any]):
        """Ключ уникальности предмета залога (VIN для авто, кадастр/адрес для недвижимости)."""
        t = obj.get("collateralType")
        if t == "auto":
            return ("auto", (obj.get("vin") or obj.get("brandModel") or obj.get("description", "")[:60]).upper())
        if t == "real_estate":
            return ("re", (obj.get("cadastralNumber") or obj.get("address") or obj.get("description", "")[:60]).lower())
        # «Иное»: описания однотипных предметов (линия № 6 / № 7) совпадают в первых
        # символах — добавляем стоимость, чтобы разные предметы не схлопнулись.
        return ("other", obj.get("description", "")[:80].lower(), obj.get("collateralValue", ""))

    def _dedupe_collaterals(self, objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Убирает дубли предметов залога, оставляя наиболее заполненный."""
        def filled(o):
            return sum(1 for k in ("objectName", "collateralValue", "cadastralNumber",
                                   "address", "vin", "brandModel") if o.get(k))
        by_key: Dict[Any, Dict[str, Any]] = {}
        order: List[Any] = []
        for o in objs:
            key = self._collateral_dedupe_key(o)
            if key not in by_key:
                by_key[key] = o
                order.append(key)
            elif filled(o) > filled(by_key[key]):
                by_key[key] = o
        result = [by_key[k] for k in order]
        for i, o in enumerate(result):
            o["id"] = f"collateral-{i}"
        return result

    def _collateral_has_substance(self, obj: Dict[str, Any]) -> bool:
        """Проверяет, что предмет залога реальный (а не шаблонный «Предметом залога является …»).

        Недвижимость/транспорт — всегда реальны (по ключевым словам классификации).
        «Иное» — только если содержит реальный предмет: ценные бумаги, долю, оборудование,
        товары в обороте, имущественные права и т.п.
        """
        if obj.get("collateralType") in ("auto", "real_estate"):
            return True
        # «Иное» — это ВСЁ, что не недвижимость и не ТС (оборудование, линии, товары,
        # ценные бумаги, доли и т.п.). Реальный предмет ВСЕГДА имеет конкретную
        # залоговую стоимость (он так и извлекается из договора залога). Болванки
        # переизвлечения («Согласно Обзора судебной практики…», «Правовое обоснование
        # требований…», «Поттер Г.Д.») стоимости не имеют — отсекаются.
        if not obj.get("collateralValue"):
            return False
        name = (obj.get("objectName") or "").strip()
        if len(name) >= 8 and name.lower() != "иное":
            return True
        desc = (obj.get("description") or "").lower()
        return bool(re.search(
            r"ценн\w+\s+бумаг|акци\w|облигаци|вексел|дол[яюи]\s+в\s+(?:уставн|праве)|"
            r"оборудовани|товар\w*\s+в\s+оборот|имуществ\w+\s+прав|прав\w*\s+требовани|"
            r"\bпа[йи]\b|спецтехник|самоходн\w+\s+машин",
            desc,
        ))

    def _make_collateral_obj(self, idx: int, desc: str) -> Dict[str, Any]:
        """Создаёт объект залога с определённым типом и извлечёнными полями."""
        ctype = self._classify_collateral(desc)
        clip = desc if len(desc) < 200 else desc[:200]
        obj = {
            "id": f"collateral-{idx}", "description": desc, "collateralType": ctype,
            "objectName": "", "collateralValue": "", "cadastralNumber": "", "address": "",
            "vin": "", "brandModel": "", "otherDescription": "",
        }
        # Залоговая стоимость (для любого типа).
        val = self._extract_collateral_value(desc)
        if val:
            obj["collateralValue"] = val

        if ctype == "auto":
            vin = re.search(r"(?:VIN\s*[:：]?\s*)?\b([A-HJ-NPR-Z0-9]{17})\b", desc, re.IGNORECASE)
            if vin:
                obj["vin"] = vin.group(1).upper()
            vtype = self._extract_vehicle_type(desc)
            year = self._extract_car_year(desc)
            bm = self._extract_collateral_brand_model(desc)
            if not bm:  # марка/модель без меток: «…Грузовой ИЖ 27175 2009.»
                bm = self._extract_freeform_make_model(desc, vtype, year)
            if bm:
                obj["brandModel"] = bm
            # Наименование авто: «<Вид ТС> <Марка Модель>, <год> г.в., гос. знак…,
            # цвет…, кузов…». Вид ТС и марка/модель — «голова», остальное — атрибуты.
            head = " ".join(p for p in (vtype, bm) if p).strip()
            attrs = []
            if year:
                attrs.append(f"{year} г.в.")
            plate = self._extract_plate(desc)
            if plate:
                attrs.append(f"гос. знак {plate}")
            cm = re.search(r"цвет\s*[:：]?\s*([А-ЯЁа-яё\-]+)", desc, re.IGNORECASE)
            if cm:
                attrs.append(f"цвет {cm.group(1).lower()}")
            km = re.search(r"кузов\s*[№:：]?\s*([A-ZА-ЯЁ0-9\-]{4,})", desc, re.IGNORECASE)
            if km:
                attrs.append(f"кузов {km.group(1)}")
            name = (head + ", " if head and attrs else head) + ", ".join(attrs)
            obj["objectName"] = name.strip(" ,") or "Автомобиль"
        elif ctype == "real_estate":
            cad = re.search(r"(\d{2}:\d{2}:\d{6,7}:\d{1,6})", desc)
            if cad:
                obj["cadastralNumber"] = cad.group(1)
            addr = self._extract_collateral_address(desc)
            if addr:
                obj["address"] = addr
            # Наименование — вид объекта + доступные атрибуты (год постройки, площадь).
            parts = [self._extract_collateral_object_name(desc) or "Недвижимость"]
            yb = re.search(r"год\s+(?:постройки|возведения|строительства)\s*[:：]?\s*(\d{4})", desc, re.IGNORECASE)
            if yb:
                parts.append(f"год постройки {yb.group(1)}")
            am = re.search(r"площад\w*\s*[:：]?\s*([\d.,]+)\s*(?:кв\.?\s*м|м2|м²|кв\.?\s*метр\w*)", desc, re.IGNORECASE)
            if am:
                parts.append(f"площадь {am.group(1)} кв.м")
            fm = re.search(r"(\d+)[\s-]*этажн\w+", desc, re.IGNORECASE)
            if fm:
                parts.append(f"{fm.group(1)}-этажный")
            obj["objectName"] = ", ".join(parts)
        else:
            # «Иное»: наименование и стоимость — отдельными полями; в описание кладём
            # остаток (без дублирования наименования и стоимости).
            name = self._extract_other_object_name(desc)
            obj["objectName"] = name or "Иное"
            rest = re.sub(r"^\s*[-–—•]\s*", "", desc)  # срезаем ведущий маркер
            # Убираем ведущее наименование с двоеточием («Ценные бумаги: …» → «…»).
            mcolon = re.match(r"\s*[^:：\n]{2,60}[:：]\s*", rest)
            if mcolon:
                rest = rest[mcolon.end():]
            elif name and rest.lower().startswith(name.lower()):
                rest = rest[len(name):].lstrip(" :,-—–")
            obj["otherDescription"] = self._strip_value_phrase(rest)
        return obj

    def _is_car_collateral_document(self, text: str) -> bool:
        """Определяет наличие залога авто: связка «марка … (модель/VIN/год/кузов)»
        в любом месте текста (в т.ч. инлайн «…автотранспортное средство: Автомобиль, марка: …»)."""
        if not text:
            return False
        return bool(re.search(
            r"марк[аи]\s*[:：][^\n]{0,150}?(?:модель|vin|год\s+выпуска|кузов|рама)",
            text, re.IGNORECASE,
        ))

    def _extract_car_collateral_1221(self, text: str) -> Optional[str]:
        """
        Извлекает описание предмета залога [1221] для залога авто в формате:
        марка: Opel, модель: Astra, год выпуска: 2021, VIN: WP6AB2A45BLA52999
        Ищет предложение, начинающееся с «марка» и содержащее модель, год, VIN, кузов, рама.
        """
        if not text:
            return None
        normalized = text.replace('\u202f', ' ').replace('\xa0', ' ')
        # Связка «(автотранспортное средство:) (Автомобиль,) марка: …» до конца строки —
        # чтобы захватить и год выпуска, и VIN, и залоговую стоимость.
        prefix = r"(?:(?:авто)?транспортн\w+\s+средств\w*\s*[:：]?\s*)?(?:Автомобил\w*[,:\s]*)?"
        candidates = []
        for m in re.finditer(prefix + r"марк[аи]\s*[:：][^\n]+", normalized, re.IGNORECASE):
            block = re.sub(r'\s+', ' ', m.group(0)).strip().rstrip('.,; ')
            if len(block) >= 12 and re.search(r"модель|vin|год\s+выпуска|кузов|рама", block, re.IGNORECASE):
                candidates.append(block)
        if candidates:
            # Предпочитаем описание, где есть залоговая стоимость.
            for c in candidates:
                if re.search(r"стоимост", c, re.IGNORECASE):
                    return c
            return candidates[0]
        return None

    def detect_ip_collateral(self, text: str) -> bool:
        """
        Определяет, содержит ли заявление указание на залоговое имущество.
        """
        if not text:
            return False

        text_lower = text.lower()
        keywords = [
            "предмет залога",
            "заложенн",
            "залоговое имущество",
            "обращении взыскания на заложенное",
            "ипотек",
            "договор залога",
            "в залог"
        ]

        return any(keyword in text_lower for keyword in keywords)

    def extract_physical_collateral_fields(self, text: str) -> Dict[str, str]:
        """
        Извлекает поля залога для физических лиц (аналогично ИП, но без префикса ИП).
        """
        fields: Dict[str, str] = {}

        if not text:
            return fields

        normalized_text = text.replace('\u202f', ' ').replace('\xa0', ' ')

        def clean_numeric(value: str) -> str:
            cleaned = value.replace('\u202f', ' ').replace('\xa0', ' ')
            cleaned = re.sub(r'\s*(?:руб\.?|рублей|₽)\.?$', '', cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.strip()
            return cleaned

        def set_field(key: str, patterns, postprocess=None, flags=re.IGNORECASE | re.MULTILINE):
            for pattern in patterns:
                match = re.search(pattern, normalized_text, flags)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    value = value.strip()
                    value = self.clean_extracted_value(value)
                    if postprocess:
                        value = postprocess(value)
                    if value:
                        fields[key] = value
                        logger.info(f"Extracted {key}: {value}")
                        break

        # Фильтр для номера договора (аналогично ИП)
        def filter_contract_number(value):
            """Фильтрует некорректные значения для номера договора"""
            if not value:
                return None
            value = value.strip()
            if value.lower() in ["от", "none", "null", ""]:
                return None
            value = re.sub(r'^\s*от\s+', '', value, flags=re.IGNORECASE)
            value = re.sub(r'\s+от\s*$', '', value, flags=re.IGNORECASE)
            value = re.sub(r'от\s*\d+\s*$', '', value, flags=re.IGNORECASE)
            value = re.sub(r'от\s*\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*$', '', value, flags=re.IGNORECASE)
            return value.strip() if value.strip() else None

        # Номер договора залога [0005] - для ФЛ (используем те же поля, что и для ИП)
        set_field(
            "ipCollateralContractNumber",  # Используем то же поле, что и для ИП
            [
                r"что\s+подтверждается\s+договором\s+залога\s+№\s*([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)(?=\s+от\s+\d|\s+от\s*$|\s*\[|\s*$|\s*\.)",
                r"что\s+подтверждается\s+договором\s+залога[,\s]+([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)\s+от\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}",
                r"договором\s+залога\s+№\s*([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)(?=\s+от\s+\d|\s+от\s*$|\s*\[|\s*$|\s*\.)",
                r"договором\s+залога[,\s]+([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)\s+от\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}",
                r"В\s+качестве\s+обеспечения[^.]*?договором\s+залога\s+№\s*([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)(?=\s+от\s+\d|\s+от\s*$|\s*\[|\s*$|\s*\.)",
                r"В\s+качестве\s+обеспечения[^.]*?договором\s+залога[,\s]+([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)\s+от\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}",
                r"предоставил\s+в\s+залог[^.]*?договором\s+залога\s+№\s*([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)(?=\s+от\s+\d|\s+от\s*$|\s*\[|\s*$|\s*\.)",
                r"предоставил\s+в\s+залог[^.]*?договором\s+залога[,\s]+([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)\s+от\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}",
                r"договор\s+залога[:\s]*№\s*([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)(?=\s+от\s+\d|\s+от\s*$|\s*$|\s*\.)",
                r"договор\s+залога[^.]*?№\s*([А-ЯЁ0-9/-]+(?:[,\s\-]+[А-ЯЁ0-9/-]+)*?)(?=\s+от\s+\d|\s+от\s*$|\s*$|\s*\.)",
            ],
            postprocess=filter_contract_number
        )

        # Дата договора залога [0006]
        set_field(
            "ipCollateralContractDate",  # Используем то же поле, что и для ИП
            [
                r"что\s+подтверждается\s+договором\s+залога[,\s]+[А-ЯЁ0-9/-]+(?:\s+от|от)\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
                r"договором\s+залога[,\s]+[А-ЯЁ0-9/-]+(?:\s+от|от)\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
                r"договор\s+залога[:\s]*№?\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})",
                r"что\s+подтверждается\s+договором\s+залога[^.]*?от\s+(\d{1,2}[.,]\d{1,2}[.,]\d{4})"
            ]
        )

        # Сумма требований в реестре [0007]
        set_field(
            "ipCollateralClaimAmount",  # Используем то же поле, что и для ИП
            [
                r"Установить\s+требования[^.]*?в\s+размере\s+([0-9\s.,]+)\s*(?:руб|рублей|₽|р\.?)",
                r"требования[^.]*?кредиторов[^.]*?в\s+размере\s+([0-9\s.,]+)\s*(?:руб|рублей|₽|р\.?)",
                r"в\s+реестре\s+требований\s+кредиторов[^.]*?в\s+размере\s+([0-9\s.,]+)\s*(?:руб|рублей|₽|р\.?)",
                r"требования[^.]*?Публичного\s+акционерного\s+общества[^.]*?в\s+размере\s+([0-9\s.,]+)\s*(?:руб|рублей|₽|р\.?)"
            ],
            postprocess=clean_numeric
        )

        # Извлекаем описание предмета залога [1221] для ФЛ с залогом.
        # Только при наличии признаков залога — иначе ложный warning.
        has_collateral_markers = bool(re.search(r"договор\w*\s+залога|ипотек|предмет\s+залога|\[1221\]", text, re.IGNORECASE))
        if has_collateral_markers and "mortgageCollateralDescription1221" not in fields:
            logger.info(f"🔍 Ищем mortgageCollateralDescription1221 для ФЛ с залогом...")
            collateral_patterns = [
                r"что\s+подтверждается\s+договором\s+залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*([\s\S]+?)(?=Наличие\s+заложенного\s+имущества\s+подтверждается\s+выпиской\s+из\s+ЕГРН|Наличие\s+заложенного|\[1221\]|\.\s+[А-ЯЁ]|\n\s*\n|ПРОСИТ|По\s+состоянию|Сумма\s+к|В\s+результате|$)",
                r"подтверждается\s+договором\s+залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*([\s\S]+?)(?=Наличие\s+заложенного\s+имущества\s+подтверждается\s+выпиской\s+из\s+ЕГРН|Наличие\s+заложенного|\[1221\]|\.\s+[А-ЯЁ]|\n\s*\n|ПРОСИТ|По\s+состоянию|Сумма\s+к|В\s+результате|$)",
                r"В\s+качестве\s+обеспечения[^.]*?что\s+подтверждается\s+договором\s+залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*([\s\S]+?)(?=Наличие\s+заложенного\s+имущества\s+подтверждается\s+выпиской\s+из\s+ЕГРН|Наличие\s+заложенного|\[1221\]|\.\s+[А-ЯЁ]|\n\s*\n|ПРОСИТ|По\s+состоянию|Сумма\s+к|В\s+результате|$)",
                r"договором\s+залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*([\s\S]+?)(?=Наличие\s+заложенного|\[1221\]|\.\s+[А-ЯЁ]|\n\s*\n|ПРОСИТ|По\s+состоянию|Сумма\s+к|В\s+результате|$)",
                r"залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*([^\n]+(?:\n[^\n]+)*?)(?=Наличие\s+заложенного|\[1221\]|\.\s+[А-ЯЁ]|\n\s*\n|ПРОСИТ|По\s+состоянию|Сумма\s+к|В\s+результате|$)",
                r"залога\s+№\s*[А-ЯЁ0-9/-]+(?:\s+от|от)\s+\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*:\s*([^\n\.]+(?:\.[^\n]*)?)(?=Наличие|\[1221\]|\n\s*\n|ПРОСИТ|По\s+состоянию|Сумма\s+к|В\s+результате|$)"
            ]
            set_field("mortgageCollateralDescription1221", collateral_patterns)
            if "mortgageCollateralDescription1221" in fields:
                extracted_value = fields['mortgageCollateralDescription1221']
                logger.info(f"✅ Извлечено mortgageCollateralDescription1221 ({len(extracted_value)} символов): {extracted_value[:150]}...")
            else:
                logger.warning(f"⚠️ mortgageCollateralDescription1221 НЕ найдено!")

        return fields






    def _get_recommended_acts(self, document_type: str, extracted_fields: Dict[str, Any], text: str) -> Dict[str, Any]:
        """
        Определяет рекомендуемые акты на основе типа документа, типа лица и наличия залога.

        Returns:
            Словарь с рекомендациями: {
                "entityType": "individual" | "legal" | "ip" | "kfh",
                "collateralOption": "collateral" | "collateral_auto" | "no_collateral",
                "recommendedActIds": ["act_id1", "act_id2", ...]
            }
        """
        # Определяем тип лица. Приоритет: КФХ → ЮЛ (ООО/Общество) → ИП (должник/ответчик ИП ФИО) → ФЛ
        entity_type_raw = (extracted_fields.get("entityType") or "").lower()
        is_kfh = extracted_fields.get("isKfh", False)
        text_lower_for_entity = text.lower()[:5000]  # блок должника обычно в начале

        if is_kfh or entity_type_raw == "kfh":
            recommended_entity_type = "kfh"
        elif entity_type_raw in ("legal", "юридическое лицо", "юрлицо"):
            recommended_entity_type = "legal"
        elif entity_type_raw == "ip":
            recommended_entity_type = "ip"
        elif entity_type_raw == "individual":
            # Доверяем извлечённому типу ФЛ — не переопределяем по тексту (в тексте может быть ООО/ПАО кредитора)
            recommended_entity_type = "individual"
        else:
            # Тип не определён при извлечении — проверяем по тексту только блок должника (не кредитора)
            debtor_name = (extracted_fields.get("debtorName") or extracted_fields.get("applicantName") or "").lower()
            legal_in_debtor_name = (
                "ооо" in debtor_name or "оао" in debtor_name or "пао" in debtor_name or "зао" in debtor_name or
                "общество с ограниченной ответственностью" in debtor_name or "ограниченной ответственностью" in debtor_name or
                bool(re.search(r"\b(ооо|оао|пао|зао)\b", debtor_name))
            )
            legal_in_text = (
                "ооо" in text_lower_for_entity or
                "общество с ограниченной ответственностью" in text_lower_for_entity or
                "ограниченной ответственностью" in text_lower_for_entity or
                bool(re.search(r"\bооо\b", text_lower_for_entity)) or
                bool(re.search(r"\b(оао|пао|зао)\b", text_lower_for_entity))
            )
            if legal_in_debtor_name or (legal_in_text and not re.search(r"[а-яё]{2,}\s+[а-яё]{2,}\s+[а-яё]{2,}", debtor_name)):
                recommended_entity_type = "legal"
            elif re.search(r"(?:должник|ответчик)[:\s]*\n?\s*ип\s+[а-яё]", text_lower_for_entity) or re.search(r"индивидуальный предприниматель\s+[а-яё]", text_lower_for_entity):
                recommended_entity_type = "ip"
            else:
                recommended_entity_type = "individual"

        # Определяем наличие залога
        has_collateral = False
        has_auto_collateral = False

        # ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА: документ считается залоговым ТОЛЬКО если есть формулировка "обеспеченное залогом"
        # или похожие формулировки, которые явно указывают на залог (ограничиваем расстояние, чтобы не ловить случайные совпадения)
        required_collateral_phrases = [
            r"обеспеченное\s+залогом",
            r"обеспечено\s+залогом",
            r"обеспечен\s+залогом",
            r"обеспечена\s+залогом",
            r"обеспечены\s+залогом",
            r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
            r"обязательство[^.]{0,120}?обеспечен[^.]{0,30}?залогом",
            r"обязательства[^.]{0,120}?обеспечен[^.]{0,30}?залогом"
        ]

        # Проверяем наличие обязательной формулировки о залоге
        has_required_collateral_phrase = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in required_collateral_phrases)

        # Если нет обязательной формулировки, документ НЕ может быть залоговым
        if not has_required_collateral_phrase:
            logger.info("Документ НЕ содержит обязательной формулировки 'обеспеченное залогом' - залог не определяется")
            # Устанавливаем no_collateral, но продолжаем определять рекомендуемые акты
            has_collateral = False
            has_collateral_fields = False
            has_collateral_text = False
        else:
            # Если обязательная формулировка есть, проверяем дополнительные индикаторы
            # Проверяем поля залога в извлеченных данных (не считаем залогом "Кому выдана [ФИО]" — это не описание залога)
            _collateral_desc = (extracted_fields.get("mortgageCollateralDescription1221") or "").strip()
            _valid_collateral_desc = bool(_collateral_desc and not re.match(r"^Кому\s+выдана\s+", _collateral_desc, re.IGNORECASE))
            has_collateral_fields = bool(
                extracted_fields.get("ipCollateralContractNumber") or
                extracted_fields.get("ipCollateralContractDate") or
                _valid_collateral_desc or
                extracted_fields.get("physicalHasCollateral") == "true" or
                extracted_fields.get("observationHasCollateral") == "true" or
                extracted_fields.get("ipHasCollateral") == "true"
            )

            # Проверяем различные индикаторы залога в тексте
            collateral_indicators = [
                r"В\s+качестве\s+обеспечения\s+исполнения\s+обязательств\s+кредитному\s+договору\s+Заемщик\s+предоставил\s+в\s+залог\s+Банку",
                r"что\s+подтверждается\s+договором\s+залога",
                r"договор\s+залога\s+№",
                r"предоставил\s+в\s+залог",
                r"предоставляет\s+в\s+залог"
            ]

            has_collateral_text = any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in collateral_indicators)

            # Используем либо поля, либо текст (но только если есть обязательная формулировка)
            has_collateral = has_collateral_fields or has_collateral_text

        # Проверяем наличие авто в залоге
        auto_indicators = [
            r"автомобил",
            r"транспортное\s+средство",
            r"vin",
            r"марка.*модель",
            r"гос\.?\s*номер"
        ]

        # Проверяем поля авто в извлеченных данных
        has_auto_fields = bool(
            extracted_fields.get("vin") or
            extracted_fields.get("brandModel")
        )

        if has_collateral:
            has_auto_collateral = has_auto_fields or any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in auto_indicators)

        # Определяем тип залога
        if has_auto_collateral:
            recommended_collateral_option = "collateral_auto"
        elif has_collateral:
            recommended_collateral_option = "collateral"
        else:
            recommended_collateral_option = "no_collateral"

        # Определяем рекомендуемые акты на основе типа документа
        recommended_act_ids = []
        text_lower = text.lower()

        # Определяем процедуру из типа документа или текста
        is_realization = "realization" in document_type or "реализац" in text_lower
        is_restructuring = "restructuring" in document_type or "реструктур" in text_lower
        is_observation = "observation" in document_type or "наблюден" in text_lower
        is_competition = "competition" in document_type or "конкурсн" in text_lower

        # Базовые акты для включения в РТК (если это заявление о включении)
        if document_type == "rtk_application" or "включ" in text_lower or "ртк" in text_lower:
            recommended_act_ids.append("final_rtk_inclusion")
            recommended_act_ids.append("acceptance_definition")

        # Для реализации
        if is_realization:
            recommended_act_ids.append("final_realization")
            if recommended_collateral_option != "no_collateral":
                recommended_act_ids.append("acceptance_no_motion_no_duty_collateral")
            else:
                recommended_act_ids.append("acceptance_definition")

        # Для реструктуризации
        if is_restructuring:
            recommended_act_ids.append("final_restructuring")
            if recommended_collateral_option != "no_collateral":
                recommended_act_ids.append("acceptance_no_motion_no_duty_collateral")
            else:
                recommended_act_ids.append("acceptance_definition")

        # Для наблюдения (только не для физлиц — ФЛ не бывает процедура наблюдение/конкурс)
        if is_observation and recommended_entity_type != "individual":
            recommended_act_ids.append("final_observation")
            if recommended_collateral_option != "no_collateral":
                recommended_act_ids.append("acceptance_no_motion_no_duty_collateral")
            else:
                recommended_act_ids.append("acceptance_definition")

        # Для конкурсного производства (только не для физлиц)
        if is_competition and recommended_entity_type != "individual":
            recommended_act_ids.append("final_competition")
            if recommended_collateral_option != "no_collateral":
                recommended_act_ids.append("acceptance_no_motion_no_duty_collateral")
            else:
                recommended_act_ids.append("acceptance_definition")

        # Для ИП с залогом
        if recommended_entity_type == "ip" and recommended_collateral_option != "no_collateral":
            if "realization" in document_type:
                recommended_act_ids.append("final_realization")
            elif "restructuring" in document_type:
                recommended_act_ids.append("final_restructuring")
            recommended_act_ids.append("acceptance_no_motion_no_duty_collateral")

        # Для ИП без залога
        if recommended_entity_type == "ip" and recommended_collateral_option == "no_collateral":
            if "realization" in document_type:
                recommended_act_ids.append("final_realization")
            elif "restructuring" in document_type:
                recommended_act_ids.append("final_restructuring")
            recommended_act_ids.append("acceptance_definition")

        # Для КФХ (всегда наблюдение)
        if recommended_entity_type == "kfh":
            recommended_act_ids.append("final_observation")
            if recommended_collateral_option != "no_collateral":
                recommended_act_ids.append("acceptance_no_motion_no_duty_collateral")
            else:
                recommended_act_ids.append("acceptance_definition")

        # Для ЮЛ без залога (наблюдение по умолчанию)
        if recommended_entity_type == "legal" and recommended_collateral_option == "no_collateral" and not is_realization and not is_restructuring:
            recommended_act_ids.append("final_observation")
            recommended_act_ids.append("acceptance_definition")

        # ИП — не предлагаем конкурсный акт
        if recommended_entity_type == "ip":
            recommended_act_ids = [act_id for act_id in recommended_act_ids if act_id != "final_competition"]

        # Физлицо — не предлагаем наблюдение и конкурсное производство
        if recommended_entity_type == "individual":
            recommended_act_ids = [act_id for act_id in recommended_act_ids if act_id not in ("final_observation", "final_competition")]

        # Убираем дубликаты, сохраняя порядок
        recommended_act_ids = list(dict.fromkeys(recommended_act_ids))

        logger.info(f"Рекомендации: entityType={recommended_entity_type}, collateralOption={recommended_collateral_option}, acts={recommended_act_ids}")

        return {
            "entityType": recommended_entity_type,
            "collateralOption": recommended_collateral_option,
            "recommendedActIds": recommended_act_ids
        }

    def find_date_near_contract(self, text: str, contract_number: str) -> str:
        """
        Ищет дату рядом с номером договора
        """
        def _is_plausible_date(date_str: str) -> bool:
            m = re.match(r'^(\d{1,2})[.,](\d{1,2})[.,](\d{4})$', date_str or "")
            if not m:
                return False
            day = int(m.group(1))
            month = int(m.group(2))
            year = int(m.group(3))
            return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100

        # 1) Приоритет: конструкции "DD.MM.YYYY ... заключен договор № CONTRACT"
        direct_pattern = rf'(?<!\d)(\d{{1,2}}[.,]\d{{1,2}}[.,]\d{{4}})(?!\d)[\s\S]{{0,220}}?(?:заключ[её]н[ао]?|заключили)[\s\S]{{0,120}}?договор[^\n]{{0,80}}?№\s*{re.escape(contract_number)}'
        direct_match = re.search(direct_pattern, text, re.IGNORECASE)
        if direct_match:
            direct_date = direct_match.group(1)
            if _is_plausible_date(direct_date):
                return direct_date

        # 2) Фолбэк: ищем дату рядом с каждым вхождением номера договора
        for contract_match in re.finditer(re.escape(contract_number), text, re.IGNORECASE):
            start = max(0, contract_match.start() - 300)
            end = min(len(text), contract_match.end() + 300)
            context = text[start:end]
            date_pattern = r'(?<!\d)(\d{1,2}[.,]\d{1,2}[.,]\d{4})(?!\d)'
            for date_match in re.finditer(date_pattern, context):
                candidate = date_match.group(1)
                if _is_plausible_date(candidate):
                    return candidate

        return ''


    def detect_obligation_type(self, text: str, contract_number: str) -> str:
        """
        Определяет тип обязательства по контексту
        """
        # Ищем контекст вокруг номера договора
        context_pattern = rf'.{{0,100}}{re.escape(contract_number)}.{{0,100}}'
        context_match = re.search(context_pattern, text, re.IGNORECASE)

        local_type = 'Договор'
        if context_match:
            context = context_match.group(0).lower()
            # Сравниваем по основам слов, т.к. в тексте склонённые формы
            # («кредитному договору», «договора залога», «займа»).
            # Тип определяет САМ договор: «кредитный договор» с обеспечением
            # остаётся кредитным (залог — отдельный блок). «Договор залога» —
            # только по явной формулировке, а не по любому упоминанию «залог».
            # 2 самых частых типа — кредитный договор и кредитная карта.
            if 'карт' in context and ('кредит' in context or 'эмисси' in context):
                local_type = 'Кредитная карта'
            elif 'эмисси' in context:  # эмиссионный контракт = выпуск кредитной карты
                local_type = 'Кредитная карта'
            elif 'кредитн' in context:
                local_type = 'Кредитный договор'
            elif 'займ' in context:
                local_type = 'Договор займа'
            elif 'поручительств' in context:
                local_type = 'Договор поручительства'
            elif 'договор залога' in context or 'договора залога' in context or 'договором залога' in context:
                local_type = 'Договор залога'
            elif 'ссуд' in context:
                local_type = 'Договор ссуды'

        # Если по локальному контексту тип не уточнён (договор назван просто
        # «договор» — форма Совкомбанка), берём явное поле «Вид обязательства:
        # <Кредит/Заём/Поручительство>» из документа.
        if local_type == 'Договор':
            vm = re.search(
                r'вид\s+обязательств\w*[:\s]*\n?\s*([A-Za-zА-Яа-яЁё]+)',
                text, re.IGNORECASE)
            if vm:
                v = vm.group(1).lower()
                if 'кредит' in v:
                    local_type = 'Кредитный договор'
                elif 'залог' in v:
                    local_type = 'Договор залога'
                elif v.startswith('за'):  # заём / займ
                    local_type = 'Договор займа'
                elif 'поручит' in v:
                    local_type = 'Договор поручительства'

        return local_type

    def calculate_confidence(self, document_type: Optional[str], extracted_fields: Dict[str, str], text: str) -> float:
        """
        Рассчитывает уверенность в результатах анализа
        """
        if not extracted_fields:
            return 0.0

        # Базовые поля для РТК заявления
        if document_type == "ip_enforcement_statement" or document_type == "ip_enforcement_statement_collateral":
            required_fields = [
                "applicantName", "inn", "ogrnip", "creditAmount", "principalDebt13"
            ]
        else:
            required_fields = [
                "applicantName", "courtName", "caseNumber", "debtAmount"
            ]

        # Подсчитываем заполненные обязательные поля
        filled_required = sum(1 for field in required_fields if field in extracted_fields)

        # Базовый уровень уверенности
        base_confidence = filled_required / len(required_fields)

        # Дополнительные факторы
        additional_factors = 0.0

        # Качество извлечения имен
        if "applicantName" in extracted_fields:
            name = extracted_fields["applicantName"]
            if len(name.split()) >= 3:  # ФИО должно содержать минимум 3 части
                additional_factors += 0.1

        # Качество извлечения сумм и дат в зависимости от типа документа
        if document_type == "ip_enforcement_statement" or document_type == "ip_enforcement_statement_collateral":
            amount = (
                extracted_fields.get("totalDebt")
                or extracted_fields.get("creditAmount")
                or extracted_fields.get("principalDebt13")
            )
            if amount and re.match(r'^\d+(?:[.,]\d+)?$', amount.replace(' ', '')):
                additional_factors += 0.1

            contract_date = extracted_fields.get("contractDate")
            if contract_date and re.match(r'^\d{1,2}[.,]\d{1,2}[.,]\d{4}$', contract_date):
                additional_factors += 0.1
        else:
            if "debtAmount" in extracted_fields:
                amount = extracted_fields["debtAmount"]
                if re.match(r'^\d+$', amount.replace(' ', '')):
                    additional_factors += 0.1

            if "applicationDate" in extracted_fields:
                date = extracted_fields["applicationDate"]
                if re.match(r'^\d{1,2}[.,]\d{1,2}[.,]\d{4}$', date):
                    additional_factors += 0.1

        # Общая уверенность
        total_confidence = min(base_confidence + additional_factors, 1.0)

        return round(total_confidence, 2)

    def get_page_count(self, file_path: str) -> int:
        """
        Получает количество страниц в документе (.docx или .pdf).
        """
        try:
            suffix = Path(file_path).suffix.lower()
            if suffix == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                return max(1, len(reader.pages))
            doc = Document(file_path)
            return max(1, len(doc.paragraphs) // 20)
        except Exception:
            return 1

    def validate_field(self, field_name: str, value: str, field_type: str) -> bool:
        """
        Валидирует извлеченное поле
        """
        if not value or len(value.strip()) < 2:
            return False

        if field_type == "date":
            # Проверяем формат даты
            date_pattern = r'^\d{1,2}[.,]\d{1,2}[.,]\d{4}$'
            return bool(re.match(date_pattern, value))

        elif field_type == "amount":
            # Проверяем, что это число
            amount_pattern = r'^\d+$'
            return bool(re.match(amount_pattern, value.replace(' ', '')))

        elif field_type == "person_name":
            # Проверяем, что это ФИО (минимум 2 слова)
            return len(value.split()) >= 2

        return True
