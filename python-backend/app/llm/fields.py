# -*- coding: utf-8 -*-
"""Единственное место, где схема LLM сопоставляется с полями формы.

Зачем отдельным файлом: имена в схеме LLM (`court.name`, `debtors[].inn`) и
ключи полей на фронте (`courtName`, `debtors[0].inn`) — разные словари, и если
раскладку размазать по коду, они разъедутся молча. Подсказка с ключом, которого
на форме нет, просто не отобразится — без единой ошибки в логах.

Формат ключей массивов (`debtors[0].inn`) повторяет уже принятый в fieldQuality:
фронт разбирает его регуляркой в FieldIssuesPanel.
"""

# Порядок блоков = порядок на экране = порядок вызовов LLM. Юрист читает форму
# сверху вниз, поэтому раньше должно приходить то, что он увидит первым.
# `title` идёт в индикатор прогресса, `labels` — в текст подсказки.
BLOCKS: tuple = (
    {
        "key": "court",
        "title": "Судебная информация",
        "kind": "flat",
        "source": "court",
        "map": {"name": "courtName", "address": "courtAddress"},
        "labels": {"name": "Название суда", "address": "Адрес суда"},
    },
    {
        "key": "representative",
        "title": "Представитель истца",
        "kind": "flat",
        "source": "representatives",
        "map": {"plaintiff": "representativeName"},
        "labels": {"plaintiff": "ФИО представителя истца"},
    },
    {
        "key": "debtors",
        "title": "Данные ответчика",
        "kind": "array",
        "source": "debtors",
        "prefix": "debtors",
        "map": {
            "name": "name",
            "address": "address",
            "inn": "inn",
            "birthDate": "birthDate",
        },
        "labels": {
            "name": "ФИО",
            "address": "Адрес ответчика",
            "inn": "ИНН",
            "birthDate": "Дата рождения",
        },
    },
    {
        "key": "thirdParties",
        "title": "Третьи лица",
        "kind": "array",
        "source": "thirdParties",
        "prefix": "thirdParties",
        "map": {"name": "name", "address": "address", "inn": "inn"},
        "labels": {
            "name": "ФИО/наименование",
            "address": "Адрес",
            "inn": "ИНН",
        },
    },
    {
        "key": "properties",
        "title": "Предмет ипотеки",
        "kind": "array",
        "source": "properties",
        "prefix": "mortgageProperties",
        "map": {
            "description": "description",
            "cadastralNumber": "cadastralNumber",
            "address": "address",
            "value": "value",
            "startingPrice": "startingPrice",
            "npcStrategy": "npcStrategy",
            "appraisalReport": "appraisalReport",
            "egrnRecord": "egrnRecord",
        },
        "labels": {
            "description": "Описание объекта",
            "cadastralNumber": "Кадастровый номер",
            "address": "Адрес объекта",
            "value": "Стоимость (оценка)",
            "startingPrice": "Начальная продажная цена",
            "npcStrategy": "Стратегия определения НПЦ",
            "appraisalReport": "Отчёт об оценке",
            "egrnRecord": "Запись в ЕГРН",
        },
    },
)

BLOCK_KEYS: tuple = tuple(b["key"] for b in BLOCKS)

# Этапы, о которых отчитывается индикатор прогресса. Правдоподобие — не блок
# формы (у него нет своих полей, замечания он вешает на чужие), но по времени
# это отдельный шаг, и не считать его значило бы показывать юристу «5 из 5»,
# пока работа ещё идёт.
SANITY_BLOCK = "sanity"

# Проверка правдоподобия ОТКЛЮЧЕНА по результату замера на ипотечном корпусе
# (2026-08-20, handoff §R.23). В каждое из 8 заявлений подсаживали мусор в три
# разных поля и отдельно считали тревоги на нетронутых значениях:
#
#     поймано подсаженного мусора    11 из 24
#     ложных тревог на чистом        11 (разброс по файлам 0..5)
#
# То есть больше половины мусора проходит мимо, и при этом юриста дёргают
# примерно раз на документ без повода. Для сигнала, который должен вызывать
# доверие, это негодное соотношение: несколько ложных тревог научат
# игнорировать ВСЕ подсказки разом, включая верные.
#
# Отдельно показательно КАЧЕСТВО ответов: в поле «почему» модель возвращала то
# само проверяемое значение, то метку чужого поля («ИНН (1)» в объяснении к
# ФИО). Задача «вынеси суждение о наборе разнородных полей» для 4B-модели
# просто за пределами возможностей, и правкой промпта это не лечится — в этом
# проекте точечные правки уже трижды давали регрессию.
#
# Код и промпт оставлены НАМЕРЕННО: если появится модель побольше или задачу
# удастся сузить до одного поля за вызов, замер надо повторить, а не писать
# заново. Правильный путь для той же цели — детерминированный контракт поля
# (field_contract): на тех же данных он даёт ноль ложных при мгновенной работе.
SANITY_ENABLED = False

PROGRESS_KEYS: tuple = ((SANITY_BLOCK,) + BLOCK_KEYS) if SANITY_ENABLED else BLOCK_KEYS


def block_by_key(key: str) -> dict | None:
    for b in BLOCKS:
        if b["key"] == key:
            return b
    return None


def field_key(block: dict, schema_field: str, index: int = 0) -> str:
    """Ключ поля на форме для одного поля схемы."""
    target = block["map"][schema_field]
    if block["kind"] == "array":
        return f"{block['prefix']}[{index}].{target}"
    return target


def field_label(block: dict, schema_field: str) -> str:
    return block["labels"].get(schema_field, schema_field)
