# -*- mode: python ; coding: utf-8 -*-
# Сборка: из корня проекта выполнить: pyinstaller SberAct.spec
# Результат (one-file): dist/SberAct (Linux) или dist/SberAct.exe (Windows)

import sys
from pathlib import Path

# Корень проекта (где лежит этот .spec)
project_root = Path(SPECPATH)
app_dir = project_root / 'python-backend' / 'app'

# Модель spacy ru_core_news_sm
datas = []
try:
    import ru_core_news_sm
    pkg_dir = Path(ru_core_news_sm.__path__[0])
    for sub in pkg_dir.iterdir():
        if sub.is_dir() and sub.name.startswith("ru_core_news_sm-"):
            datas.append((str(sub), "ru_core_news_sm"))
            break
    if not datas:
        datas.append((str(pkg_dir), "ru_core_news_sm"))
except Exception:
    pass
# Фронтенд (React build) и web-api.js
build_path = project_root / "electron-app" / "build"
if (build_path / "index.html").exists():
    datas.append((str(build_path), "frontend"))
static_path = app_dir / "static"
if static_path.exists():
    datas.append((str(static_path), "static"))
# Шаблоны
for src, dest in (
    (project_root / "emplates", "Templates"),
    (project_root / "Shablony", "Shablony"),
    (project_root / "Templates", "Templates"),
    (project_root / "шаблоны актов без залогов", "шаблоны актов без залогов"),
):
    if src.exists():
        datas.append((str(src), dest))

a = Analysis(
    [str(app_dir / 'main.py')],
    pathex=[str(app_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'starlette',
        'pydantic',
        'document_analyzer',
        'document_generator',
        'template_manager',
        'docx',
        'pypdf',
        'spacy',
        'ru_core_news_sm',
        'webview',
        'webview.platforms',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'webview.platforms.cef',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'transformers',
        'tensorflow',
        'tensorboard',
        'sklearn',
        'scikit-learn',
        'nltk',
        'pandas',
        'triton',
        'cupy',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SberAct',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
