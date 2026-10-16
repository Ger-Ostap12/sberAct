"""Выбор файла шаблона в дереве «Банкротство»: папка по осям дела, роль по имени файла.

Пока покрыт только вид «Включение в РТК», раздел «Первоначальные».
"""

import re
from pathlib import Path
from typing import List, NamedTuple, Optional

BRANCH_RTK = "Включение в РТК"
SECTION_INITIAL = "Первоначальные"
SECTION_INTERMEDIATE = "Промежуточные"

# Роли первоначальных актов. Порядок правил важен: узкие раньше широких, иначе
# «о принятии после БД» попадёт в обычное принятие, а «нет ГП залог» — в «нет ГП».
ROLE_RULES = (
    ("acceptance_after_no_motion", re.compile(r"о принятии после бд|принятие после бд")),
    ("acceptance", re.compile(r"о принятии|принятие заявления|принятие иниц")),
    ("no_motion_no_duty_collateral", re.compile(r"бд не?т? гп залог")),
    ("no_motion_no_duty", re.compile(r"бд не?т? гп")),
    ("no_motion_other", re.compile(r"бд иное")),
    # Промежуточные. «Отложение 3 лицо» — отдельный акт, проверяем раньше общего.
    ("postponement_third_party", re.compile(r"отложение 3 лицо")),
    ("postponement", re.compile(r"отложение")),
    ("extend_no_motion", re.compile(r"продление бд")),
    ("return_no_duty", re.compile(r"возврат не?т? гп")),
    ("return_general", re.compile(r"общий возврат")),
    ("simplified_to_main", re.compile(r"переход из упрощенки")),
)

# Имена не унифицированы: «реализация» и «реал», «конкурсное» и «конкурс», плюс
# опечатка «кокнурсное». Один файл бывает на две процедуры — «Отложение рестр+реал».
PROCEDURE_RULES = (
    ("realization", re.compile(r"реализац|\bреал\b")),
    ("restructuring", re.compile(r"реструктур|\bрестр\b")),
    ("observation", re.compile(r"наблюд")),
    ("competition", re.compile(r"конкурс|кокнурс")),
)

# Акт на форме (галка) → роль файла. Пока только раздел «Первоначальные».
INITIAL_ACT_ROLES = {
    "acceptance_definition": "acceptance",
    "acceptance_after_no_motion": "acceptance_after_no_motion",
    "acceptance_no_motion_no_duty": "no_motion_no_duty",
    "acceptance_no_motion_no_duty_collateral": "no_motion_no_duty_collateral",
    "acceptance_no_motion_other": "no_motion_other",
}

# Акт на форме → роль файла, раздел «Промежуточные».
INTERMEDIATE_ACT_ROLES = {
    "intermediate_postponement": "postponement",
    "intermediate_postponement_third_party": "postponement_third_party",
    "intermediate_extend_no_motion": "extend_no_motion",
    "intermediate_return_general": "return_general",
    "intermediate_return_no_duty": "return_no_duty",
    "intermediate_simplified_to_main": "simplified_to_main",
}

# Галка на форме есть, файла в дереве нет ни у одной оси — «шаблон не готов».
ACTS_WITHOUT_TEMPLATE = {
    "intermediate_extend_simplified": "продление упрощёнки: такого акта в дереве нет",
}

ACT_SECTIONS = {
    **{act_id: SECTION_INITIAL for act_id in INITIAL_ACT_ROLES},
    **{act_id: SECTION_INTERMEDIATE for act_id in INTERMEDIATE_ACT_ROLES},
}

ACT_ROLES = {**INITIAL_ACT_ROLES, **INTERMEDIATE_ACT_ROLES}

_ENTITY_DIRS = {"individual": "ФЛ", "ip": "ИП", "legal": "ЮЛ", "kfh": "КФХ"}
_STATUS_DIRS = {"": "Обычный", "liquidation": "Ликвидируемый", "absent": "Отсутствующий"}
# Лица, у которых между заявителем и залогом лежит папка статуса.
_ENTITIES_WITH_STATUS = ("legal", "kfh")


class Resolution(NamedTuple):
    """Итог поиска: путь либо причина, по которой файла нет."""

    path: Optional[Path]
    folder: Optional[Path]
    reason: str = ""


def normalize_name(name: str) -> str:
    """Имя файла к сравнимому виду: регистр, ё, подчёркивания, восклицательный знак."""
    text = name.lower().replace("ё", "е").replace("_", " ")
    text = re.sub(r"\.docx$", "", text)
    text = text.replace("!", " ").replace("(копия)", " ")
    return re.sub(r"\s+", " ", text).strip()


def file_role(name: str) -> Optional[str]:
    normalized = normalize_name(name)
    for role, pattern in ROLE_RULES:
        if pattern.search(normalized):
            return role
    return None


def file_procedures(name: str) -> frozenset:
    """Процедуры из имени. Пустое множество — файл годится любой процедуре."""
    normalized = normalize_name(name)
    return frozenset(p for p, pattern in PROCEDURE_RULES if pattern.search(normalized))


def _same_name(left: str, right: str) -> bool:
    return left.lower().replace("ё", "е") == right.lower().replace("ё", "е")


def child_dir(parent: Path, name: str) -> Optional[Path]:
    """Подпапка по имени без учёта регистра и ё/е.

    Имя берём из листинга, а не из запроса: Windows открывает папку при любом
    регистре, и путь с чужим регистром потом не сошёлся бы с диском на Astra.
    """
    if not parent.is_dir():
        return None
    for item in parent.iterdir():
        if item.is_dir() and _same_name(item.name, name):
            return item
    return None


def section_folder(
    root: Path,
    *,
    entity: str,
    applicant: str = "creditors",
    status: str = "",
    collateral: bool = False,
    section: str = SECTION_INITIAL,
) -> Resolution:
    """Папка раздела по осям дела. Возвращает Resolution с folder либо причиной."""
    entity_dir = _ENTITY_DIRS.get(entity)
    if entity_dir is None:
        return Resolution(None, None, "неизвестный тип лица: %s" % entity)

    current = child_dir(root, "Банкротство")
    for step in (BRANCH_RTK, entity_dir):
        if current is None:
            break
        current = child_dir(current, step)
    if current is None:
        return Resolution(None, None, "нет папки лица %s в дереве" % entity_dir)

    if applicant == "fns":
        # У ФНС нет ни статуса, ни залога: всегда ФНС\Незалог.
        current = child_dir(current, "ФНС")
        current = child_dir(current, "Незалог") if current else None
        current = child_dir(current, section) if current else None
        return _folder_result(current, "ФНС/Незалог/%s" % section)

    current = child_dir(current, "Кредиторы")
    if current is None:
        return Resolution(None, None, "нет папки Кредиторы у %s" % entity_dir)

    if status == "deceased":
        # У умершего залог лежит ВНУТРИ раздела, а не перед ним.
        current = child_dir(current, "Умерший")
        current = child_dir(current, section) if current else None
        current = child_dir(current, "залог" if collateral else "незалог") if current else None
        return _folder_result(current, "Умерший/%s/%s" % (section, "залог" if collateral else "незалог"))

    if entity in _ENTITIES_WITH_STATUS:
        status_dir = _STATUS_DIRS.get(status)
        if status_dir is None:
            return Resolution(None, None, "неизвестный статус должника: %s" % status)
        current = child_dir(current, status_dir)
        if current is None:
            return Resolution(None, None, "нет папки статуса %s у %s" % (status_dir, entity_dir))

    current = child_dir(current, "Залог" if collateral else "Незалог")
    current = child_dir(current, section) if current else None
    return _folder_result(current, "%s/%s" % ("Залог" if collateral else "Незалог", section))


def _folder_result(folder: Optional[Path], tail: str) -> Resolution:
    if folder is None:
        return Resolution(None, None, "нет папки %s" % tail)
    return Resolution(None, folder)


def act_files(folder: Path) -> List[Path]:
    """Шаблоны в папке; файлы блокировки Word пропускаем."""
    return sorted(p for p in folder.glob("*.docx") if not p.name.startswith("~$"))


def pick_file(folder: Path, role: str, procedure: Optional[str] = None) -> Resolution:
    """Файл нужной роли и процедуры. Несколько кандидатов — отказ, а не первый попавшийся."""
    by_role = [p for p in act_files(folder) if file_role(p.name) == role]
    if not by_role:
        return Resolution(None, folder, "в папке нет акта роли «%s»" % role)

    if procedure:
        exact = [p for p in by_role if procedure in file_procedures(p.name)]
        # Файл без процедуры в имени годится любой, но названная важнее.
        candidates = exact or [p for p in by_role if not file_procedures(p.name)]
        if not candidates:
            return Resolution(None, folder, "в папке нет акта роли «%s» для процедуры «%s»"
                              % (role, procedure))
    else:
        candidates = by_role

    if len(candidates) > 1:
        return Resolution(None, folder, "неоднозначно, подходят: %s"
                          % ", ".join(p.name for p in candidates))
    return Resolution(candidates[0], folder)


def procedure_for_case(
    entity: str,
    status: str = "",
    *,
    rtk_variant: str = "",
    act_ids: Optional[List[str]] = None,
    introduced: str = "",
) -> str:
    """Процедура дела: сначала выбор юриста, затем статус, затем тип лица."""
    known = tuple(p for p, _ in PROCEDURE_RULES)
    if rtk_variant in known:
        return rtk_variant

    by_final = {
        "final_restructuring": "restructuring",
        "final_competition": "competition",
        "final_observation": "observation",
        "final_realization": "realization",
    }
    for act_id, procedure in by_final.items():
        if act_ids and act_id in act_ids:
            return procedure

    # Статус сужает процедуру жёстче типа лица: у ликвидируемого и отсутствующего
    # бывает только конкурсное, у умершего — только реализация имущества.
    if status in ("liquidation", "absent"):
        return "competition"
    if status == "deceased":
        return "realization"

    if introduced in known:
        return introduced
    return "observation" if entity in ("legal", "kfh") else "realization"


def resolve(
    root: Path,
    *,
    entity: str,
    role: str,
    applicant: str = "creditors",
    status: str = "",
    collateral: bool = False,
    procedure: Optional[str] = None,
    section: str = SECTION_INITIAL,
) -> Resolution:
    """Полный путь: оси дела плюс роль и процедура акта."""
    folder = section_folder(root, entity=entity, applicant=applicant, status=status,
                            collateral=collateral, section=section)
    if folder.folder is None:
        return folder
    return pick_file(folder.folder, role, procedure)
