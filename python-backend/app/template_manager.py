import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TemplateManager:
    def __init__(self):
        """
        Инициализация менеджера шаблонов
        """
        self.templates_dir = Path("templates")
        self.templates_dir.mkdir(exist_ok=True)

        # Загружаем шаблоны
        self.templates = self.load_templates()

    def load_templates(self) -> List[Dict[str, Any]]:
        """
        Загружает все доступные шаблоны
        """
        templates = [
            {
                "id": "rtk_single_obligation",
                "name": "Решение о включении в РТК (одно обязательство)",
                "description": "Шаблон для судебного акта о включении в реестр требований кредиторов по одному обязательству",
                "category": "РТК",
                "version": "1.0.0",
                "created_date": "2025-01-01",
                "author": "SberAct Team",
                "fields": [
                    {
                        "name": "applicantName",
                        "label": "ФИО заявителя",
                        "type": "text",
                        "required": True,
                        "description": "Полное имя заявителя",
                        "validation": {
                            "minLength": 5,
                            "maxLength": 100,
                            "pattern": "^[А-ЯЁ][а-яё]+\\s+[А-ЯЁ][а-яё]+\\s+[А-ЯЁ][а-яё]+$"
                        }
                    },
                    {
                        "name": "applicantAddress",
                        "label": "Адрес заявителя",
                        "type": "text",
                        "required": True,
                        "description": "Адрес места жительства заявителя",
                        "validation": {
                            "minLength": 10,
                            "maxLength": 200
                        }
                    },
                    {
                        "name": "applicationDate",
                        "label": "Дата заявления",
                        "type": "date",
                        "required": True,
                        "description": "Дата подачи заявления",
                        "validation": {
                            "pattern": "^\\d{1,2}[.,]\\d{1,2}[.,]\\d{4}$"
                        }
                    },
                    {
                        "name": "courtName",
                        "label": "Название суда",
                        "type": "text",
                        "required": True,
                        "description": "Полное название арбитражного суда",
                        "validation": {
                            "minLength": 10,
                            "maxLength": 150
                        }
                    },
                    {
                        "name": "caseNumber",
                        "label": "Номер дела",
                        "type": "text",
                        "required": True,
                        "description": "Номер дела в арбитражном суде",
                        "validation": {
                            "pattern": "^[А-ЯЁ0-9/-]+$"
                        }
                    },
                    {
                        "name": "debtAmount",
                        "label": "Сумма долга",
                        "type": "number",
                        "required": True,
                        "description": "Сумма долга в рублях",
                        "validation": {
                            "minValue": 1,
                            "maxValue": 999999999
                        }
                    },
                    {
                        "name": "creditorName",
                        "label": "Кредитор",
                        "type": "text",
                        "required": True,
                        "description": "Наименование кредитора",
                        "validation": {
                            "minLength": 3,
                            "maxLength": 200
                        }
                    },
                    {
                        "name": "debtorName",
                        "label": "Должник",
                        "type": "text",
                        "required": True,
                        "description": "Наименование должника",
                        "validation": {
                            "minLength": 3,
                            "maxLength": 200
                        }
                    },
                    {
                        "name": "contractNumber",
                        "label": "Номер договора",
                        "type": "text",
                        "required": False,
                        "description": "Номер договора или иного документа",
                        "validation": {
                            "maxLength": 50
                        }
                    },
                    {
                        "name": "contractDate",
                        "label": "Дата договора",
                        "type": "date",
                        "required": False,
                        "description": "Дата заключения договора",
                        "validation": {
                            "pattern": "^\\d{1,2}[.,]\\d{1,2}[.,]\\d{4}$"
                        }
                    },
                    {
                        "name": "obligationType",
                        "label": "Тип обязательства",
                        "type": "text",
                        "required": False,
                        "description": "Тип обязательства (кредитный договор, поставка и т.д.)",
                        "validation": {
                            "maxLength": 100
                        }
                    }
                ],
                "preview_image": None,
                "tags": ["ртк", "банкротство", "одно обязательство"],
                "usage_count": 0,
                "last_used": None
            },
            {
                "id": "rtk_multiple_obligations",
                "name": "Решение о включении в РТК (несколько обязательств)",
                "description": "Шаблон для судебного акта о включении в реестр требований кредиторов по нескольким обязательствам",
                "category": "РТК",
                "version": "1.0.0",
                "created_date": "2025-01-01",
                "author": "SberAct Team",
                "fields": [
                    {
                        "name": "applicantName",
                        "label": "ФИО заявителя",
                        "type": "text",
                        "required": True,
                        "description": "Полное имя заявителя",
                        "validation": {
                            "minLength": 5,
                            "maxLength": 100,
                            "pattern": "^[А-ЯЁ][а-яё]+\\s+[А-ЯЁ][а-яё]+\\s+[А-ЯЁ][а-яё]+$"
                        }
                    },
                    {
                        "name": "applicantAddress",
                        "label": "Адрес заявителя",
                        "type": "text",
                        "required": True,
                        "description": "Адрес места жительства заявителя",
                        "validation": {
                            "minLength": 10,
                            "maxLength": 200
                        }
                    },
                    {
                        "name": "applicationDate",
                        "label": "Дата заявления",
                        "type": "date",
                        "required": True,
                        "description": "Дата подачи заявления",
                        "validation": {
                            "pattern": "^\\d{1,2}[.,]\\d{1,2}[.,]\\d{4}$"
                        }
                    },
                    {
                        "name": "courtName",
                        "label": "Название суда",
                        "type": "text",
                        "required": True,
                        "description": "Полное название арбитражного суда",
                        "validation": {
                            "minLength": 10,
                            "maxLength": 150
                        }
                    },
                    {
                        "name": "caseNumber",
                        "label": "Номер дела",
                        "type": "text",
                        "required": True,
                        "description": "Номер дела в арбитражном суде",
                        "validation": {
                            "pattern": "^[А-ЯЁ0-9/-]+$"
                        }
                    },
                    {
                        "name": "debtAmount",
                        "label": "Общая сумма долга",
                        "type": "number",
                        "required": True,
                        "description": "Общая сумма долга по всем обязательствам",
                        "validation": {
                            "minValue": 1,
                            "maxValue": 999999999
                        }
                    },
                    {
                        "name": "creditorName",
                        "label": "Кредитор",
                        "type": "text",
                        "required": True,
                        "description": "Наименование кредитора",
                        "validation": {
                            "minLength": 3,
                            "maxLength": 200
                        }
                    },
                    {
                        "name": "debtorName",
                        "label": "Должник",
                        "type": "text",
                        "required": True,
                        "description": "Наименование должника",
                        "validation": {
                            "minLength": 3,
                            "maxLength": 200
                        }
                    },
                    {
                        "name": "obligationsCount",
                        "label": "Количество обязательств",
                        "type": "number",
                        "required": False,
                        "description": "Количество обязательств",
                        "validation": {
                            "minValue": 2,
                            "maxValue": 100
                        }
                    }
                ],
                "preview_image": None,
                "tags": ["ртк", "банкротство", "несколько обязательств"],
                "usage_count": 0,
                "last_used": None
            },
            {
                "id": "ip_enforcement",
                "name": "Взыскание с индивидуального предпринимателя",
                "description": "Комплект судебных актов (принятие и решение) по иску к индивидуальному предпринимателю",
                "category": "Взыскание",
                "version": "1.0.0",
                "created_date": datetime.now().strftime("%Y-%m-%d"),
                "author": "SberAct Team",
                "fields": [
                    {"name": "applicantName", "label": "ФИО индивидуального предпринимателя", "type": "text", "required": True},
                    {"name": "inn", "label": "ИНН ИП", "type": "text", "required": True},
                    {"name": "ogrnip", "label": "ОГРНИП", "type": "text", "required": True},
                    {"name": "birthDate", "label": "Дата рождения", "type": "date", "required": False},
                    {"name": "applicantAddress", "label": "Адрес регистрации", "type": "text", "required": False},
                    {"name": "contractNumber", "label": "Номер кредитного договора", "type": "text", "required": True},
                    {"name": "contractDate", "label": "Дата кредитного договора", "type": "date", "required": True},
                    {"name": "creditAmount", "label": "Сумма кредита", "type": "number", "required": True},
                    {"name": "creditTermMonths", "label": "Срок кредита (месяцы)", "type": "number", "required": True},
                    {"name": "creditInterestRate", "label": "Процентная ставка (%)", "type": "number", "required": True},
                    {"name": "creditPenaltyRate", "label": "Ставка неустойки (%)", "type": "number", "required": False},
                    {"name": "totalDebt", "label": "Общая сумма задолженности", "type": "number", "required": True},
                    {"name": "principalDebt13", "label": "Основной долг", "type": "number", "required": True},
                    {"name": "interest14", "label": "Проценты", "type": "number", "required": True},
                    {"name": "forfeit15", "label": "Неустойка", "type": "number", "required": False},
                    {"name": "stateDuty16", "label": "Госпошлина", "type": "number", "required": False},
                    {"name": "ipHasCollateral", "label": "Есть залог", "type": "select", "required": False, "options": ["true", "false"]}
                ],
                "preview_image": None,
                "tags": ["ип", "взыскание", "кредит"],
                "usage_count": 0,
                "last_used": None
            }
        ]

        return templates

    def get_all_templates(self) -> List[Dict[str, Any]]:
        """
        Возвращает все доступные шаблоны
        """
        return self.templates

    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает шаблон по ID
        """
        for template in self.templates:
            if template["id"] == template_id:
                return template
        return None

    def get_templates_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Возвращает шаблоны по категории
        """
        return [t for t in self.templates if t["category"].lower() == category.lower()]

    def search_templates(self, query: str) -> List[Dict[str, Any]]:
        """
        Ищет шаблоны по запросу
        """
        query_lower = query.lower()
        results = []

        for template in self.templates:
            # Поиск по названию
            if query_lower in template["name"].lower():
                results.append(template)
                continue

            # Поиск по описанию
            if query_lower in template["description"].lower():
                results.append(template)
                continue

            # Поиск по тегам
            if any(query_lower in tag.lower() for tag in template["tags"]):
                results.append(template)
                continue

        return results

    def validate_template_data(self, template_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Валидирует данные для шаблона
        """
        template = self.get_template_by_id(template_id)
        if not template:
            return {
                "valid": False,
                "errors": [f"Шаблон {template_id} не найден"]
            }

        errors = []
        warnings = []

        for field in template["fields"]:
            field_name = field["name"]
            field_value = data.get(field_name)

            if field["required"] and not field_value:
                errors.append(f"Поле '{field['label']}' обязательно для заполнения")
                continue

            if field_value and "validation" in field:
                validation = field["validation"]

                # Проверка минимальной длины
                if "minLength" in validation and len(str(field_value)) < validation["minLength"]:
                    errors.append(f"Поле '{field['label']}' должно содержать минимум {validation['minLength']} символов")

                # Проверка максимальной длины
                if "maxLength" in validation and len(str(field_value)) > validation["maxLength"]:
                    errors.append(f"Поле '{field['label']}' должно содержать максимум {validation['maxLength']} символов")

                # Проверка паттерна
                if "pattern" in validation:
                    import re
                    if not re.match(validation["pattern"], str(field_value)):
                        errors.append(f"Поле '{field['label']}' не соответствует требуемому формату")

                # Проверка числовых значений
                if field["type"] == "number" and "minValue" in validation:
                    try:
                        num_value = float(field_value)
                        if num_value < validation["minValue"]:
                            errors.append(f"Поле '{field['label']}' должно быть не менее {validation['minValue']}")
                    except (ValueError, TypeError):
                        errors.append(f"Поле '{field['label']}' должно быть числом")

                if field["type"] == "number" and "maxValue" in validation:
                    try:
                        num_value = float(field_value)
                        if num_value > validation["maxValue"]:
                            errors.append(f"Поле '{field['label']}' должно быть не более {validation['maxValue']}")
                    except (ValueError, TypeError):
                        pass

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def increment_usage(self, template_id: str):
        """
        Увеличивает счетчик использования шаблона
        """
        template = self.get_template_by_id(template_id)
        if template:
            template["usage_count"] += 1
            template["last_used"] = datetime.now().isoformat()
            logger.info(f"Увеличен счетчик использования шаблона {template_id}")

    def add_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Добавляет новый шаблон
        """
        try:
            # Проверяем обязательные поля
            required_fields = ["id", "name", "description", "category", "fields"]
            for field in required_fields:
                if field not in template_data:
                    return {
                        "success": False,
                        "error": f"Отсутствует обязательное поле: {field}"
                    }

            # Проверяем уникальность ID
            if self.get_template_by_id(template_data["id"]):
                return {
                    "success": False,
                    "error": f"Шаблон с ID {template_data['id']} уже существует"
                }

            # Добавляем метаданные
            template_data["version"] = template_data.get("version", "1.0.0")
            template_data["created_date"] = datetime.now().isoformat()
            template_data["author"] = template_data.get("author", "SberAct Team")
            template_data["usage_count"] = 0
            template_data["last_used"] = None
            template_data["tags"] = template_data.get("tags", [])

            # Добавляем шаблон
            self.templates.append(template_data)

            logger.info(f"Добавлен новый шаблон: {template_data['id']}")

            return {
                "success": True,
                "template_id": template_data["id"]
            }

        except Exception as e:
            logger.error(f"Ошибка при добавлении шаблона: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def update_template(self, template_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет существующий шаблон
        """
        template = self.get_template_by_id(template_id)
        if not template:
            return {
                "success": False,
                "error": f"Шаблон {template_id} не найден"
            }

        try:
            # Обновляем поля
            for key, value in updates.items():
                if key in template:
                    template[key] = value

            # Обновляем дату изменения
            template["last_modified"] = datetime.now().isoformat()

            logger.info(f"Обновлен шаблон: {template_id}")

            return {
                "success": True,
                "template_id": template_id
            }

        except Exception as e:
            logger.error(f"Ошибка при обновлении шаблона: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_template(self, template_id: str) -> Dict[str, Any]:
        """
        Удаляет шаблон
        """
        template = self.get_template_by_id(template_id)
        if not template:
            return {
                "success": False,
                "error": f"Шаблон {template_id} не найден"
            }

        try:
            # Удаляем шаблон
            self.templates = [t for t in self.templates if t["id"] != template_id]

            logger.info(f"Удален шаблон: {template_id}")

            return {
                "success": True,
                "template_id": template_id
            }

        except Exception as e:
            logger.error(f"Ошибка при удалении шаблона: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def export_templates(self, file_path: str) -> Dict[str, Any]:
        """
        Экспортирует шаблоны в JSON файл
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.templates, f, ensure_ascii=False, indent=2)

            logger.info(f"Шаблоны экспортированы в {file_path}")

            return {
                "success": True,
                "file_path": file_path
            }

        except Exception as e:
            logger.error(f"Ошибка при экспорте шаблонов: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def import_templates(self, file_path: str) -> Dict[str, Any]:
        """
        Импортирует шаблоны из JSON файла
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_templates = json.load(f)

            # Проверяем структуру
            if not isinstance(imported_templates, list):
                return {
                    "success": False,
                    "error": "Неверный формат файла: ожидается список шаблонов"
                }

            # Добавляем импортированные шаблоны
            added_count = 0
            for template in imported_templates:
                result = self.add_template(template)
                if result["success"]:
                    added_count += 1

            logger.info(f"Импортировано {added_count} шаблонов из {file_path}")

            return {
                "success": True,
                "added_count": added_count
            }

        except Exception as e:
            logger.error(f"Ошибка при импорте шаблонов: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
