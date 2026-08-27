from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    storage_dir: Path = Path("storage")
    upload_subdir: str = "uploads"
    highlighted_subdir: str = "highlighted"
    db_filename: str = "bomcoc.db"
    max_upload_mb: int = 100
    default_strategy: str = "auto"  # auto | fast | hi_res | ocr_only
    ocr_languages: str = "eng"
    # If unset, auth is a no-op (local `uvicorn --reload` stays friction-free).
    # If set, every /api/* and /documents/* route requires a matching X-API-Key header.
    api_key: str | None = None
    allowed_origins: list[str] = ["http://localhost:5173"]
    parse_timeout_seconds: int = 120

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / self.upload_subdir

    @property
    def highlighted_dir(self) -> Path:
        return self.storage_dir / self.highlighted_subdir

    @property
    def db_path(self) -> Path:
        """SQLite database for structured records (parsed-document metadata,
        BOMs, COCs) — see app/db.py. Raw files (uploads, highlighted PDFs)
        stay on disk under upload_dir/highlighted_dir; only those two need
        their own subdirectory."""
        return self.storage_dir / self.db_filename

    model_config = SettingsConfigDict(env_prefix="BOMCOC_")


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.highlighted_dir.mkdir(parents=True, exist_ok=True)
