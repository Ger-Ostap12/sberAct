"""Выбор шаблона в дереве «Банкротство»: роль по имени, папка по осям дела."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from bankruptcy_tree import (  # noqa: E402
    INITIAL_ACT_ROLES,
    INTERMEDIATE_ACT_ROLES,
    ROLE_RULES,
    SECTION_INITIAL,
    SECTION_INTERMEDIATE,
    act_files,
    child_dir,
    file_procedures,
    file_role,
    normalize_name,
    pick_file,
    resolve,
    section_folder,
)
from document_generator import DocumentGenerator  # noqa: E402

# Роли раздела «Первоначальные»: промежуточные живут в своей папке и свои
# файлы ищут там же, перебирать их по этому разделу бессмысленно.
РОЛИ = list(INITIAL_ACT_ROLES.values())
ВСЕ_РОЛИ = [r for r, _ in ROLE_RULES]


@pytest.fixture(scope="module")
def корень():
    return DocumentGenerator()._templates_root()


class TestРольПоИмени:
    @pytest.mark.parametrize("имя,роль", [
        ("Определение о принятии реализация.docx", "acceptance"),
        ("Определение о принятии КОНКУРСНОЕ.docx", "acceptance"),
        ("Определение о принятии после БД реализация.docx", "acceptance_after_no_motion"),
        ("Определение о принятии после БД КОНКУРСНОЕ.docx", "acceptance_after_no_motion"),
        ("Определение БД нет ГП реализация.docx", "no_motion_no_duty"),
        ("Определение БД нет ГП залог реализация.docx", "no_motion_no_duty_collateral"),
        ("Определение БД иное реструктуризация.docx", "no_motion_other"),
        ("Определение БД иное кокнурсное.docx", "no_motion_other"),
    ])
    def test_реальные_имена(self, имя, роль):
        assert file_role(имя) == роль

    def test_после_бд_не_путается_с_принятием(self):
        # Узкое правило раньше широкого, иначе принятие после Б/Д уедет в принятие.
        assert file_role("Определение о принятии после БД наблюдение.docx") != "acceptance"

    def test_залоговый_не_путается_с_обычным(self):
        assert file_role("Определение БД нет ГП залог наблюдение.docx") == "no_motion_no_duty_collateral"
        assert file_role("Определение БД нет ГП наблюдение.docx") == "no_motion_no_duty"

    def test_чужое_имя_без_роли(self):
        # Акты включения в РТК — другой раздел, ролей у них пока нет.
        assert file_role("Вкл в РТК реализация залог полный текст.docx") is None
        assert file_role("Резолютивка ВКЛ реализация Залог.docx") is None

    @pytest.mark.parametrize("имя,роль", [
        ("Отложение рестр+реал.docx", "postponement"),
        ("Отложение залог наблюд+конкурс.docx", "postponement"),
        ("Отложение 3 лицо кокнурсное.docx", "postponement_third_party"),
        ("Отложение 3 лицо залог рестр+реал.docx", "postponement_third_party"),
        ("Продление БД конкурс.docx", "extend_no_motion"),
        ("Общий возврат реализация.docx", "return_general"),
        ("Возврат нет ГП залог наблюд.docx", "return_no_duty"),
        ("Переход из упрощенки в основное производство конкурс.docx", "simplified_to_main"),
    ])
    def test_роли_промежуточных(self, имя, роль):
        assert file_role(имя) == роль

    def test_отложение_3_лицо_не_путается_с_общим(self):
        # Узкое правило раньше широкого: иначе «3 лицо» уедет в общее отложение.
        assert file_role("Отложение 3 лицо рестр+реал.docx") != "postponement"


class TestПроцедураПоИмени:
    @pytest.mark.parametrize("имя,процедура", [
        ("Определение о принятии реализация.docx", "realization"),
        ("Определение о принятии реструктуризация.docx", "restructuring"),
        ("Определение о принятии наблюдение.docx", "observation"),
        ("Определение о принятии КОНКУРСНОЕ.docx", "competition"),
        ("Определение о принятии конкурсное.docx", "competition"),
        ("Определение БД иное кокнурсное.docx", "competition"),
    ])
    def test_опознаётся(self, имя, процедура):
        assert file_procedures(имя) == {процедура}

    def test_без_токена_процедуры(self):
        # Такой файл годится любой процедуре.
        assert file_procedures("Определение о принятии.docx") == frozenset()

    @pytest.mark.parametrize("имя,процедуры", [
        ("Отложение рестр+реал.docx", {"restructuring", "realization"}),
        ("Отложение залог наблюд+конкурс.docx", {"observation", "competition"}),
        ("Продление БД наблюдение+конкурсное.docx", {"observation", "competition"}),
        ("Переход из упрощенки в основное производство наблюд.docx", {"observation"}),
    ])
    def test_файл_на_две_процедуры(self, имя, процедуры):
        # Сокращённые формы: «рестр», «реал», «наблюд», «конкурс».
        assert file_procedures(имя) == процедуры


class TestНормализация:
    def test_регистр_ё_подчёркивание(self):
        assert normalize_name("Определение_БД_НЕТ_ГП_Залог.docx") == "определение бд нет гп залог"

    def test_восклицательный_знак_и_копия(self):
        assert normalize_name("!Принятие (Копия).docx") == "принятие"

    @pytest.mark.parametrize("с_ё,с_е", [
        ("Переход из упрощёнки в основное.docx", "Переход из упрощенки в основное.docx"),
        ("Определение о приёме.docx", "Определение о приеме.docx"),
    ])
    def test_ё_и_е_дают_одно_имя(self, с_ё, с_е):
        # В «Первоначальных» ё пока не встречается, но имена не унифицированы.
        assert normalize_name(с_ё) == normalize_name(с_е)


class TestПапкаПоОсям:
    def test_фл_залог(self, корень):
        итог = section_folder(корень, entity="individual", collateral=True)
        assert итог.folder is not None, итог.reason
        assert итог.folder.parts[-3:] == ("Кредиторы", "Залог", SECTION_INITIAL)

    def test_юл_статус_перед_залогом(self, корень):
        итог = section_folder(корень, entity="legal", status="liquidation", collateral=False)
        assert итог.folder is not None, итог.reason
        assert итог.folder.parts[-3:] == ("Ликвидируемый", "Незалог", SECTION_INITIAL)

    def test_фнс_без_статуса_и_залога(self, корень):
        # У ФНС залог и статус игнорируются: всегда ФНС\Незалог.
        итог = section_folder(корень, entity="legal", applicant="fns",
                              status="liquidation", collateral=True)
        assert итог.folder is not None, итог.reason
        assert итог.folder.parts[-3:] == ("ФНС", "Незалог", SECTION_INITIAL)

    def test_умерший_залог_внутри_раздела(self, корень):
        итог = section_folder(корень, entity="individual", status="deceased", collateral=True)
        assert итог.folder is not None, итог.reason
        assert итог.folder.parts[-3:] == ("Умерший", SECTION_INITIAL, "залог")

    def test_у_фл_нет_папки_статуса(self, корень):
        итог = section_folder(корень, entity="individual", collateral=False)
        assert "Обычный" not in итог.folder.parts

    def test_неизвестное_лицо(self, корень):
        итог = section_folder(корень, entity="робот")
        assert итог.folder is None
        assert "неизвестный тип лица" in итог.reason

    def test_неизвестный_статус(self, корень):
        итог = section_folder(корень, entity="legal", status="летающий")
        assert итог.folder is None
        assert "неизвестный статус" in итог.reason


# Все сочетания осей ветки РТК: лицо, заявитель, статус, залог.
ОСИ_РТК = (
    [("individual", "creditors", "", z) for z in (True, False)]
    + [("ip", "creditors", "", z) for z in (True, False)]
    + [("individual", "creditors", "deceased", z) for z in (True, False)]
    + [(e, "creditors", s, z) for e in ("legal", "kfh")
       for s in ("", "liquidation", "absent") for z in (True, False)]
    + [(e, "fns", "", False) for e in ("individual", "ip", "legal", "kfh")]
)
ПРОЦЕДУРЫ = {
    "individual": ("realization", "restructuring"),
    "ip": ("realization", "restructuring"),
    "legal": ("observation", "competition"),
    "kfh": ("observation", "competition"),
}


class TestРеальноеДерево:
    @pytest.mark.parametrize("лицо,заявитель,статус,залог", ОСИ_РТК)
    def test_папка_раздела_существует(self, корень, лицо, заявитель, статус, залог):
        итог = section_folder(корень, entity=лицо, applicant=заявитель,
                              status=статус, collateral=залог)
        assert итог.folder is not None, итог.reason
        assert итог.folder.is_dir()

    @pytest.mark.parametrize("лицо,заявитель,статус,залог", ОСИ_РТК)
    def test_каждый_файл_опознан(self, корень, лицо, заявитель, статус, залог):
        папка = section_folder(корень, entity=лицо, applicant=заявитель,
                               status=статус, collateral=залог).folder
        безродные = [p.name for p in act_files(папка) if file_role(p.name) is None]
        assert not безродные, "в %s не опознаны: %s" % (папка, безродные)

    @pytest.mark.parametrize("лицо,заявитель,статус,залог", ОСИ_РТК)
    def test_ни_одной_неоднозначности(self, корень, лицо, заявитель, статус, залог):
        спорные = []
        for процедура in ПРОЦЕДУРЫ[лицо]:
            for роль in РОЛИ:
                итог = resolve(корень, entity=лицо, applicant=заявитель, status=статус,
                               collateral=залог, role=роль, procedure=процедура)
                if итог.path is None and "неоднозначно" in итог.reason:
                    спорные.append("%s/%s: %s" % (процедура, роль, итог.reason))
        assert not спорные, спорные

    @pytest.mark.parametrize("лицо,заявитель,статус,залог", ОСИ_РТК)
    def test_промежуточные_опознаны_и_однозначны(self, корень, лицо, заявитель, статус, залог):
        папка = section_folder(корень, entity=лицо, applicant=заявитель, status=статус,
                               collateral=залог, section=SECTION_INTERMEDIATE).folder
        assert папка is not None and папка.is_dir()
        безродные = [p.name for p in act_files(папка) if file_role(p.name) is None]
        assert not безродные, "в %s не опознаны: %s" % (папка, безродные)

        спорные = []
        for процедура in ПРОЦЕДУРЫ[лицо]:
            for роль in INTERMEDIATE_ACT_ROLES.values():
                итог = resolve(корень, entity=лицо, applicant=заявитель, status=статус,
                               collateral=залог, role=роль, procedure=процедура,
                               section=SECTION_INTERMEDIATE)
                if итог.path is None and "неоднозначно" in итог.reason:
                    спорные.append("%s/%s: %s" % (процедура, роль, итог.reason))
        assert not спорные, спорные

    @pytest.mark.parametrize("лицо,процедура", [
        ("individual", "realization"), ("individual", "restructuring"),
        ("ip", "realization"), ("ip", "restructuring"),
        ("legal", "competition"), ("kfh", "competition"),
    ])
    def test_пять_ролей_с_залогом_находятся(self, корень, лицо, процедура):
        статус = "" if лицо in ("individual", "ip") else ""
        for роль in РОЛИ:
            итог = resolve(корень, entity=лицо, status=статус, collateral=True,
                           role=роль, procedure=процедура)
            assert итог.path is not None, "%s %s %s: %s" % (лицо, процедура, роль, итог.reason)
            assert итог.path.is_file()

    def test_умерший_только_реализация(self, корень):
        есть = resolve(корень, entity="individual", status="deceased", collateral=False,
                       role="acceptance", procedure="realization")
        нет = resolve(корень, entity="individual", status="deceased", collateral=False,
                      role="acceptance", procedure="restructuring")
        assert есть.path is not None, есть.reason
        assert нет.path is None and "реструктур" not in нет.reason.lower()

    def test_у_фнс_нет_роли_нет_гп(self, корень):
        итог = resolve(корень, entity="individual", applicant="fns",
                       role="no_motion_no_duty", procedure="realization")
        assert итог.path is None
        assert "нет акта роли" in итог.reason

    def test_залоговый_акт_не_ищется_в_незалоге(self, корень):
        итог = resolve(корень, entity="individual", collateral=False,
                       role="no_motion_no_duty_collateral", procedure="realization")
        assert итог.path is None

    def test_ликвидируемому_залоговый_акт_есть_и_в_незалоге(self, корень):
        # Решение юристов: отдельный акт лежит в обеих папках.
        итог = resolve(корень, entity="legal", status="liquidation", collateral=False,
                       role="no_motion_no_duty_collateral", procedure="competition")
        assert итог.path is not None, итог.reason


class TestВыборВПапке:
    def _папка(self, tmp_path, *имена):
        for имя in имена:
            (tmp_path / имя).write_bytes(b"docx")
        return tmp_path

    def test_точная_процедура_важнее_файла_без_процедуры(self, tmp_path):
        папка = self._папка(tmp_path, "Определение о принятии.docx",
                            "Определение о принятии реализация.docx")
        итог = pick_file(папка, "acceptance", "realization")
        assert итог.path.name == "Определение о принятии реализация.docx"

    def test_файл_без_процедуры_подходит_любой(self, tmp_path):
        папка = self._папка(tmp_path, "Определение о принятии.docx")
        assert pick_file(папка, "acceptance", "observation").path is not None

    def test_два_кандидата_отказ_а_не_первый(self, tmp_path):
        папка = self._папка(tmp_path, "Определение о принятии реализация.docx",
                            "Определение о принятии реализация копия2.docx")
        итог = pick_file(папка, "acceptance", "realization")
        assert итог.path is None
        assert "неоднозначно" in итог.reason

    def test_файл_блокировки_word_пропускается(self, tmp_path):
        папка = self._папка(tmp_path, "Определение о принятии реализация.docx",
                            "~$пределение о принятии реализация.docx")
        итог = pick_file(папка, "acceptance", "realization")
        assert итог.path is not None, итог.reason
        assert not итог.path.name.startswith("~$")

    def test_нет_роли_в_папке(self, tmp_path):
        папка = self._папка(tmp_path, "Отложение.docx")
        итог = pick_file(папка, "acceptance", "realization")
        assert итог.path is None
        assert "нет акта роли" in итог.reason

    def test_без_процедуры_берётся_единственный(self, tmp_path):
        папка = self._папка(tmp_path, "Определение БД иное наблюдение.docx")
        assert pick_file(папка, "no_motion_other").path is not None


class TestРегистрИмёнПапок:
    def test_залог_со_строчной_находится(self, tmp_path):
        # У умершего папки «залог»/«незалог» со строчной — сравниваем без регистра.
        (tmp_path / "Банкротство" / "Включение в РТК" / "ФЛ" / "кредиторы").mkdir(parents=True)
        найдено = child_dir(tmp_path / "Банкротство" / "Включение в РТК" / "ФЛ", "Кредиторы")
        assert найдено is not None
        assert найдено.name == "кредиторы", "путь должен быть реальным с диска"

    def test_ё_и_е_равны(self, tmp_path):
        (tmp_path / "Умерший").mkdir()
        assert child_dir(tmp_path, "Умерщий") is None
        assert child_dir(tmp_path, "Умерший") is not None
        (tmp_path / "Зелёный").mkdir()
        assert child_dir(tmp_path, "Зеленый") is not None

    def test_файл_не_считается_папкой(self, tmp_path):
        (tmp_path / "Банкротство").write_text("файл", encoding="utf-8")
        assert child_dir(tmp_path, "Банкротство") is None

    def test_нет_папки_возвращает_none(self, tmp_path):
        assert child_dir(tmp_path / "нет-такой", "Банкротство") is None


class TestПапкаНеНайдена:
    def test_причина_названа(self, tmp_path):
        (tmp_path / "Банкротство").mkdir()
        итог = section_folder(tmp_path, entity="individual", collateral=True)
        assert итог.folder is None
        assert "нет папки" in итог.reason

    def test_resolve_возвращает_причину_папки(self, tmp_path):
        итог = resolve(tmp_path, entity="legal", role="acceptance", procedure="competition")
        assert итог.path is None
        assert "нет папки" in итог.reason
