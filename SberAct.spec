# -*- mode: python ; coding: utf-8 -*-
# Сборка API-бэкенда (onedir): из корня проекта — pyinstaller SberAct.spec
# Результат: dist/SberAct/ — папка с SberAct(.exe) и зависимостями внутри.
#
# Пакуется ТОЛЬКО backend-API. Фронт грузит Electron напрямую (не бэкенд),
# конвертер поставляется отдельной папкой. Electron спавнит этот бинарник как
# API-сервер на 127.0.0.1:8000.

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH)
app_dir = project_root / 'python-backend' / 'app'

datas = []
binaries = []
hiddenimports = []

# Пакеты с данными/динамическими импортами (модели, словари) — тянем целиком.
# Отсутствующие в venv молча пропускаем (try/except), лишние в списке безвредны.
for pkg in (
    'spacy', 'ru_core_news_sm', 'thinc', 'srsly', 'catalogue', 'wasabi', 'blis',
    'natasha', 'navec', 'slovnet', 'razdel', 'ipymarkup',
    'pymorphy2', 'pymorphy2_dicts_ru', 'pymorphy3', 'pymorphy3_dicts_ru',
    'docx', 'pypdf',
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Шаблоны (read-only) — рядом с бинарником, чтобы можно было менять без пересборки.
for src, dest in (
    (project_root / "Shablony", "Shablony"),
    (project_root / "Templates", "Templates"),
    (project_root / "шаблоны актов без залогов", "шаблоны актов без залогов"),
):
    if src.exists():
        datas.append((str(src), dest))

# Локальные модули бэкенда: импортируются по имени (from document_analyzer import ...),
# статический анализ PyInstaller их не находит — перечисляем явно.
hiddenimports += [
    'amounts_mixin', 'classify_mixin', 'creditor_registry', 'document_analyzer',
    'document_generator', 'docx_edit', 'docx_ops_mixin', 'field_contract', 'fio_detector',
    'fns_data', 'fns_registry', 'formatting_mixin', 'generator_inflection_mixin',
    'inflection_mixin', 'ip_mixin', 'label_synonyms', 'morph_utils', 'nlp_natasha',
    'obligations_mixin', 'obligations_render_mixin', 'org_normalizer', 'parties_mixin',
    'paths', 'patterns', 'prior_collection_mixin', 'requisites_validation',
    'sro_data', 'sro_registry', 'template_manager', 'templates_resolver_mixin',
]
hiddenimports += [
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    'fastapi', 'starlette', 'pydantic',
]

a = Analysis(
    [str(app_dir / 'main.py')],
    pathex=[str(app_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'transformers', 'tensorflow', 'tensorboard', 'sklearn',
        'scikit-learn', 'nltk', 'pandas', 'triton', 'cupy',
        # webview больше не нужен: окно даёт Electron, бэкенд — чистый API
        'webview',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# onedir: exe без встроенных бинарников, всё складывает COLLECT рядом.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SberAct',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX выключен: сжатие нативных либ spacy/thinc/pymorphy ломает загрузку DLL.
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SberAct',
)
