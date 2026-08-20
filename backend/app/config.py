from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://bomcoc:bomcoc@localhost:5432/bomcoc"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    storage_dir: str = "./storage"
    low_confidence_threshold: float = 0.6

    class Config:
        env_file = ".env"


settings = Settings()
