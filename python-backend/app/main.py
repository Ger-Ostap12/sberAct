from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
import json
import logging

from document_analyzer import DocumentAnalyzer
from document_generator import DocumentGenerator
from template_manager import TemplateManager

# Настройка логирования
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SberAct Document Generator API",
    description="API для анализа заявлений и генерации судебных актов",
    version="1.0.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить до конкретных доменов
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация компонентов
document_analyzer = DocumentAnalyzer()
document_generator = DocumentGenerator()
template_manager = TemplateManager()

@app.get("/")
async def root():
    return {"message": "SberAct Document Generator API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "components": {
        "analyzer": "ready",
        "generator": "ready",
        "templates": "ready"
    }}

@app.post("/analyze-document")
async def analyze_document(document: UploadFile = File(...)):
    """
    Анализирует загруженный документ и извлекает данные
    """
    print("🔍 API: Получен запрос на анализ документа")
    try:
        # Проверяем тип файла
        if not document.filename.endswith('.docx'):
            raise HTTPException(status_code=400, detail="Поддерживаются только файлы .docx")

        # Сохраняем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
            shutil.copyfileobj(document.file, tmp_file)
            tmp_path = tmp_file.name

        try:
            # Анализируем документ
            analysis_result = document_analyzer.analyze(tmp_path)

            return {
                "success": True,
                "data": analysis_result
            }
        finally:
            # Удаляем временный файл
            os.unlink(tmp_path)

    except ValueError as e:
        # Ошибки извлечения текста/поврежденный файл -> 400
        raise HTTPException(status_code=400, detail=f"Ошибка при анализе документа: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при анализе документа: {str(e)}")

@app.get("/templates")
async def get_templates():
    """
    Возвращает список доступных шаблонов
    """
    try:
        templates = template_manager.get_all_templates()
        return templates
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении шаблонов: {str(e)}")

@app.post("/generate-document")
async def generate_document(request_data: Dict[str, Any]):
    """
    Генерирует документ на основе выбранного шаблона и данных
    """
    print("🚀 API: Получен запрос на генерацию документа")
    print(f"📊 API: Данные запроса: {request_data}")
    try:
        # Извлекаем данные из запроса
        template_type = request_data.get("template_type")
        extracted_data = request_data.get("data")

        if not template_type or not extracted_data:
            raise HTTPException(status_code=400, detail="Отсутствуют обязательные поля: template_type или data")

        # Генерируем документ
        result = document_generator.generate(template_type, extracted_data)

        if result["success"]:
            # Проверяем, генерируется ли один документ или несколько
            if "documents" in result:
                # Генерируется несколько документов
                return {
                    "success": True,
                    "documents": result["documents"],
                    "document_ids": result["document_ids"],
                    "count": result["count"],
                    "message": f"Успешно сгенерировано {result['count']} документов"
                }
            else:
                # Генерируется один документ (старый формат)
                return {
                    "success": True,
                    "document_id": result["document_id"],
                    "file_path": result["file_path"]
                }
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации документа: {str(e)}")

@app.get("/download-document/{document_id}")
async def download_document(document_id: str):
    """
    Скачивает сгенерированный документ
    """
    try:
        # Ищем файл в папке generated
        generated_dir = "generated"
        document_path = os.path.join(generated_dir, f"{document_id}.docx")

        if not os.path.exists(document_path):
            raise HTTPException(status_code=404, detail="Документ не найден")

        filename = f"Судебный_акт_{document_id}.docx"

        return FileResponse(
            path=document_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при скачивании документа: {str(e)}")

@app.post("/download-all-documents")
async def download_all_documents(request: dict):
    """
    Скачивает все сгенерированные документы в виде ZIP архива
    """
    try:
        import zipfile
        import tempfile
        from pathlib import Path

        logger.info(f"🔽 API: Получен запрос на скачивание документов")
        logger.info(f"📋 API: Данные запроса: {request}")

        document_ids = request.get('document_ids', '')
        download_path = request.get('download_path', '')

        logger.info(f"📄 API: ID документов: {document_ids}")
        logger.info(f"📁 API: Путь для скачивания: {download_path}")

        # Парсим ID документов
        ids = document_ids.split(',') if document_ids else []

        if not ids:
            raise HTTPException(status_code=400, detail="Не указаны ID документов")

        # Определяем путь для сохранения
        if download_path:
            # Если указан путь, сохраняем туда
            download_dir = Path(download_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            zip_path = download_dir / "generated_documents.zip"
        else:
            # Иначе создаем временный файл
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            zip_path = Path(temp_zip.name)

        # Создаем ZIP архив
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            generated_dir = Path("generated")

            for doc_id in ids:
                file_path = generated_dir / f"{doc_id}.docx"
                if file_path.exists():
                    # Получаем информацию о документе для имени файла
                    doc_info = document_generator.documents.get(doc_id, {})
                    doc_name = doc_info.get('document_name', f'document_{doc_id}')

                    # Добавляем файл в архив
                    zipf.write(file_path, f"{doc_name}.docx")

        if download_path:
            # Если указан путь, возвращаем информацию о сохранении
            logger.info(f"✅ API: Документы сохранены в {zip_path}")
            return {
                "success": True,
                "message": f"Документы сохранены в {zip_path}",
                "file_path": str(zip_path)
            }
        else:
            # Иначе возвращаем файл для скачивания
            logger.info(f"✅ API: Возвращаем файл для скачивания: {zip_path}")
            return FileResponse(
                path=str(zip_path),
                filename="generated_documents.zip",
                media_type="application/zip"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании архива: {str(e)}")

@app.get("/download-paths")
async def get_download_paths():
    """
    Возвращает список доступных путей для сохранения документов
    """
    try:
        from pathlib import Path

        logger.info(f"📁 API: Получен запрос на список путей для скачивания")

        # Получаем корень проекта
        project_root = Path(__file__).parent.parent.parent.absolute()

        # Предлагаем несколько вариантов путей
        paths = [
            {
                "name": "Рабочий стол",
                "path": str(Path.home() / "Desktop"),
                "description": "Сохранить на рабочий стол"
            },
            {
                "name": "Папка проекта",
                "path": str(project_root / "generated"),
                "description": "Сохранить в папку проекта"
            },
            {
                "name": "Документы",
                "path": str(Path.home() / "Documents"),
                "description": "Сохранить в папку Документы"
            }
        ]

        return {
            "success": True,
            "paths": paths
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении путей: {str(e)}")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Удаляет сгенерированный документ
    """
    try:
        success = document_generator.delete_document(document_id)

        if success:
            return {"success": True, "message": "Документ удален"}
        else:
            raise HTTPException(status_code=404, detail="Документ не найден")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении документа: {str(e)}")

if __name__ == "__main__":
    # Создаем необходимые директории
    os.makedirs("temp", exist_ok=True)
    os.makedirs("generated", exist_ok=True)

    # Запускаем сервер
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
