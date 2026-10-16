"""Имя скачанного акта не теряется после перезапуска бэкенда: подпись лежит рядом."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

КОРЕНЬ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(КОРЕНЬ / "app"))

main = pytest.importorskip("main")

ПОДПИСЬ = "Определение о принятии"
ДОЛЖНИК = "Иванов Иван Иванович"


@pytest.fixture
def акт_без_реестра():
    """Файл и подпись на диске, в памяти — ничего (как после перезапуска)."""
    генератор = main.document_generator
    doc_id = "тест-подпись-1"
    docx = генератор.generated_dir / f"{doc_id}.docx"
    docx.parent.mkdir(parents=True, exist_ok=True)
    docx.write_bytes(b"PK\x03\x04 fake docx")
    мета = генератор.generated_dir / f"{doc_id}.json"
    мета.write_text(json.dumps({"document_name": ПОДПИСЬ,
                                "data": {"debtorName": ДОЛЖНИК}}, ensure_ascii=False),
                    encoding="utf-8")
    генератор.documents.pop(doc_id, None)
    yield doc_id
    docx.unlink(missing_ok=True)
    мета.unlink(missing_ok=True)


class TestПодписьСДиска:
    def test_имя_акта_из_подписи(self, акт_без_реестра):
        сведения = main.document_generator.document_meta(акт_без_реестра)
        assert сведения["document_name"] == ПОДПИСЬ

    def test_память_старше_диска(self, акт_без_реестра):
        генератор = main.document_generator
        генератор.documents[акт_без_реестра] = {"document_name": "Из памяти"}
        try:
            assert генератор.document_meta(акт_без_реестра)["document_name"] == "Из памяти"
        finally:
            генератор.documents.pop(акт_без_реестра, None)

    def test_без_подписи_пусто(self):
        assert main.document_generator.document_meta("такого-акта-нет") == {}

    def test_имя_архива_из_подписи(self, акт_без_реестра):
        ответ = asyncio.run(main.download_zip_get(ids=акт_без_реестра))
        assert ответ.status_code == 200
        cd = ответ.headers["content-disposition"]
        assert "%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2" in cd, cd


class TestГенерацияПишетПодпись:
    def test_подпись_появляется_рядом_с_каждым_актом(self):
        """Без этого скачанный после перезапуска акт назывался бы «document_<uuid>»."""
        from document_generator import DocumentGenerator

        генератор = DocumentGenerator()
        акты = ["acceptance_definition"]
        data = {
            "caseNumber": "А53-1234/2026", "debtorName": ДОЛЖНИК,
            "applicantName": ДОЛЖНИК, "creditorName": "ПАО Сбербанк",
            "judge": "Ерёмин Ф.Ф.", "date": "17.07.2026", "obligations": [],
            "selectedApplicationKind": "rtk", "selectedEntityType": "individual",
            "selectedCollateralOption": "no_collateral",
            "selectedActsIds": ",".join(акты),
            "selectedActsData": json.dumps([{"id": a, "selected": True} for a in акты]),
        }
        результат = генератор.generate("rtk_single_obligation", data)
        assert результат["success"], результат
        ids = результат.get("document_ids") or []
        assert ids, результат
        try:
            for doc_id in ids:
                подпись = генератор.generated_dir / f"{doc_id}.json"
                assert подпись.is_file(), подпись
                записано = json.loads(подпись.read_text(encoding="utf-8"))
                assert записано["document_name"], записано
                assert записано["data"]["debtorName"] == ДОЛЖНИК
        finally:
            for doc_id in ids:
                генератор.delete_document(doc_id)

    def test_файл_подписи_рядом_с_актом(self, tmp_path, monkeypatch):
        from document_generator import DocumentGenerator

        генератор = DocumentGenerator()
        monkeypatch.setattr(генератор, "generated_dir", tmp_path)
        генератор._save_document_meta("abc", ПОДПИСЬ, "acceptance",
                                      {"debtorName": ДОЛЖНИК, "caseNumber": "А53-1/2026"})
        записано = json.loads((tmp_path / "abc.json").read_text(encoding="utf-8"))
        assert записано["document_name"] == ПОДПИСЬ
        assert записано["document_type"] == "acceptance"
        # Храним только то, из чего строится имя архива: данные генерации тяжёлые.
        assert записано["data"] == {"debtorName": ДОЛЖНИК}

    def test_заявитель_когда_должника_нет(self, tmp_path, monkeypatch):
        """У самобанкрота заявление подаёт сам должник: имя лежит в applicantName."""
        from document_generator import DocumentGenerator

        генератор = DocumentGenerator()
        monkeypatch.setattr(генератор, "generated_dir", tmp_path)
        генератор._save_document_meta("abc", ПОДПИСЬ, "acceptance",
                                      {"applicantName": ДОЛЖНИК})
        записано = json.loads((tmp_path / "abc.json").read_text(encoding="utf-8"))
        assert записано["data"] == {"applicantName": ДОЛЖНИК}

    def test_удаление_акта_сносит_подпись(self, tmp_path, monkeypatch):
        from document_generator import DocumentGenerator

        генератор = DocumentGenerator()
        monkeypatch.setattr(генератор, "generated_dir", tmp_path)
        docx = tmp_path / "abc.docx"
        docx.write_bytes(b"PK\x03\x04")
        генератор._save_document_meta("abc", ПОДПИСЬ, "acceptance", {})
        генератор.documents["abc"] = {"file_path": str(docx),
                                      "generation_date": "2026-10-16T00:00:00"}
        assert генератор.delete_document("abc")
        assert not docx.exists()
        assert not (tmp_path / "abc.json").exists()
