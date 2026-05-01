from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "S&M Portal"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DB_CONNECTION_STRING: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # File Storage: "local" or "azure_blob"
    FILE_STORAGE_MODE: str = "local"
    LOCAL_STORAGE_PATH: str = "uploads"

    # Azure Blob Storage (used when FILE_STORAGE_MODE=azure_blob)
    AZURE_BLOB_CONNECTION_STRING: str = ""
    AZURE_BLOB_CONTAINER: str = "srmb-resources"
    AZURE_BLOB_DIRECTORY: str = "snmportal"

    # KPI Studio — connection string the KPI executor uses to run user-authored
    # SQL. Defaults to DB_CONNECTION_STRING when blank. Strongly recommended:
    # point this at a SQL Server login with SELECT-only permissions on the
    # tables/views you want exposed (see kpisetup.md).
    KPI_DSN: str = ""

    # KPI Studio — LLM provider for natural-language → SQL (Phase A3+).
    # One of: openai | azure_openai | gemini | cerebras | ollama_cloud
    # Leave blank to disable LLM features (manual SQL still works).
    KPI_LLM_PROVIDER: str = ""

    # OpenAI (wired first; Cerebras + Ollama Cloud reuse the same impl).
    KPI_OPENAI_API_KEY: str = ""
    KPI_OPENAI_MODEL: str = "gpt-4o-mini"
    KPI_OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Cerebras / Ollama Cloud env vars are read by the kpi_studio factory
    # directly from the process environment when their providers are
    # selected — no need to enumerate them in Settings unless you want
    # validation. See kpisetup.md for the full list.

    # CORS
    CORS_ORIGINS: str = "http://localhost:4200"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
