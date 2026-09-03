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
    # forjinn.com-hosted flow (Qwen-based agent) that does both semantic
    # field extraction (app/services/semantic_extractor.py) and semantic
    # COC-vs-BOM comparison (app/services/semantic_validator.py) — same
    # flow, two jobs, distinguished by the "task" field in the request
    # payload (see forjinn_client.call_agent). The flow ID is part of the
    # URL path itself, e.g.
    # https://forjinn.com/api/v1/prediction/23715a87-e685-4ed3-9f07-98aeb705233a
    # — set via BOMCOC_FORJINN_API_URL. If unset, extraction has nothing to
    # call (extract_bom/extract_coc raise) and semantic validation is
    # skipped (only fast rule-based checks run).
    forjinn_api_url: str | None = None
    forjinn_api_key: str | None = None
    # 60s (a reasonable default for the small "validate" call) timed out in
    # practice on a real "extract" call over a multi-row BOM table — an LLM
    # reasoning over a full table needs more headroom than a single-item
    # compliance verdict does.
    forjinn_timeout_seconds: int = 180

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
