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
                "Определение о введении реализации имущества (заемщик)",
                "Определение о введении реализации ЗАЕМЩИК.docx",
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

    def _map_selected_acts_to_templates(self, selected_acts_ids: str, entity_type: str, collateral_option: str, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Маппит выбранные пользователем акты на реальные шаблоны документов.

        Args:
            selected_acts_ids: Строка с ID выбранных актов через запятую
            entity_type: Тип лица (individual, legal, ip, kfh)
            collateral_option: Тип залога (collateral, collateral_auto, no_collateral)
            data: Данные для генерации

        Returns:
            Словарь с шаблонами для генерации
        """
        if not selected_acts_ids:
            return {}

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

        # Базовые папки без залога по типу лица: ФЛ, ЮЛ, ИП, КФХ
        def _no_collateral_dir(subpath: str, for_entity: str) -> Path:
            """Папка для актов без залога в зависимости от типа лица."""
            if "конкурсное" in subpath or "Конкурсное" in subpath:
                return base_dir / "юр конкурсное ВКЛ в РТК"
            if "наблюдение" in subpath or "Наблюдение" in subpath:
                if for_entity == "kfh":
                    return root_dir / "КФХ"
                return base_dir / "юр ВКЛ в РТК наблюдение"
            # КФХ по умолчанию использует только наблюдение; для реализации/реструктуризации — физ
            if for_entity == "kfh":
                return base_dir / "физ реализация ВКЛ в РТК"
            if for_entity == "legal":
                return base_dir / "юр ВКЛ в РТК наблюдение"
            # individual, ip — ФЛ / ИП
            if "реструк" in subpath or "Реструктуризация" in subpath:
                return base_dir / "физ реструк ВКЛ в РТК"
            return base_dir / "физ реализация ВКЛ в РТК"

        act_ids = [act_id.strip() for act_id in selected_acts_ids.split(',')]
        templates = {}
        order = 1

        for act_id in act_ids:
            # Финальные СА (строго по выбранному залогу и типу лица)
            if act_id == 'final_realization':
                if has_collateral:
                    templates[act_id] = entry(
                        "Реализация ВКЛ Залог" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Реализация" / "Реализация ВКЛ Залог.docx",
                        order
                    )
                else:
                    # Без залога: реализация — для ФЛ и ИП.
                    # Для физлиц по РТК используем отдельный единый шаблон rtk.docx, если он есть.
                    root_dir = self._templates_root()
                    rtk_template = root_dir / "ртк.docx"
                    if entity_type == "individual" and rtk_template.exists():
                        templates[act_id] = entry(
                            "Реализация ВКЛ (РТК)",
                            rtk_template,
                            order
                        )
                    else:
                        d = _no_collateral_dir("реализация", entity_type)
                        templates[act_id] = entry(
                            "Реализация ВКЛ",
                            d / "Реализация ВКЛ несколько договоров.docx",
                            order
                        )
                order += 1
            elif act_id == 'final_competition':
                if has_collateral:
                    templates[act_id] = entry(
                        "Конкурсное ВКЛ в РТК Залог" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Конкурсное" / "Конкурсное ВКЛ в РТК Залог.docx",
                        order
                    )
                else:
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
                    if template_path is None and (base_dir / "юр инициир набл + конкурс").exists():
                        alt_d = base_dir / "юр инициир набл + конкурс"
                        template_path = _pick_docx_by_keywords_multi(alt_d, [
                            ["РЕШЕНИЕ", "КОНКУРС", "ПРОИЗВОДСТВА"],
                            ["РЕШЕНИЕ", "КОНКУРС"]
                        ])
                    if template_path is None:
                        template_path = preferred if preferred.exists() else (d / "Решение конкурсное.docx")

                    templates[act_id] = entry("Решение конкурсное", template_path, order)
                order += 1
            elif act_id == 'final_restructuring':
                if has_collateral:
                    templates[act_id] = entry(
                        "Реструктуризация ВКЛ Залог" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Реструктуризация" / "Реструктуризация ВКЛ Залог.docx",
                        order
                    )
                else:
                    d = _no_collateral_dir("реструк", entity_type)
                    templates[act_id] = entry(
                        "Реструктуризация ВКЛ",
                        d / "Реструктуризация ВКЛ.docx",
                        order
                    )
                order += 1
            elif act_id == 'final_observation':
                if has_collateral:
                    templates[act_id] = entry(
                        "Наблюдение ВКЛ в РТК Залог" + (" (авто)" if is_auto_collateral else ""),
                        collateral_dir / "Наблюдение" / "Наблюдение ВКЛ в РТК  Залог.docx",
                        order
                    )
                else:
                    if entity_type == "kfh":
                        templates[act_id] = entry(
                            "Наблюдение КФХ",
                            root_dir / "КФХ" / "Наблюдение КФХ.docx",
                            order
                        )
                    else:
                        templates[act_id] = entry(
                            "Наблюдение ВКЛ в РТК",
                            base_dir / "юр ВКЛ в РТК наблюдение" / "Наблюдение ВКЛ в РТК.docx",
                            order
                        )
                order += 1
            elif act_id == 'final_rtk_inclusion':
                # Определение ВКЛ в РТК
                # Проверяем, есть ли выбранный вариант (реализация / реструктуризация / конкурсное / наблюдение / зареестр)
                rtk_variant = data.get("final_rtk_inclusion_variant")

                if rtk_variant == 'registry':
                    templates['rtk_registry'] = entry(
                        "Определение ВКЛ в РТК зареестр",
                        new_acts_dir / "внести зареестр.docx",
                        order
                    )
                elif rtk_variant == 'realization':
                    if has_collateral:
                        templates['rtk_inclusion'] = entry(
                            "Определение ВКЛ в РТК (реализация с залогом)",
                            collateral_dir / "Реализация" / "Реализация ВКЛ Залог.docx",
                            order
                        )
                    else:
                        # Используем шаблон из "шаблоны актов без залогов\ртк.docx"
                        path = base_dir / "ртк.docx"
                        templates['rtk_inclusion'] = entry(
                            "Определение ВКЛ в РТК (реализация)",
                            path,
                            order
                        )
                elif rtk_variant == 'restructuring':
                    if has_collateral:
                        templates['rtk_inclusion'] = entry(
                            "Определение ВКЛ в РТК (реструктуризация с залогом)",
                            collateral_dir / "Реструктуризация" / "Реструктуризация ВКЛ Залог.docx",
                            order
                        )
                    else:
                        # Используем шаблон из "шаблоны актов без залогов\ртк.docx"
                        path = base_dir / "ртк.docx"
                        templates['rtk_inclusion'] = entry(
                            "Определение ВКЛ в РТК (реструктуризация)",
                            path,
                            order
                        )
                elif rtk_variant == 'competition':
                    if has_collateral:
                        templates['rtk_inclusion'] = entry(
                            "Определение ВКЛ в РТК (конкурсное с залогом)",
                            collateral_dir / "Конкурсное" / "Конкурсное ВКЛ в РТК Залог.docx",
                            order
                        )
                    else:
                        d = _resolve_competition_dir()
                        preferred = d / "Конкурсное ВКЛ в РТК.docx"
                        if preferred.exists():
                            template_path = preferred
                        else:
                            template_path = _pick_docx_by_keywords_multi(d, [
                                ["ОПРЕДЕЛЕНИЕ", "ВКЛЮЧЕНИИ", "ТРЕБОВАНИЙ", "РЕЕСТР"],
                                ["ОПРЕДЕЛЕНИЕ", "ВКЛ", "РЕЕСТР", "КРЕДИТОР"],
                                ["ОПРЕДЕЛЕНИЕ", "КОНКУРС", "ВКЛ"],
                                ["ОПРЕДЕЛЕНИЕ", "ВКЛ", "ТРЕБОВАНИЙ"],
                                ["ОПРЕДЕЛЕНИЕ", "ВКЛ"]
                            ])
                        if template_path is None:
                            template_path = preferred if preferred.exists() else (d / "Конкурсное ВКЛ в РТК.docx")

                        templates['rtk_inclusion'] = entry("Определение ВКЛ в РТК (конкурсное)", template_path, order)
                elif rtk_variant == 'observation':
                    if has_collateral:
                        templates['rtk_inclusion'] = entry(
                            "Определение ВКЛ в РТК (наблюдение с залогом)",
                            collateral_dir / "Наблюдение" / "Наблюдение ВКЛ в РТК  Залог.docx",
                            order
                        )
                    else:
                        if entity_type == "kfh":
                            templates['rtk_inclusion'] = entry(
                                "Определение ВКЛ в РТК (наблюдение КФХ)",
                                root_dir / "КФХ" / "Наблюдение КФХ.docx",
                                order
                            )
                        else:
                            templates['rtk_inclusion'] = entry(
                                "Определение ВКЛ в РТК (наблюдение)",
                                base_dir / "юр ВКЛ в РТК наблюдение" / "Наблюдение ВКЛ в РТК.docx",
                                order
                            )
                else:
                    # Вариант не указан: по типу лица — ЮЛ/КФХ наблюдение, ФЛ/ИП реализация
                    if entity_type in ('legal', 'kfh'):
                        if has_collateral:
                            templates['rtk_inclusion'] = entry(
                                "Определение ВКЛ в РТК (наблюдение с залогом)",
                                collateral_dir / "Наблюдение" / "Наблюдение ВКЛ в РТК  Залог.docx",
                                order
                            )
                        else:
                            if entity_type == "kfh":
                                templates['rtk_inclusion'] = entry(
                                    "Определение ВКЛ в РТК (наблюдение КФХ)",
                                    root_dir / "КФХ" / "Наблюдение КФХ.docx",
                                    order
                                )
                            else:
                                templates['rtk_inclusion'] = entry(
                                    "Определение ВКЛ в РТК (наблюдение)",
                                    base_dir / "юр ВКЛ в РТК наблюдение" / "Наблюдение ВКЛ в РТК.docx",
                                    order
                                )
                    else:
                        if has_collateral:
                            templates['rtk_inclusion'] = entry(
                                "Определение ВКЛ в РТК (реализация с залогом)",
                                collateral_dir / "Реализация" / "Реализация ВКЛ Залог.docx",
                                order
                            )
                        else:
                            # Используем шаблон из "шаблоны актов без залогов\ртк.docx"
                            path = base_dir / "ртк.docx"
                            templates['rtk_inclusion'] = entry(
                                "Определение ВКЛ в РТК (реализация)",
                                path,
                                order
                            )
                order += 1

            # Принятие (по типу лица: ФЛ/ЮЛ/ИП — принятие РТК, КФХ — инициирование КФХ)
            elif act_id == 'acceptance_definition':
                if entity_type == "kfh":
                    path = root_dir / "КФХ" / "Принятие иницирование КФХ.docx"
                else:
                    # Используем шаблон из "промежуточные_особые\заменить Принятие\принятие ртк.docx"
                    path = new_acts_dir / "заменить Принятие" / "принятие ртк.docx"
                    # Если файл не найден, используем старый путь как fallback
                    if not path.exists():
                        if entity_type == "legal":
                            path = base_dir / "юр ВКЛ в РТК наблюдение" / "Принятие РТК наблюдение.docx" if (base_dir / "юр ВКЛ в РТК наблюдение" / "Принятие РТК наблюдение.docx").exists() else (base_dir / "физ реализация ВКЛ в РТК" / "Реализация принятие РТК.docx")
                        else:
                            path = base_dir / "физ реализация ВКЛ в РТК" / "Реализация принятие РТК.docx"
                templates['acceptance'] = entry(
                    "Определение о принятии",
                    path,
                    order
                )
                order += 1
            elif act_id == 'acceptance_no_motion_no_duty':
                templates['acceptance_no_motion'] = entry(
                    "Определение Б/Д нет ГП",
                    new_acts_dir / "внести Обездвижка" / "бд ртк.docx",
                    order
                )
                order += 1
            elif act_id == 'acceptance_no_motion_no_duty_collateral':
                templates['acceptance_no_motion_collateral'] = entry(
                    "Определение Б/Д нет ГП залог",
                    new_acts_dir / "внести Обездвижка" / "бд ртк ГП залог недвижка.docx",
                    order
                )
                order += 1
            elif act_id == 'acceptance_no_motion_other':
                reason = data.get('acceptance_no_motion_other_reason', '')
                for_parties = data.get('acceptance_no_motion_other_forParties', '')
                templates['acceptance_no_motion_other'] = entry(
                    "Определение Б/Д иное",
                    new_acts_dir / "внести Обездвижка" / "бд ртк правопреемство.docx",
                    order
                )
                order += 1
            elif act_id == 'acceptance_after_no_motion':
                templates['acceptance_after_no_motion'] = entry(
                    "Принятие после Б/Д",
                    new_acts_dir / "принятие ртк после БД.docx",
                    order
                )
                order += 1

            # Промежуточные
            elif act_id == 'intermediate_postponement':
                reason = data.get('intermediate_postponement_reason', '')
                for_parties = data.get('intermediate_postponement_forParties', '')
                postponement_path = (new_acts_dir / "внести отложка" / "отложение залог+предл мир.docx") if has_collateral else (new_acts_dir / "внести отложка" / "отлож документар+мировое.docx")
                templates['postponement'] = entry(
                    "Отложение",
                    postponement_path,
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
                    base_dir / "Промежуточные" / "Продление Б/Д.docx",
                    order
                )
                order += 1
            elif act_id == 'intermediate_extend_simplified':
                templates['extend_simplified'] = entry(
                    "Продление упрощёнка",
                    base_dir / "Промежуточные" / "Продление упрощёнка.docx",
                    order
                )
                order += 1
            elif act_id == 'intermediate_simplified_to_main':
                templates['simplified_to_main'] = entry(
                    "Переход из упрощёнки в основное производство",
                    new_acts_dir / "внести Назначение после упрощенки" / "Назачение после упрощенки.docx",
                    order
                )
                order += 1

        return templates

