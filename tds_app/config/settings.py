"""
Global settings for the TDS App.
Values can be overridden via environment variables or a `.env` file in the
project root.  Example:

    DAYBOOK_FILE=MyDaybook.xlsx
    LEDGER_FILE=MyLedger.xlsx
"""

from pathlib import Path

from pydantic import Field
# OLD (v1 style) ➜ from pydantic import BaseSettings, Field
from pydantic_settings import BaseSettings  # ✅ NEW

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # C:/Projects/tds_app


class Settings(BaseSettings):
    # ── file paths ──────────────────────────────────────────────────────
    daybook_file: Path = Field(default=PROJECT_ROOT / "Daybook.xlsx")
    ledger_file: Path = Field(default=PROJECT_ROOT / "Ledger.xlsx")
    form26q_file: Path = Field(default=PROJECT_ROOT / "26Q.docx")

    # ── OpenAI settings (Step 1) ────────────────────────────────────────
    openai_api_key: str | None = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"

    # ── misc options ────────────────────────────────────────────────────
    verbose: bool = Field(default=False, env="TDS_VERBOSE")

    class Config:
        env_file = PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"


# Singleton helper so every module imports the same instance
settings = Settings()
