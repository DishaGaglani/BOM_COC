from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    storage_dir: Path = Path("storage")
    upload_subdir: str = "uploads"
    parsed_subdir: str = "parsed"
    bom_subdir: str = "bom"
    coc_subdir: str = "coc"
    highlighted_subdir: str = "highlighted"
    max_upload_mb: int = 100
    default_strategy: str = "auto"  # auto | fast | hi_res | ocr_only
    ocr_languages: str = "eng"

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / self.upload_subdir

    @property
    def parsed_dir(self) -> Path:
        return self.storage_dir / self.parsed_subdir

    @property
    def bom_dir(self) -> Path:
        return self.storage_dir / self.bom_subdir

    @property
    def coc_dir(self) -> Path:
        return self.storage_dir / self.coc_subdir

    @property
    def highlighted_dir(self) -> Path:
        return self.storage_dir / self.highlighted_subdir

    model_config = SettingsConfigDict(env_prefix="BOMCOC_")


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.parsed_dir.mkdir(parents=True, exist_ok=True)
settings.bom_dir.mkdir(parents=True, exist_ok=True)
settings.coc_dir.mkdir(parents=True, exist_ok=True)
settings.highlighted_dir.mkdir(parents=True, exist_ok=True)
