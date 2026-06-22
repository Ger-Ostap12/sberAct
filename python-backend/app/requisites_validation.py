"""Валидация российских реквизитов по контрольным суммам.

Используется как фильтр в document_analyzer: отсеивает мусорные значения,
пойманные жадными regex (например, ИНН/ОГРН-плейсхолдеры или случайные цифры),
не затирая уже найденные корректные реквизиты.

Алгоритмы стандартные (ФНС):
  - ИНН 10 знаков — один контрольный разряд (юрлица);
  - ИНН 12 знаков — два контрольных разряда (физлица/ИП);
  - ОГРН 13 знаков — контрольный разряд = (число[:12] mod 11) mod 10;
  - ОГРНИП 15 знаков — контрольный разряд = (число[:14] mod 13) mod 10;
  - КПП 9 знаков — формат (без контрольной суммы как таковой).
"""
import re


def _digits(value) -> str:
    """Оставляет только цифры из значения."""
    return re.sub(r"\D", "", str(value or ""))


def is_valid_inn(value) -> bool:
    """Проверяет ИНН (10 или 12 цифр) по контрольным разрядам ФНС."""
    inn = _digits(value)
    if len(inn) == 10:
        return _inn_csum(inn, (2, 4, 10, 3, 5, 9, 4, 6, 8)) == int(inn[9])
    if len(inn) == 12:
        c11 = _inn_csum(inn, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
        c12 = _inn_csum(inn, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
        return c11 == int(inn[10]) and c12 == int(inn[11])
    return False


def _inn_csum(inn: str, coeffs) -> int:
    """Контрольный разряд ИНН по набору коэффициентов."""
    return sum(int(inn[i]) * c for i, c in enumerate(coeffs)) % 11 % 10


def is_valid_ogrn(value) -> bool:
    """Проверяет ОГРН (13 цифр) по контрольному разряду."""
    ogrn = _digits(value)
    if len(ogrn) != 13:
        return False
    return int(ogrn[:12]) % 11 % 10 == int(ogrn[12])


def is_valid_ogrnip(value) -> bool:
    """Проверяет ОГРНИП (15 цифр) по контрольному разряду."""
    ogrnip = _digits(value)
    if len(ogrnip) != 15:
        return False
    return int(ogrnip[:14]) % 13 % 10 == int(ogrnip[14])


def is_valid_kpp(value) -> bool:
    """Проверяет КПП: 9 знаков, формат NNNN[A-Z0-9]{2}NNN."""
    kpp = re.sub(r"\s", "", str(value or "")).upper()
    return bool(re.fullmatch(r"[0-9]{4}[0-9A-Z]{2}[0-9]{3}", kpp))


def is_valid_ogrn_any(value) -> bool:
    """ОГРН или ОГРНИП — для случаев, когда тип заранее неизвестен."""
    return is_valid_ogrn(value) or is_valid_ogrnip(value)
