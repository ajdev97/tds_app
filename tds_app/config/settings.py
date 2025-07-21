# settings.py  (only the imports + model config changed)

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

class Settings(BaseSettings):
    """Central project settings loaded from environment or .env file."""

    # ---------- core files ----------
    daybook_file: str = "Daybook.xlsx"
    ledger_file: str = "Ledger.xlsx"
    form26q_file: str = "26Q.docx"

    # ---------- flags ----------
    verbose: bool = False
    odbc_dsn: str = "TallyODBC64_9000"          # ← new DSN setting

    # ---------- pydantic-config ----------
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Keep the convenient global for old imports
settings = get_settings()
