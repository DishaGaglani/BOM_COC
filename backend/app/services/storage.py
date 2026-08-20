import os
import shutil
import uuid

from app.config import settings

SUBDIRS = ["bom", "coc", "highlighted", "reports"]


def ensure_storage_dirs():
    for sub in SUBDIRS:
        os.makedirs(os.path.join(settings.storage_dir, sub), exist_ok=True)


def save_upload(subdir: str, filename: str, file_obj) -> str:
    ensure_storage_dirs()
    safe_name = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
    dest = os.path.join(settings.storage_dir, subdir, safe_name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return dest


def path_for(subdir: str, filename: str) -> str:
    return os.path.join(settings.storage_dir, subdir, filename)
