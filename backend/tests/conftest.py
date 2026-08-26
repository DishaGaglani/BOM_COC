import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own throwaway storage_dir instead of writing into
    the real backend/storage/ — settings.upload_dir/bom_dir/etc. are
    properties computed from storage_dir, so patching that one attribute is
    enough."""
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    for directory in (
        settings.upload_dir,
        settings.parsed_dir,
        settings.bom_dir,
        settings.coc_dir,
        settings.highlighted_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    yield
