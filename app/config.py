import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Deterministic Recipe Service"
    data_dir: str = "data"
    db_url: str = "sqlite:///app.db"
    max_upload_mb: int = 10
    retention_days: int = 90
    timezone: str = "UTC"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"


@lru_cache()
def get_settings() -> Settings:
    # Load .env once
    load_dotenv()
    return Settings(
        app_name=os.getenv("APP_NAME", "Deterministic Recipe Service"),
        data_dir=os.getenv("DATA_DIR", "data"),
        db_url=os.getenv("DB_URL", "sqlite:///app.db"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
        retention_days=int(os.getenv("RETENTION_DAYS", "90")),
        timezone=os.getenv("TIMEZONE", "UTC"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
    )


def ensure_data_dir() -> None:
    settings = get_settings()
    os.makedirs(settings.data_dir, exist_ok=True)



