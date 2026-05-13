import sys
from app.document_analyzer import DocumentAnalyzer


def run_check() -> int:
    analyzer = DocumentAnalyzer()

    sample_text = (
        "Взыскатель (кредитор):\n"
        "Публичное акционерное общество «Сбербанк России»\n"
        "рассмотрев в открытом судебном заседании материалы дела по иску "
        "публичного акционерного общества «Сбербанк России С Ип Борохова Василия Ивановича "
        "Сумму Задолженности По Кредитному Договору № 1111122202.24.2200 От 09.09.2025 "
        "В Размере 966982,28 Руб., В Том Числе:»\n"
        "Требование № 1 по кредитному договору № 1111122202.24.2200\n"
    )

    fields = analyzer.extract_ip_enforcement_fields(sample_text)
    obligations = analyzer.extract_obligations(sample_text, fields)

    creditor_name = (fields.get("creditorName") or "").strip()
    expected_creditor = "Сбербанк России"

    found_obligation = next(
        (o for o in obligations if (o.get("contractNumber") or "").strip() == "1111122202.24.2200"),
        None,
    )

    print("creditorName:", creditor_name or "<empty>")
    print("obligations:", obligations)

    errors = []
    if expected_creditor.lower() not in creditor_name.lower():
        errors.append(
            f"creditorName mismatch: expected to contain '{expected_creditor}', got '{creditor_name}'"
        )

    if not found_obligation:
        errors.append("contractNumber not extracted from 'Требование № ... по кредитному договору № ...'")
    else:
        contract_date = (found_obligation.get("contractDate") or "").strip()
        if contract_date != "09.09.2025":
            errors.append(f"contractDate mismatch: expected '09.09.2025', got '{contract_date}'")

    if errors:
        print("\nFAILED:")
        for err in errors:
            print("-", err)
        return 1

    print("\nOK: patterns work for provided sample.")
    return 0


if __name__ == "__main__":
    sys.exit(run_check())
