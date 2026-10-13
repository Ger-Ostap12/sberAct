# -*- coding: utf-8 -*-
"""Введённая процедура по тексту заявления о включении в РТК.

Формулировки взяты из корпуса (замер 13.10.2026): падежи плавают, тире бывает
коротким и длинным, слова рвутся переносом. Конкурсное производство в корпусе
встречается один раз — у «ООО СПОРТ».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from introduced_procedure import detect_introduced_procedure  # noqa: E402


class TestРеализация:
    def test_прямая_форма(self):
        текст = "Решением суда от 23.04.2026 введена процедура реализации имущества гражданина."
        assert detect_introduced_procedure(текст) == "realization"

    def test_через_применяемую_процедуру_длинное_тире(self):
        текст = ("должник признан банкротом, введена процедура, применяемая в деле "
                 "о банкротстве — реализация имущества гражданина")
        assert detect_introduced_procedure(текст) == "realization"

    def test_через_применяемую_процедуру_короткое_тире(self):
        текст = ("введена процедура, применяемая в деле о банкротстве – реализация "
                 "имущества гражданина")
        assert detect_introduced_procedure(текст) == "realization"

    def test_в_отношении_него(self):
        текст = ("признан несостоятельным (банкротом), в отношении него введена "
                 "процедура реализации имущества гражданина")
        assert detect_introduced_procedure(текст) == "realization"

    def test_имущества_должника(self):
        assert detect_introduced_procedure("введена процедура реализации имущества должника") == "realization"

    def test_без_слова_гражданина(self):
        assert detect_introduced_procedure("введена процедура реализации имущества") == "realization"

    def test_слово_разорвано_переносом(self):
        текст = "введена процедура реализации имуще- ства гражданина"
        assert detect_introduced_procedure(текст) == "realization"

    def test_перенос_без_пробела(self):
        # Форма из «ПИСКОВА»: конвертация склеила перенос и оставила дефис.
        текст = "введена процедура реализации имуще-ства гражданина"
        assert detect_introduced_procedure(текст) == "realization"

    def test_перенос_со_строкой(self):
        текст = "введена процедура реализации имущества граж-\nданина"
        assert detect_introduced_procedure(текст) == "realization"


class TestРеструктуризация:
    def test_прямая_форма(self):
        текст = "введена процедура реструктуризации долгов гражданина"
        assert detect_introduced_procedure(текст) == "restructuring"

    def test_через_применяемую_процедуру(self):
        текст = ("введена процедура, применяемая в деле о банкротстве – реструктуризация "
                 "долгов гражданина")
        assert detect_introduced_procedure(текст) == "restructuring"

    def test_винительный_падеж(self):
        текст = ("суд ввёл процедуру: введена применяемая в деле о банкротстве "
                 "реструктуризацию долгов гражданина")
        assert detect_introduced_procedure(текст) == "restructuring"


class TestКонкурсное:
    def test_введено_формулировка_спорта(self):
        текст = ("Решением суда от 11.02.2026 в отношении Должника введено конкурсное "
                 "производство, конкурсным управляющим утверждён(а) Полейчук Семён Сергеевич")
        assert detect_introduced_procedure(текст) == "competition"

    def test_открыто(self):
        assert detect_introduced_procedure("открыто конкурсное производство") == "competition"

    def test_сообщение_о_введении(self):
        текст = "Сообщение о введении конкурсного производства опубликовано в газете «Коммерсантъ»"
        assert detect_introduced_procedure(текст) == "competition"


class TestНаблюдение:
    def test_процедура_банкротства_наблюдение(self):
        assert detect_introduced_procedure("введена процедура банкротства наблюдение") == "observation"

    def test_родительный_падеж(self):
        assert detect_introduced_procedure("введена процедура наблюдения") == "observation"


class TestЛовушки:
    def test_цитата_закона_фнс_не_считается(self):
        # Эта фраза есть у десяти заявлений ФНС и не называет процедуру дела.
        текст = ("требований об уплате обязательных платежей и требований Российской "
                 "Федерации по денежным обязательствам, применяемых в деле о банкротстве")
        assert detect_introduced_procedure(текст) is None

    def test_депозит_суда_не_считается(self):
        текст = ("денежные средства на выплату вознаграждения управляющему за процедуру, "
                 "применяемую в деле о банкротстве гражданина, вносятся конкурсным "
                 "кредитором в депозит арбитражного суда")
        assert detect_introduced_procedure(текст) is None

    def test_просьба_ввести_не_считается(self):
        # Инициирующее заявление просит ввести процедуру — она ещё не введена.
        текст = "ПРОШУ: признать должника банкротом и ввести процедуру реализации имущества гражданина"
        assert detect_introduced_procedure(текст) is None

    def test_пустой_текст(self):
        assert detect_introduced_procedure("") is None
        assert detect_introduced_procedure(None) is None

    def test_процедура_не_названа(self):
        assert detect_introduced_procedure("введена процедура по делу о банкротстве") is None

    def test_ходатайство_о_введении_не_считается(self):
        # «О введении» бывает и просьбой: принимаем только публикацию о факте.
        текст = "ходатайствуем о введении процедуры реализации имущества гражданина"
        assert detect_introduced_procedure(текст) is None

    def test_заявление_о_признании_и_введении_не_считается(self):
        текст = ("заявление о признании несостоятельным (банкротом) и введении процедуры "
                 "реализации имущества гражданина")
        assert detect_introduced_procedure(текст) is None

    def test_конкурсный_управляющий_без_производства_не_считается(self):
        # «Конкурсный управляющий» в шапке не означает конкурсного производства.
        текст = "Конкурсный управляющий: Полейчук Семён Сергеевич, признан представителем"
        assert detect_introduced_procedure(текст) is None


class TestПорядок:
    def test_берётся_первая_названная_процедура(self):
        текст = ("введена процедура реструктуризации долгов гражданина. Позднее введена "
                 "процедура реализации имущества гражданина")
        assert detect_introduced_procedure(текст) == "restructuring"

    def test_в_одном_окне_берётся_ближайшая(self):
        текст = "введена процедура реализации имущества гражданина, конкурсное производство не вводилось"
        assert detect_introduced_procedure(текст) == "realization"
