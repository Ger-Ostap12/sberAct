"""Сборка закреплённых весов перед полным прогоном backend."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "python-backend" / "tools"))
from split_model import assemble
target = root / "python-backend/models/paraphrase-multilingual-MiniLM-L12-v2/model.safetensors"
if not (target.parent / "model.safetensors.parts/manifest.json").is_file():
    raise SystemExit("Pinned model parts are missing")
if not assemble(str(target)):
    raise SystemExit("Cannot assemble the backend model")
sys.path.insert(0, str(root / "python-backend/app"))
from semantic_classifier import _ensure_model
if not _ensure_model():
    raise SystemExit("Backend model cannot load; refusing optional semantic skips")
print("Pinned backend model assembled and loaded")
