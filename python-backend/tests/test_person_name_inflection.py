"""Общие падежи ФИО и защита от чужого рода, числа и словарной парадигмы."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from docx import Document

from generator_inflection_mixin import GeneratorInflectionMixin
from inflection_mixin import InflectionMixin
from morph_utils import (
    detect_gender,
    get_name_morph,
    inflect_full_name,
    inflect_surname,
    refresh_debtor_case_forms,
)

CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
NAMES = [
    (
        "Ароян Ваче Рушани",
        (
            "Ароян Ваче Рушани",
            "Арояна Ваче Рушани",
            "Арояну Ваче Рушани",
            "Арояна Ваче Рушани",
            "Арояном Ваче Рушани",
            "Арояне Ваче Рушани",
        ),
    ),
    ("Ароян Гаяне Рушани", ("Ароян Гаяне Рушани",) * 6),
    (
        "Иванов Никита Ильич",
        (
            "Иванов Никита Ильич",
            "Иванова Никиты Ильича",
            "Иванову Никите Ильичу",
            "Иванова Никиту Ильича",
            "Ивановым Никитой Ильичом",
            "Иванове Никите Ильиче",
        ),
    ),
    (
        "Иванов Дима Петрович",
        (
            "Иванов Дима Петрович",
            "Иванова Димы Петровича",
            "Иванову Диме Петровичу",
            "Иванова Диму Петровича",
            "Ивановым Димой Петровичем",
            "Иванове Диме Петровиче",
        ),
    ),
    (
        "Петрова Любовь Ивановна",
        (
            "Петрова Любовь Ивановна",
            "Петровой Любови Ивановны",
            "Петровой Любови Ивановне",
            "Петрову Любовь Ивановну",
            "Петровой Любовью Ивановной",
            "Петровой Любови Ивановне",
        ),
    ),
    (
        "Путова Совдаш Ромзановна",
        (
            "Путова Совдаш Ромзановна",
            "Путовой Совдаш Ромзановны",
            "Путовой Совдаш Ромзановне",
            "Путову Совдаш Ромзановну",
            "Путовой Совдаш Ромзановной",
            "Путовой Совдаш Ромзановне",
        ),
    ),
    (
        "Шишлина Сальвиназ Маматовна",
        (
            "Шишлина Сальвиназ Маматовна",
            "Шишлиной Сальвиназ Маматовны",
            "Шишлиной Сальвиназ Маматовне",
            "Шишлину Сальвиназ Маматовну",
            "Шишлиной Сальвиназ Маматовной",
            "Шишлиной Сальвиназ Маматовне",
        ),
    ),
    (
        "Седых Павел Ильич",
        (
            "Седых Павел Ильич",
            "Седых Павла Ильича",
            "Седых Павлу Ильичу",
            "Седых Павла Ильича",
            "Седых Павлом Ильичом",
            "Седых Павле Ильиче",
        ),
    ),
    (
        "Шевченко Андрей Иванович",
        (
            "Шевченко Андрей Иванович",
            "Шевченко Андрея Ивановича",
            "Шевченко Андрею Ивановичу",
            "Шевченко Андрея Ивановича",
            "Шевченко Андреем Ивановичем",
            "Шевченко Андрее Ивановиче",
        ),
    ),
    (
        "Иванов-Петров Иван Петрович",
        (
            "Иванов-Петров Иван Петрович",
            "Иванова-Петрова Ивана Петровича",
            "Иванову-Петрову Ивану Петровичу",
            "Иванова-Петрова Ивана Петровича",
            "Ивановым-Петровым Иваном Петровичем",
            "Иванове-Петрове Иване Петровиче",
        ),
    ),
    (
        "Нуриева Елена Валидиновна",
        (
            "Нуриева Елена Валидиновна",
            "Нуриевой Елены Валидиновны",
            "Нуриевой Елене Валидиновне",
            "Нуриеву Елену Валидиновну",
            "Нуриевой Еленой Валидиновной",
            "Нуриевой Елене Валидиновне",
        ),
    ),
]


NAMES += [
    (
        "Песня Сергей Николаевич",
        (
            "Песня Сергей Николаевич",
            "Песни Сергея Николаевича",
            "Песне Сергею Николаевичу",
            "Песню Сергея Николаевича",
            "Песней Сергеем Николаевичем",
            "Песне Сергее Николаевиче",
        ),
    ),
    (
        "Галета Ольга Николаевна",
        (
            "Галета Ольга Николаевна",
            "Галеты Ольги Николаевны",
            "Галете Ольге Николаевне",
            "Галету Ольгу Николаевну",
            "Галетой Ольгой Николаевной",
            "Галете Ольге Николаевне",
        ),
    ),
    (
        "Манукян Сос Жораевич",
        (
            "Манукян Сос Жораевич",
            "Манукяна Соса Жораевича",
            "Манукяну Сосу Жораевичу",
            "Манукяна Соса Жораевича",
            "Манукяном Сосом Жораевичем",
            "Манукяне Сосе Жораевиче",
        ),
    ),
    (
        "Ароян Жан-Люк Рушани",
        (
            "Ароян Жан-Люк Рушани",
            "Арояна Жана-Люка Рушани",
            "Арояну Жану-Люку Рушани",
            "Арояна Жана-Люка Рушани",
            "Арояном Жаном-Люком Рушани",
            "Арояне Жане-Люке Рушани",
        ),
    ),
]


class AnalyzerNames(InflectionMixin):
    morph = get_name_morph()


@pytest.mark.parametrize("name,forms", NAMES)
@pytest.mark.parametrize("index,case", enumerate(CASES))
def test_same_expected_forms_in_analyzer_and_generator(name, forms, index, case):
    assert AnalyzerNames()._inflect_full_name(name, case) == forms[index]
    assert GeneratorInflectionMixin()._decline_person_name(name, case) == forms[index]


@pytest.mark.parametrize("case", CASES)
def test_uppercase_preserved_in_analyzer(case):
    assert AnalyzerNames()._inflect_full_name(NAMES[0][0].upper(), case) == NAMES[0][1][CASES.index(case)].upper()


@pytest.mark.parametrize(
    "tokens,gender",
    [
        (["Ароян", "Ваче", "Рушани"], "masc"),
        (["Ароян", "Гаяне", "Рушани"], "femn"),
        (["Иванов", "Никита"], "masc"),
        (["Ароян", "Жан-Люк", "Рушани"], "masc"),
        (["Ким", "Саша"], None),
        (["Гулиев", "Али", "Аслан", "оглы"], "masc"),
        (["Гулиева", "Лейла", "Аслан", "кызы"], "femn"),
    ],
)
def test_gender_is_not_guessed_from_final_vowel(tokens, gender):
    assert detect_gender(tokens) == gender


def test_unknown_gender_preserved_and_reported():
    fields = {"applicantName": "Ким Саша", "applicantNameGenitive": "Кимов Саш"}
    warnings = refresh_debtor_case_forms(fields, get_name_morph())
    assert warnings and "род" in warnings[0]
    assert fields["applicantNameGenitive"] == "Ким Саша"


def test_rebuild_stale_forms_without_mutating_names_or_finances():
    fields = {
        "applicantName": "Ароян Ваче Рушани",
        "debtorName": "Ароян Ваче Рушани",
        "applicantNameGenitive": "Ароян Вача Рушани",
        "applicantNameInstrumental": "Шалинским городским судом",
        "totalDebt": "100,00",
        "debtors": [{"name": "Ароян Ваче Рушани"}],
    }
    original = deepcopy(fields)
    assert refresh_debtor_case_forms(fields, get_name_morph()) == []
    assert fields["applicantNameGenitive"] == "Арояна Ваче Рушани"
    assert fields["applicantNameDative"] == "Арояну Ваче Рушани"
    assert fields["applicantNameInstrumental"] == "Арояном Ваче Рушани"
    assert fields["applicantNameAccusative"] == "Арояна Ваче Рушани"
    for key in ("applicantName", "debtorName", "totalDebt", "debtors"):
        assert fields[key] == original[key]


def test_each_person_in_list_has_own_gender():
    fields = {"applicantName": "Ароян Ваче Рушани, Ароян Гаяне Рушани"}
    refresh_debtor_case_forms(fields, get_name_morph())
    assert fields["applicantNameDative"] == "Арояну Ваче Рушани, Ароян Гаяне Рушани"


@pytest.mark.parametrize("prefix", ["ИП ", "Глава КФХ ИП "])
def test_prefix_is_not_part_of_person_name(prefix):
    fields = {"applicantName": prefix + "Ароян Ваче Рушани"}
    refresh_debtor_case_forms(fields, get_name_morph())
    assert fields["applicantNameDative"] == "Арояну Ваче Рушани"
    assert fields["applicantName"] == prefix + "Ароян Ваче Рушани"


def test_legal_entity_is_unchanged():
    fields = {"entityType": "legal", "applicantName": "ООО «Ромашка»", "applicantNameGenitive": "ООО «Ромашка»"}
    before = deepcopy(fields)
    assert refresh_debtor_case_forms(fields, get_name_morph()) == []
    assert fields == before


def test_no_dictionary_preserves_name_and_reports_problem():
    fields = {"applicantName": "Ароян Ваче Рушани"}
    warnings = refresh_debtor_case_forms(fields, None)
    assert warnings and "недоступен" in warnings[0]
    assert fields["applicantNameInstrumental"] == fields["applicantName"]


def test_surname_plural_candidate_is_never_used():
    import pymorphy3

    tag = pymorphy3.MorphAnalyzer().parse("люди")[0].tag
    candidate = SimpleNamespace(
        tag=tag,
        normal_form="люди",
        is_known=True,
        inflect=lambda _: pytest.fail("Множественное число нельзя склонять как фамилию"),
    )
    assert inflect_surname(SimpleNamespace(parse=lambda _: [candidate]), "Люди", "datv", "masc") == "Люди"


def test_initials_are_preserved():
    assert inflect_full_name(get_name_morph(), "Ароян В.Р.", "gent", "masc") == "Арояна В.Р."


def test_generated_markers_use_refreshed_name():
    from document_generator import DocumentGenerator

    data = {
        "entityType": "individual",
        "applicantName": "Ароян Ваче Рушани",
        "debtorName": "Ароян Ваче Рушани",
        "applicantNameGenitive": "Ароян Вача Рушани",
        "applicantNameDative": "Ароян Вачу Рушани",
        "applicantNameInstrumental": "Ароян Вачом Рушаней",
        "applicantNameAccusative": "Ароян Вача Рушаню",
    }
    before = deepcopy(data)
    doc = Document()
    doc.add_paragraph("[2] | [2.1] | [2.2] | [2.3] | [2.4]")
    DocumentGenerator().replace_document_data(doc, data)
    text = doc.paragraphs[0].text
    assert (
        text == "Ароян Ваче Рушани | Арояна Ваче Рушани | Арояну Ваче Рушани | Арояном Ваче Рушани | Арояна Ваче Рушани"
    )
    assert data == before


def test_analyze_refreshes_raw_case_capture():
    from document_analyzer import DocumentAnalyzer

    result = DocumentAnalyzer().analyze_from_text(
        "Арбитражный суд Ростовской области\\n"
        "Кредитор: ООО «Ромашка»\\nДолжник: Ароян Ваче Рушани\\n"
        "Заявление о включении в реестр требований кредиторов\\n"
        "В рамках дела о банкротстве Ароян Вача Рушани.\\n"
        "Прошу включить требование в размере 1000,00 руб."
    )
    fields = result["fields"]
    assert fields["applicantName"] == "Ароян Ваче Рушани"
    assert fields["applicantNameGenitive"] == "Арояна Ваче Рушани"
    assert fields["applicantNameInstrumental"] == "Арояном Ваче Рушани"


def test_child_and_representative_have_independent_cases():
    source = "Рябова Лиана Сергеевна в лице законного представителя Федотьев Александр Артаваздович"
    expected = "Рябовой Лиане Сергеевне в лице законного представителя Федотьева Александра Артаваздовича"
    assert AnalyzerNames()._inflect_full_name(source, "datv") == expected
    assert GeneratorInflectionMixin()._decline_person_name(source, "datv") == expected


def test_oblique_surname_does_not_become_new_indeclinable_surname():
    source = "Шишлину Азиз Аслан Емин"
    assert AnalyzerNames()._inflect_full_name(source, "gent") == "Шишлина Азиза Аслана Емина"


def test_business_prose_is_not_used_to_rebuild_a_person():
    fields = {
        "applicantName": "ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ПРОФЕССИОНАЛЬНАЯ",
        "applicantNameGenitive": "Хантемерьяна Евгения Александровича",
    }
    before = deepcopy(fields)
    refresh_debtor_case_forms(fields, get_name_morph())
    assert fields == before


@pytest.mark.parametrize(
    "case,expected", [("gent", "Путовой Совдаш"), ("datv", "Путовой Совдаш"), ("ablt", "Путовой Совдаш")]
)
def test_rare_two_part_name_never_uses_legacy_plural(case, expected):
    assert GeneratorInflectionMixin()._decline_person_name("Путова Совдаш", case) == expected
    assert AnalyzerNames()._inflect_full_name("Путова Совдаш", case) == expected


def test_guardian_already_genitive_is_not_inflected_as_a_woman():
    source = "Рябова Лиана Сергеевна в лице законного представителя Федотьева Александра Артаваздовича"
    expected = "Рябовой Лиане Сергеевне в лице законного представителя Федотьева Александра Артаваздовича"
    assert AnalyzerNames()._inflect_full_name(source, "datv") == expected
    assert GeneratorInflectionMixin()._decline_person_name(source, "datv") == expected


def test_existing_ip_label_is_preserved_outside_name():
    fields = {"applicantName": "ИП Иванов Иван Иванович", "applicantNameDative": "ИП Иванов Иван Иванович"}
    refresh_debtor_case_forms(fields, get_name_morph())
    assert fields["applicantNameDative"] == "ИП Иванову Ивану Ивановичу"


def test_api_reports_ambiguous_gender(tmp_path):
    from document_generator import DocumentGenerator

    generator = DocumentGenerator()
    generator.generated_dir = tmp_path
    data = {
        "applicantName": "Ким Саша",
        "debtorName": "Ким Саша",
        "entityType": "individual",
        "selectedEntityType": "individual",
        "sourceDocumentType": "rtk_application",
        "selectedApplicationKind": "rtk",
        "selectedCollateralOption": "no_collateral",
        "selectedActsIds": "acceptance_definition",
        "introducedProcedure": "realization",
    }
    result = generator.generate("rtk_single_obligation", data)
    assert result["success"], result
    assert any("род ФИО" in warning for warning in result.get("warnings", []))


def test_unknown_fio_does_not_fall_back_to_first_dictionary_parse():
    assert GeneratorInflectionMixin()._decline_person_name("Тырг Совдэ", "datv") == "Тырг Совдэ"


def test_stale_represented_child_cases_are_rebuilt():
    fields = {
        "applicantName": "Рябова Лиана Сергеевна в лице законного представителя Федотьева Александра Артаваздовича",
        "applicantNameDative": "Рябовой Лиане Сергеевне в лицу законному представителю Федотьеву Александру Артаваздовичу",
    }
    refresh_debtor_case_forms(fields, get_name_morph())
    assert (
        fields["applicantNameDative"]
        == "Рябовой Лиане Сергеевне в лице законного представителя Федотьева Александра Артаваздовича"
    )
