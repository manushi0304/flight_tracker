"""
Centralized, validated configuration. Everything is loaded from environment
variables (via .env in local/dev, or real env vars in production).
"""
from datetime import date, timedelta
from typing import List, Tuple

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram (free, no trial expiry)
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    # Anthropic (OPTIONAL -- leave unset to run 100% free with template messages)
    ANTHROPIC_API_KEY: str = ""

    # App
    DB_PATH: str = "flights.db"
    PRICE_DROP_THRESHOLD_INR: int = 1000
    TRACK_START_DATE: date = date(2027, 1, 10)
    TRACK_END_DATE: date = date(2027, 2, 20)
    ROUTES: str = "BOM:SYD,DEL:SYD,BLR:SYD"
    CURRENCY: str = "INR"
    REQUEST_DELAY_SECONDS: float = 3.0
    MAX_RETRIES: int = 3

    DAILY_JOB_HOUR: int = 6
    DAILY_JOB_MINUTE: int = 0
    WEEKLY_JOB_HOUR: int = 8
    WEEKLY_JOB_MINUTE: int = 0

    @field_validator("TRACK_END_DATE")
    @classmethod
    def end_after_start(cls, v: date, info):
        start = info.data.get("TRACK_START_DATE")
        if start and v < start:
            raise ValueError("TRACK_END_DATE must be on or after TRACK_START_DATE")
        return v

    def route_pairs(self) -> List[Tuple[str, str]]:
        """Parse 'BOM:SYD,DEL:SYD' -> [('BOM','SYD'), ('DEL','SYD')]"""
        pairs = []
        for chunk in self.ROUTES.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            origin, dest = chunk.split(":")
            pairs.append((origin.strip().upper(), dest.strip().upper()))
        return pairs

    def date_range(self) -> List[date]:
        """All dates from TRACK_START_DATE to TRACK_END_DATE inclusive."""
        days = (self.TRACK_END_DATE - self.TRACK_START_DATE).days
        return [self.TRACK_START_DATE + timedelta(days=i) for i in range(days + 1)]


settings = Settings()
