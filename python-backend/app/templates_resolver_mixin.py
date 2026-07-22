# -*- coding: utf-8 -*-
"""Резолверы шаблонов document_generator (вынос без изменения поведения).

Все методы _get_*_templates и _map_selected_acts_to_templates по входным
признакам (процедура, тип лица, залог, выбранные акты) возвращают набор
{логическое_имя: {"name", "path", "order"}}. Единственная внешняя зависимость —
self._templates_root() (остаётся в DocumentGenerator). Поведение 1-в-1 под gen-golden.
"""
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TemplatesResolverMixin:

    @staticmethod
    def _is_fns_creditor(data: Dict[str, Any]) -> bool:
        """Заявитель/кредитор — уполномоченный орган (ФНС). Признак — creditorName
        начинается с «ФНС» (совпадает с фронтовым isFnsCreditor: «ФНС России»,
        «ФНС России в лице …»)."""
        name = str(data.get("creditorName") or "").strip().upper()
        return name.startswith("ФНС")

    @staticmethod
    def _is_self_bankruptcy(data: Dict[str, Any]) -> bool:
        """Самобанкротство — заявление подаёт сам должник. Признак —
        selectedApplicationKind ∈ {self, self_bankruptcy} (фронтовый ApplicationKind='self')."""
        kind = str(data.get("selectedApplicationKind") or data.get("applicationKind") or "").strip().lower()
        return kind in ("self", "self_bankruptcy")

    @staticmethod
    def _fns_has_second_queue(data: Dict[str, Any]) -> bool:
        """Есть ли у ФНС-заявления суммы 2-й очереди (fnsQ2*). Если да — берём
        шаблон «2-я и 3-я очередь», иначе «3-я очередь»."""
        def _num(v) -> float:
            try:
                return float(str(v).replace("\xa0", "").replace(" ", "").replace(",", ".") or 0)
            except (TypeError, ValueError):
                return 0.0
        suffixes = ("Total", "Arrears", "Penalties", "Forfeit", "Ndfl",
                    "Insurance", "LoanDebt", "LoanDuty", "Commission")
        return any(_num(data.get(f"fnsQ2{s}")) != 0 for s in suffixes)

    def _find_docx_by_name(self, dir_path: Path, *substrings: str) -> Optional[Path]:
        """Ищет в папке первый .docx, чьё имя содержит ВСЕ подстроки (регистронезависимо).
        Устойчиво к неудобным именам файлов (пробелы/подчёркивания/регистр)."""
        if not dir_path.exists():
            return None
        subs = [s.lower() for s in substrings]
        try:
            for candidate in sorted(dir_path.glob("*.docx")):
                low = candidate.name.lower()
                if all(s in low for s in subs):
                    return candidate
        except Exception:
            return None
        return None

    def _resolve_self_bankruptcy_act(self, act_id: str, act_ids: List[str], data: Dict[str, Any]):
        """Роутинг актов самобанкротства (заявление подаёт сам должник).

        Папки: самобанкротство/{реализ|реструктуриз}. Матрица 2×2:
        процедура (реализ/реструктуриз) × акт (принятие / признание банкротом).
        Процедуру берём из выбранного финального акта (final_restructuring →
        реструктуризация, иначе реализация) либо из procedureTypeRaw.
        Возвращает (ключ, путь, человекочитаемое имя) или None.
        """
        root_dir = self._templates_root()
        base = root_dir / "самобанкротство"

        proc_raw = str(data.get("procedureTypeRaw") or data.get("procedureType") or "").lower()
        is_restr = ("final_restructuring" in act_ids) or ("реструк" in proc_raw)
        sub = "реструктуриз" if is_restr else "реализ"
        proc_dir = base / sub

        if act_id == "acceptance_definition":
            path = self._find_docx_by_name(proc_dir, "принятии")
            return ("self_acceptance", path, "Определение о принятии (самобанкрот)") if path else None
        if act_id == "final_realization" and not is_restr:
            path = self._find_docx_by_name(proc_dir, "признали")
            return ("self_final", path, "Решение о признании банкротом (самобанкрот, реализация)") if path else None
        if act_id == "final_restructuring" and is_restr:
            path = self._find_docx_by_name(proc_dir, "признали")
            return ("self_final", path, "Определение о признании банкротом (самобанкрот, реструктуризация)") if path else None
        return None

    def _resolve_fns_act(self, act_id: str, entity_type: str, data: Dict[str, Any]):
        """Роутинг актов ФНС (уполномоченный орган).

        Папки: ФНС/{«2-я и 3-я очередь»|«3-я очередь»}. Вариант очереди выбираем
        авто: есть суммы 2-й очереди → «2-я и 3-я», иначе «3-я». Внутри «3-я очередь»
        включенка различается по типу лица: ЮЛ → файл «ЮЛ» (маркеры [2]/[13]),
        ФЛ → «налоговая» (маркеры [2.1]/[34.3]).
        Обрабатываем: final_rtk_inclusion (ВКЛ в РТК, включенка-резолютивка) и
        final_restructuring (реструктуризация — признание банкротом).
        Возвращает (ключ, путь, имя) или None.
        """
        root_dir = self._templates_root()
        fns = root_dir / "ФНС"
        has_q2 = self._fns_has_second_queue(data)
        dir_2_3 = fns / "2-я и 3-я очередь"
        dir_3 = fns / "3-я очередь"

        if act_id == "final_rtk_inclusion":
            if has_q2:
                path = self._find_docx_by_name(dir_2_3, "вкл", "резолютивка")
            elif entity_type == "legal":
                path = self._find_docx_by_name(dir_3, "юл")
            else:
                path = self._find_docx_by_name(dir_3, "включенка", "резолютивка", "налоговая")
            return ("fns_inclusion", path, "ФНС: включение в РТК (резолютивка)") if path else None

        if act_id == "final_restructuring":
            if has_q2:
                path = self._find_docx_by_name(dir_2_3, "реструк")
            else:
                path = self._find_docx_by_name(dir_3, "реструк", "признание")
            return ("fns_restructuring", path, "ФНС: реструктуризация (признание банкротом)") if path else None
        return None

    def _resolve_deceased_act(self, act_id: str, data: Dict[str, Any]):
        """Роутинг актов «умерший» (ФЛ, selectedDebtorStatus == deceased) при выборе актов.
        Возвращает (ключ, путь, имя) или None."""
        root_dir = self._templates_root()
        deceased_dir = root_dir / "умерший"

        if act_id == "acceptance_definition":
            path = deceased_dir / "Принятие заявления о призании должника банкротом умерший.docx"
            return ("acceptance", path, "Определение о принятии (умерший)")
        if act_id == "final_realization":
            path = deceased_dir / "Решение Умерший старый.docx"
            return ("final_realization", path, "Решение реализация (умерший)")
        return None

    def _get_templates_for_procedure(self, procedure_type: str) -> Dict[str, Dict[str, Any]]:
        """Возвращает набор шаблонов для указанного типа процедуры (ВКЛ в РТК без залога)."""
        templates_dir = Path(__file__).parent.parent / "templates"
        root_dir = self._templates_root()
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
                    deceased_dir / "Решение Умерший старый.docx",
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
                realization_dir / "Реализация ВКЛ несколько договоров.docx",
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
        root_dir = self._templates_root()

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
            # Без залога: ИП использует те же акты РТК-включения, что и физлица
            # (тексты содержат слово "должник" — заменяется на "индивидуальный
            # предприниматель" в replace_document_data через _apply_ip_debtor_wording).
            base_dir = root_dir / "шаблоны актов без залогов"
            if procedure_type == "restructuring":
                no_collateral_dir = base_dir / "физ реструк ВКЛ в РТК"
                templates = {
                    "acceptance": entry(
                        "Реструктуризация принятие РТК",
                        no_collateral_dir / "Реструктуризация принятие РТК.docx",
                        1
                    ),
                    "decision": entry(
                        "Реструктуризация ВКЛ",
                        no_collateral_dir / "Реструктуризация ВКЛ.docx",
                        2
                    ),
                    "resolution": entry(
                        "Резолютивка ВКЛ реструктуризация",
                        no_collateral_dir / "Резолютивка ВКЛ реструктуризация.docx",
                        3
                    )
                }
            else:  # realization по умолчанию
                no_collateral_dir = base_dir / "физ реализация ВКЛ в РТК"
                templates = {
                    "acceptance": entry(
                        "Реализация принятие РТК",
                        no_collateral_dir / "Реализация принятие РТК.docx",
                        1
                    ),
                    "decision": entry(
                        "Реализация ВКЛ",
                        no_collateral_dir / "Реализация ВКЛ несколько договоров.docx",
                        2
                    ),
                    "resolution": entry(
                        "Резолютивка ВКЛ реализация",
                        no_collateral_dir / "Резолютивка ВКЛ реализация.docx",
                        3
                    )
                }
            procedure_label = "реструктуризация" if procedure_type == "restructuring" else "реализация"
            logger.info(f"ℹ️ Используются акты РТК-включения физлиц для ИП {procedure_label} (без залога).")

        for info in templates.values():
            logger.info(f"📁 Шаблон: {info['name']} -> {info['path'].absolute()} (существует: {info['path'].exists()})")

        return templates

    def _get_ip_collection_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для искового заявления о взыскании с ИП.
        Генерирует 2 акта: "Принятие иска о взыскании с ИП" и "Решение взыскание с ИП".
        """
        root_dir = self._templates_root()
        collection_dir = root_dir / "Взыскания ИП + Залог"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            logger.info(f"📁 Шаблон взыскания ИП: {name} -> {path.absolute()} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        templates = {
            "acceptance": entry(
                "Принятие иска о взыскании с ИП",
                collection_dir / "Принятие иска о взыскании с ИП.docx",
                1
            ),
            "decision": entry(
                "Решение взыскание с ИП",
                collection_dir / "Решение взыскание с ИП.docx",
                2
            )
        }

        logger.info("⚖️ Используются шаблоны для искового заявления о взыскании с ИП.")
        return templates

    def _get_ip_collection_collateral_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для искового заявления о взыскании с ИП с залогом.
        Генерирует 2 акта: "Принятие иска о взыскании с ИП Залог" и "Решение о взысканнии с ИП залог".
        """
        root_dir = self._templates_root()
        collection_dir = root_dir / "Взыскания ИП + Залог" / "Взыскаие ИП залог"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            logger.info(f"📁 Шаблон взыскания ИП с залогом: {name} -> {path.absolute()} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        templates = {
            "acceptance": entry(
                "Принятие иска о взыскании с ИП Залог",
                collection_dir / "Принятие иска о взыскании с ИП Залог.docx",
                1
            ),
            "decision": entry(
                "Решение о взысканнии с ИП залог",
                collection_dir / "Решение о взысканнии с ИП залог.docx",
                2
            )
        }

        logger.info("⚖️ Используются шаблоны для искового заявления о взыскании с ИП с залогом.")
        return templates

    def _get_ip_collection_collateral_auto_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для искового заявления о взыскании с ИП залог авто.
        Маркер [1221] — описание авто (марка, модель, год, VIN и т.д.).
        """
        root_dir = self._templates_root()
        collection_dir = root_dir / "Взыскание ИП залог авто"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            logger.info(f"📁 Шаблон взыскания ИП залог авто: {name} -> {path.absolute()} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        templates = {
            "acceptance": entry(
                "Принятие иска о взыскании с ИП залог авто",
                collection_dir / "Принятие иска о взыскании с ИП Залог авто.docx",
                1
            ),
            "decision": entry(
                "Решение о взыскании с ИП залог авто",
                collection_dir / "Решение о взысканнии с ИП залог.docx",
                2
            )
        }

        logger.info("⚖️ Используются шаблоны для искового заявления о взыскании с ИП залог авто.")
        return templates

    def _get_legal_collection_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для искового заявления о взыскании с ЮЛ.
        Генерирует 2 акта: "Принятие иска о взыскании с ЮЛ" и "Решение о взыскании с ЮЛ".
        """
        root_dir = self._templates_root()
        collection_dir = root_dir / "Взыскание ЮЛ"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            logger.info(f"📁 Шаблон взыскания ЮЛ: {name} -> {path.absolute()} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        templates = {
            "acceptance": entry(
                "Принятие иска о взыскании с ЮЛ",
                collection_dir / "Принятие иска о взыскании с ЮЛ.docx",
                1
            ),
            "decision": entry(
                "Решение о взыскании с ЮЛ",
                collection_dir / "Решение о взыскании с ЮЛ.docx",
                2
            )
        }

        logger.info("⚖️ Используются шаблоны для искового заявления о взыскании с ЮЛ.")
        return templates

    def _get_legal_collection_collateral_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для искового заявления о взыскании с ЮЛ с залогом.
        Генерирует 2 акта: "Принятие иска о взыскании с ЮЛ Залог" и "Решение о взыскании с ЮЛ Залог".
        """
        root_dir = self._templates_root()
        collection_dir = root_dir / "ЮЛ взыскание залог"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            logger.info(f"📁 Шаблон взыскания ЮЛ с залогом: {name} -> {path.absolute()} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        templates = {
            "acceptance": entry(
                "Принятие иска о взыскании с ЮЛ Залог",
                collection_dir / "Принятие иска о взыскании с ЮЛ Залог.docx",
                1
            ),
            "decision": entry(
                "Решение о взыскании с ЮЛ Залог",
                collection_dir / "Решение о взыскании с ЮЛ Залог.docx",
                2
            )
        }

        logger.info("⚖️ Используются шаблоны для искового заявления о взыскании с ЮЛ с залогом.")
        return templates

    def _get_legal_collection_collateral_auto_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для искового заявления о взыскании с ЮЛ залог авто.
        Генерирует 2 акта: "Принятие иска о взыскании с ЮЛ Залог авто" и "Решение о взыскании с ЮЛ Залог авто".
        Маркер [1221] — описание авто (марка, модель, год, VIN и т.д.).
        """
        root_dir = self._templates_root()
        collection_dir = root_dir / "взыскание ЮЛ залог авто"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            logger.info(f"📁 Шаблон взыскания ЮЛ залог авто: {name} -> {path.absolute()} (существует: {path.exists()})")
            return {"name": name, "path": path, "order": order}

        templates = {
            "acceptance": entry(
                "Принятие иска о взыскании с ЮЛ Залог авто",
                collection_dir / "Принятие иска о взыскании с ЮЛ Залог авто.docx",
                1
            ),
            "decision": entry(
                "Решение о взыскании с ЮЛ Залог авто",
                collection_dir / "Решение о взыскании с ЮЛ Залог авто.docx",
                2
            )
        }

        logger.info("⚖️ Используются шаблоны для искового заявления о взыскании с ЮЛ залог авто.")
        return templates

    def _get_physical_collateral_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для ФЛ с залогом в реализации.
        Использует те же шаблоны, что и для ИП с залогом.
        """
        root_dir = self._templates_root()

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
        root_dir = self._templates_root()

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
        root_dir = self._templates_root()
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
                "Решение о введении реализации имущества (заемщик)",
                "решение реализ заемщик.docx",
                3
            )
        }

    def _get_initiation_legal_templates(self, contest_type: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для инициирования банкротства юридического лица.
        """
        root_dir = self._templates_root()
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
                "!О введении конкурсное отсутствующий.docx",
                2
            )
        elif contest_type == "liquidation":
            templates["competition"] = entry(
                "О введении конкурсное (ликвидируемый)",
                "!О введении конкурсное ликвидируемый.docx",
                2
            )

        return templates

    def _get_kfh_observation_templates(self, has_collateral: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает шаблоны для КФХ (наблюдение / ВКЛ в РТК), с залогом или без.
        """
        root_dir = self._templates_root()
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
        root_dir = self._templates_root()
        base_dir = root_dir / "ипотека"

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

    def _map_selected_acts_to_templates(self, selected_acts_ids: str, entity_type: str, collateral_option: str, data: Dict[str, Any]):
        """
        Маппит выбранные пользователем акты на реальные шаблоны документов.

        Args:
            selected_acts_ids: Строка с ID выбранных актов через запятую
            entity_type: Тип лица (individual, legal, ip, kfh)
            collateral_option: Тип залога (collateral, collateral_auto, no_collateral)
            data: Данные для генерации

        Returns:
            (templates, unresolved_act_ids) — словарь шаблонов для генерации и список
            ID актов, для которых ветки маппинга нет вообще. Раньше такие ID молча
            проглатывались циклом; вызывающий код обязан сообщить о них пользователю,
            а не подменять выбор стандартным комплектом.
        """
        if not selected_acts_ids:
            return {}, []

        root_dir = self._templates_root()
        base_dir = root_dir / "шаблоны актов без залогов"
        # Папка с промежуточными/особыми судебными актами
        new_acts_dir = root_dir / "промежуточные_особые"
        # Залог: обычный залог — папка "Залог"; залог авто — папка "Залог авто" (если есть)
        has_collateral = collateral_option in ('collateral', 'collateral_auto')
        is_auto_collateral = collateral_option == 'collateral_auto'
        collateral_dir = root_dir / ("Залог авто" if is_auto_collateral else "Залог")
        # Для залога авто может не быть подпапок Реализация/Наблюдение — тогда используем "Залог"
        if is_auto_collateral and not (collateral_dir / "Реализация").exists():
            collateral_dir = root_dir / "Залог"

        def entry(name: str, path: Path, order: int) -> Dict[str, Any]:
            return {"name": name, "path": path, "order": order}

        def _docx_xml_upper(path: Path) -> str:
            try:
                with zipfile.ZipFile(path) as z:
                    return z.read("word/document.xml").decode("utf-8", "ignore").upper()
            except Exception:
                return ""

        def _pick_docx_by_keywords(dir_path: Path, must_have: List[str]) -> Optional[Path]:
            """Подбор DOCX по содержимому (если имя файла отличается от ожидаемого)."""
            try:
                candidates = sorted(dir_path.glob("*.docx"))
            except Exception:
                return None

            for candidate in candidates:
                xml_up = _docx_xml_upper(candidate)
                if xml_up and all(k in xml_up for k in must_have):
                    return candidate
            return None

        def _pick_docx_by_keywords_multi(dir_path: Path, keyword_lists: List[List[str]]) -> Optional[Path]:
            """Пробует по очереди несколько наборов ключевых слов; возвращает первый найденный DOCX."""
            if not dir_path.exists():
                return None
            for must_have in keyword_lists:
                found = _pick_docx_by_keywords(dir_path, must_have)
                if found is not None:
                    return found
            return None

        def _resolve_competition_dir() -> Path:
            """Папка для конкурсных актов ЮЛ без залога. Ищет по имени, если стандартная не найдена."""
            default = base_dir / "юр конкурсное ВКЛ в РТК"
            if default.exists():
                return default
            try:
                for sub in base_dir.iterdir():
                    if sub.is_dir() and "конкурс" in sub.name.lower():
                        # Проверяем, что в папке есть хотя бы один .docx
                        if any(sub.glob("*.docx")):
                            return sub
            except Exception:
                pass
            return default

        def _rtk_inclusion_path(variant: str, for_entity: str, collateral: bool):
            """Путь к акту включения в РТК (final_rtk_inclusion) по варианту процедуры.
            Общая точка для явного variant-блока и no-variant fallback — раньше эти пять
            путей были прописаны в двух местах и рисковали разъехаться при правках."""
            if variant == 'realization':
                if collateral:
                    return collateral_dir / "Реализация" / "Реализация ВКЛ Залог.docx", "Определение ВКЛ в РТК (реализация с залогом)"
                return base_dir / "физ реализация ВКЛ в РТК" / "Реализация ВКЛ несколько договоров.docx", "Определение ВКЛ в РТК (реализация)"
            if variant == 'restructuring':
                if collateral:
                    return collateral_dir / "Реструктуризация" / "Реструктуризация ВКЛ Залог.docx", "Определение ВКЛ в РТК (реструктуризация с залогом)"
                return base_dir / "физ реструк ВКЛ в РТК" / "Реструктуризация ВКЛ.docx", "Определение ВКЛ в РТК (реструктуризация)"
            if variant == 'competition':
                if collateral:
                    return collateral_dir / "Конкурсное" / "Конкурсное ВКЛ в РТК Залог.docx", "Определение ВКЛ в РТК (конкурсное с залогом)"
                return base_dir / "юр инициир набл + конкурс" / "Конкурсное_ВКЛ_в_РТК (без залога).docx", "Определение ВКЛ в РТК (конкурсное)"
            if variant == 'observation':
                if for_entity == "kfh":
                    if collateral:
                        return root_dir / "КФХ" / "Наблюдение КФХ Залог.docx", "Определение ВКЛ в РТК (наблюдение КФХ, залог)"
                    return root_dir / "КФХ" / "Наблюдение КФХ.docx", "Определение ВКЛ в РТК (наблюдение КФХ)"
                if collateral:
                    return collateral_dir / "Наблюдение" / "Наблюдение ВКЛ в РТК  Залог.docx", "Определение ВКЛ в РТК (наблюдение с залогом)"
                return base_dir / "юр ВКЛ в РТК наблюдение" / "Наблюдение ВКЛ в РТК.docx", "Определение ВКЛ в РТК (наблюдение)"
            return None, None

        def _acceptance_definition_path(for_entity: str, collateral: bool, app_kind: str):
            """Путь к «Определению о принятии» по контексту (тип лица, залог,
            инициирование/ВКЛ, статус ЮЛ). Самобанкрот/ФНС/умерший уже отсечены
            pre-routing-резолверами выше по циклу — сюда они не попадают."""
            if for_entity == "kfh":
                return root_dir / "КФХ" / "Принятие иницирование КФХ.docx", "Определение о принятии"

            debtor_status = str(data.get("selectedDebtorStatus") or data.get("debtorStatus") or "").strip().lower()
            if for_entity == "legal":
                if not collateral and debtor_status in ("liquidation", "absent"):
                    return base_dir / "юр инициир набл + конкурс" / "О принятии заявления.docx", "Определение о принятии"
                is_observation = ("final_observation" in act_ids) or (data.get("final_rtk_inclusion_variant") == "observation")
                if collateral:
                    if is_observation:
                        return collateral_dir / "Наблюдение" / "Принятие РТК наблюдение.docx", "Определение о принятии"
                    return collateral_dir / "Конкурсное" / "Принятие РТК конкурсное (Копия).docx", "Определение о принятии"
                return base_dir / "юр ВКЛ в РТК наблюдение" / "!Принятие РТК наблюдение.docx", "Определение о принятии"

            # individual / ip
            is_restructuring = ("final_restructuring" in act_ids) or (data.get("final_rtk_inclusion_variant") == "restructuring")
            if collateral:
                if app_kind == "other":
                    return root_dir / "Залог" / "принятие иниц залог недвига.docx", "Определение о принятии"
                if is_restructuring:
                    return collateral_dir / "Реструктуризация" / "Реструктуризация принятие РТК Залог.docx", "Определение о принятии"
                return collateral_dir / "Реализация" / "Реализация принятие РТК Залог.docx", "Определение о принятии"
            if app_kind == "other":
                return base_dir / "физ иниц рестр + реал" / "Принятие заявления о призании должника банкротом.docx", "Определение о принятии"
            if is_restructuring:
                return base_dir / "физ реструк ВКЛ в РТК" / "Реструктуризация принятие РТК.docx", "Определение о принятии"
            return base_dir / "физ реализация ВКЛ в РТК" / "Реализация принятие РТК.docx", "Определение о принятии"

        def _short_text_path(procedure: str, collateral: bool) -> Path:
            """Путь к «короткому тексту» (резолютивке) по процедуре + залогу — ОДИН общий
            на генерацию. Для конкурсного и наблюдения-с-залогом резолютивки пока нет —
            возвращаем ожидаемый путь (файла нет → генератор выдаст «нет шаблона»)."""
            if collateral:
                if procedure == 'realization':
                    return collateral_dir / "Реализация" / "Резолютивка ВКЛ реализация Залог (+ наблюдение).docx"
                if procedure == 'restructuring':
                    return collateral_dir / "Реструктуризация" / "Резолютивка ВКЛ реструктуризация Залог.docx"
                if procedure == 'observation':
                    return collateral_dir / "Наблюдение" / "Резолютивка ВКЛ наблюдение Залог.docx"
                return collateral_dir / "Конкурсное" / "Резолютивка ВКЛ конкурсное Залог.docx"
            if procedure == 'realization':
                return base_dir / "физ реализация ВКЛ в РТК" / "Резолютивка ВКЛ реализация.docx"
            if procedure == 'restructuring':
                return base_dir / "физ реструк ВКЛ в РТК" / "!Резолютивка ВКЛ реструктуризация.docx"
            if procedure == 'observation':
                return base_dir / "юр ВКЛ в РТК наблюдение" / "Наблюдение ВКЛ в РТК (Резолютивка).docx"
            return base_dir / "юр инициир набл + конкурс" / "Резолютивка ВКЛ конкурсное.docx"

        # Дедуп с сохранением порядка: повтор одного ID не должен считаться
        # нерезолвленным на второй итерации (проверка ниже смотрит на прирост templates).
        act_ids: List[str] = []
        for raw_act_id in selected_acts_ids.split(','):
            act_id = raw_act_id.strip()
            if act_id and act_id not in act_ids:
                act_ids.append(act_id)

        templates = {}
        unresolved: List[str] = []
        order = 1

        # ФНС (уполномоченный орган) и самобанкротство — отдельные наборы шаблонов.
        # Роутим их раньше стандартной логики; если спец-резолвер вернул шаблон —
        # используем его, иначе падаем в общую ветку ниже.
        is_fns = self._is_fns_creditor(data)
        is_self = self._is_self_bankruptcy(data)
        is_deceased = str(data.get("selectedDebtorStatus") or data.get("debtorStatus") or "").strip().lower() == "deceased"

        for act_id in act_ids:
            templates_before = len(templates)

            if is_self:
                resolved = self._resolve_self_bankruptcy_act(act_id, act_ids, data)
                if resolved:
                    key, path, name = resolved
                    templates[key] = entry(name, path, order)
                    order += 1
                    continue
            if is_fns:
                resolved = self._resolve_fns_act(act_id, entity_type, data)
                if resolved:
                    key, path, name = resolved
                    templates[key] = entry(name, path, order)
                    order += 1
                    continue
            if is_deceased:
                resolved = self._resolve_deceased_act(act_id, data)
                if resolved:
                    key, path, name = resolved
                    templates[key] = entry(name, path, order)
                    order += 1
                    continue

            # Финальные СА (строго по выбранному залогу и типу лица)
            if act_id == 'final_realization':
                if has_collateral:
                    templates[act_id] = entry(
                        "Реализация ВКЛ Залог" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Реализация" / "Реализация ВКЛ Залог.docx",
                        order
                    )
                else:
                    # Без залога: "Решение реализация" — акт инициирования (решение о
                    # введении реализации), не путать с final_rtk_inclusion (акт включения
                    # в РТК — отдельный документ, см. ветку final_rtk_inclusion ниже).
                    templates[act_id] = entry(
                        "Решение о введении реализации имущества (заемщик)",
                        base_dir / "физ иниц рестр + реал" / "решение реализ заемщик.docx",
                        order
                    )
                order += 1
            elif act_id == 'final_competition':
                # "Решение конкурсное" — акт введения конкурсного производства, не путать
                # с final_rtk_inclusion (акт включения в РТК — отдельный документ).
                # Различаем ликвидируемый/отсутствующий по selectedDebtorStatus.
                debtor_status = str(data.get("selectedDebtorStatus") or data.get("debtorStatus") or "").strip().lower()
                if has_collateral:
                    competition_collateral_dir = collateral_dir / "Конкурсное" if not is_auto_collateral else (root_dir / "Залог" / "Конкурсное")
                    if debtor_status == "absent":
                        template_path = competition_collateral_dir / "О введении конкурсное отсутствующий (залог).docx"
                    else:
                        template_path = competition_collateral_dir / "О введении конкурсное ликвидируемый (залог).docx"
                    templates[act_id] = entry("Решение конкурсное" + (" (авто)" if is_auto_collateral else ""), template_path, order)
                else:
                    initiation_legal_dir = base_dir / "юр инициир набл + конкурс"
                    if debtor_status == "absent":
                        template_path = initiation_legal_dir / "!О введении конкурсное отсутствующий.docx"
                    elif debtor_status == "liquidation":
                        template_path = initiation_legal_dir / "!О введении конкурсное ликвидируемый.docx"
                    else:
                        # Статус не указан явно — подбор по ключевым словам как последняя линия обороны.
                        d = _resolve_competition_dir()
                        preferred = d / "Решение конкурсное.docx"
                        if preferred.exists():
                            template_path = preferred
                        else:
                            template_path = _pick_docx_by_keywords_multi(d, [
                                ["РЕШЕНИЕ", "КОНКУРС", "ПРОИЗВОДСТВА"],
                                ["РЕШЕНИЕ", "КОНКУРС", "ЗАВЕРШЕНИИ"],
                                ["РЕШЕНИЕ", "КОНКУРС"]
                            ])
                        if template_path is None and initiation_legal_dir.exists():
                            template_path = _pick_docx_by_keywords_multi(initiation_legal_dir, [
                                ["РЕШЕНИЕ", "КОНКУРС", "ПРОИЗВОДСТВА"],
                                ["РЕШЕНИЕ", "КОНКУРС"]
                            ])
                        if template_path is None:
                            template_path = preferred if preferred.exists() else (d / "Решение конкурсное.docx")
                    templates[act_id] = entry("Решение конкурсное", template_path, order)
                order += 1
            elif act_id == 'final_restructuring':
                # "Определение реструктуризация" — акт инициирования (введение процедуры),
                # не путать с final_rtk_inclusion (акт включения в РТК, отдельный документ).
                if has_collateral:
                    templates[act_id] = entry(
                        "Определение о введении реструктуризации долгов (заемщик)" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Реструктуризация" / "Определение о введении реструктуризации долгов (заемщик) (залог).docx",
                        order
                    )
                else:
                    templates[act_id] = entry(
                        "Определение о введении реструктуризации долгов (заемщик)",
                        base_dir / "физ иниц рестр + реал" / "Определение о введении реструктуризации ЗАЕМЩИК.docx",
                        order
                    )
                order += 1
            elif act_id == 'final_observation':
                # "Определение Наблюдение" — акт введения процедуры наблюдения, не путать
                # с final_rtk_inclusion (акт включения в РТК — отдельный документ).
                if entity_type == "kfh":
                    if has_collateral:
                        templates[act_id] = entry(
                            "Наблюдение КФХ Залог",
                            root_dir / "КФХ" / "Наблюдение КФХ Залог.docx",
                            order
                        )
                    else:
                        templates[act_id] = entry(
                            "Наблюдение КФХ",
                            root_dir / "КФХ" / "Наблюдение КФХ.docx",
                            order
                        )
                elif has_collateral:
                    templates[act_id] = entry(
                        "Определение Наблюдение (залог)" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Наблюдение" / "Принятие РТК наблюдение (залог).docx",
                        order
                    )
                else:
                    templates[act_id] = entry(
                        "Определение Наблюдение",
                        base_dir / "юр ВКЛ в РТК наблюдение" / "Наблюдение_ЮрЛицо.docx",
                        order
                    )
                order += 1
            elif act_id == 'final_rtk_inclusion':
                # Определение ВКЛ в РТК (акт включения в реестр — отдельный документ от
                # final_realization/restructuring/observation/competition, см. выше).
                rtk_variant = data.get("final_rtk_inclusion_variant")

                if rtk_variant == 'registry':
                    templates['rtk_registry'] = entry(
                        "Определение ВКЛ в РТК зареестр",
                        new_acts_dir / "внести зареестр.docx",
                        order
                    )
                else:
                    variant = rtk_variant if rtk_variant in ('realization', 'restructuring', 'competition', 'observation') else None
                    if variant is None:
                        # Вариант не указан: по типу лица — ЮЛ/КФХ наблюдение, ФЛ/ИП реализация
                        variant = 'observation' if entity_type in ('legal', 'kfh') else 'realization'
                    template_path, label = _rtk_inclusion_path(variant, entity_type, has_collateral)
                    if template_path is not None:
                        templates['rtk_inclusion'] = entry(label, template_path, order)
                order += 1

            # Принятие (по типу лица/залогу/инициирование-vs-ВКЛ — см. _acceptance_definition_path)
            elif act_id == 'acceptance_definition':
                application_kind = str(data.get("selectedApplicationKind") or data.get("applicationKind") or "").strip().lower()
                path, label = _acceptance_definition_path(entity_type, has_collateral, application_kind)
                templates['acceptance'] = entry(label, path, order)
                order += 1
            elif act_id == 'acceptance_no_motion_no_duty':
                templates['acceptance_no_motion'] = entry(
                    "Определение Б/Д нет ГП",
                    new_acts_dir / "внести Обездвижка" / "Определение БД нет ГП.docx",
                    order
                )
                order += 1
            elif act_id == 'acceptance_no_motion_no_duty_collateral':
                templates['acceptance_no_motion_collateral'] = entry(
                    "Определение Б/Д нет ГП залог",
                    new_acts_dir / "внести Обездвижка" / "Определение БД не гп залог.docx",
                    order
                )
                order += 1
            elif act_id == 'acceptance_no_motion_other':
                reason = data.get('acceptance_no_motion_other_reason', '')
                for_parties = data.get('acceptance_no_motion_other_forParties', '')
                templates['acceptance_no_motion_other'] = entry(
                    "Определение Б/Д иное",
                    new_acts_dir / "Определение БД иное.docx",
                    order
                )
                order += 1
            elif act_id == 'acceptance_after_no_motion':
                templates['acceptance_after_no_motion'] = entry(
                    "Принятие после Б/Д",
                    new_acts_dir / "принятие после БД.docx",
                    order
                )
                order += 1

            # Промежуточные
            elif act_id == 'intermediate_postponement':
                reason = data.get('intermediate_postponement_reason', '')
                for_parties = data.get('intermediate_postponement_forParties', '')
                templates['postponement'] = entry(
                    "Отложение",
                    new_acts_dir / "внести отложка" / "отложение.docx",
                    order
                )
                order += 1
            elif act_id == 'intermediate_return':
                reason = data.get('intermediate_return_reason', '')
                for_parties = data.get('intermediate_return_forParties', '')
                templates['return'] = entry(
                    "Возврат (РТК ГП)",
                    new_acts_dir / "внести Возврат" / "возврат ртк ГП.docx",
                    order
                )
                order += 1
            elif act_id == 'intermediate_extend_no_motion':
                templates['extend_no_motion'] = entry(
                    "Продление Б/Д",
                    new_acts_dir / "продление БД.docx",
                    order
                )
                order += 1
            elif act_id == 'intermediate_extend_simplified':
                templates['extend_simplified'] = entry(
                    "Продление упрощёнка",
                    new_acts_dir / "внести отложка" / "продление упрощенка.docx",
                    order
                )
                order += 1
            elif act_id == 'intermediate_simplified_to_main':
                templates['simplified_to_main'] = entry(
                    "Переход из упрощёнки в основное производство",
                    new_acts_dir / "внести Назначение после упрощенки" / "Переход из упрощенки в основное производство.docx",
                    order
                )
                order += 1

            if len(templates) == templates_before:
                unresolved.append(act_id)
                logger.warning(f"⚠️ Нет ветки маппинга для выбранного акта: {act_id}")

        # «Короткий текст» (резолютивка) — доп. документ ОДИН на генерацию, если включён
        # чекбокс. Процедуру берём из выбранного финального акта / варианта ВКЛ. Для ФНС
        # включенка сама по себе является резолютивкой (генерится как final_rtk_inclusion) —
        # отдельный короткий текст не добавляем.
        want_short_text = bool(data.get("selectedShortText") or data.get("shortText"))
        if want_short_text and not is_fns:
            variant = data.get("final_rtk_inclusion_variant")
            if variant in ('realization', 'restructuring', 'competition', 'observation'):
                procedure = variant
            elif 'final_restructuring' in act_ids:
                procedure = 'restructuring'
            elif 'final_competition' in act_ids:
                procedure = 'competition'
            elif 'final_observation' in act_ids:
                procedure = 'observation'
            elif 'final_realization' in act_ids:
                procedure = 'realization'
            else:
                procedure = 'observation' if entity_type in ('legal', 'kfh') else 'realization'
            templates['short_text'] = entry("Короткий текст (резолютивка)", _short_text_path(procedure, has_collateral), order)
            order += 1

        return templates, unresolved

