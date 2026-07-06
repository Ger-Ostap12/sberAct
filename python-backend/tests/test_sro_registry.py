# -*- coding: utf-8 -*-
"""Тесты сопоставления СРО (`sro_registry.resolve_sro`): упоминание организации из
заявления → каноничное полное имя (NAIM_FULL) из справочника `sro_data`.

Краевые случаи: кавычки-ёлочки/прямые, хвост ИНН/ОГРН/адреса, короткая
аббревиатура, префикс «СРО », отсутствие совпадения → None.
"""
from sro_registry import resolve_sro


def test_yolki_quotes_exact():
    # «Содействие» в ёлочках — точное совпадение по нормализованному NAIMK.
    r = resolve_sro('Ассоциация МСРО «Содействие»')
    assert r == ('Ассоциация "Межрегиональная саморегулируемая организация '
                 'арбитражных управляющих "Содействие"')


def test_tail_inn_stripped():
    # Хвост ИНН не мешает: NAIMK — подстрока нормализованного входа.
    assert resolve_sro('САУ "СРО "ДЕЛО" ИНН 5010029544') == \
        'Союз арбитражных управляющих "Саморегулируемая организация "ДЕЛО"'


def test_tail_ogrn_and_prefix():
    assert resolve_sro('«Содействие» ОГРН: 1025700780071').endswith('"Содействие"')
    assert resolve_sro('- СРО ААУ "Синергия"(ИНН2308980067').endswith('"Синергия"')


def test_abbreviation():
    # Короткая аббревиатура целиком совпадает с NAIMK.
    assert 'Центрального федерального' in (resolve_sro('ПАУ ЦФО') or '')


def test_no_match_returns_none():
    assert resolve_sro('какая-то левая организация без совпадений') is None
    assert resolve_sro('') is None
    assert resolve_sro(None) is None
