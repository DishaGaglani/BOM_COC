import pytest

from app.config import settings
from app.db import init_db


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own throwaway storage_dir instead of writing into
    the real backend/storage/ — upload_dir/highlighted_dir/db_path are all
    properties computed from storage_dir, so patching that one attribute is
    enough. init_db() re-creates the schema in the new (empty) SQLite file,
    since app/db.py's own import-time init_db() already ran once against
    whatever storage_dir was in effect when the test process started."""
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    for directory in (settings.upload_dir, settings.highlighted_dir):
        directory.mkdir(parents=True, exist_ok=True)
    init_db()
    yield
