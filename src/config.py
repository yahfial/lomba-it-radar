# D:\alfa\Documents\Antigravity\lomba-it-radar\src\config.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class RadarConfig(BaseModel):
    """Application configuration loaded from environment variables."""

    telegram_bot_token: str = Field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    telegram_chat_id: str = Field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip()
    )
    scan_interval_minutes: int = Field(
        default_factory=lambda: int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    )
    max_age_days: int = Field(
        default_factory=lambda: int(os.getenv("MAX_AGE_DAYS", "30"))
    )
    db_path: Path = Field(
        default_factory=lambda: Path(os.getenv("DB_PATH", "data/radar_history.db"))
    )
    request_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12.0"))
    )
    max_requests_per_second: float = Field(
        default_factory=lambda: float(os.getenv("MAX_REQUESTS_PER_SECOND", "3.0"))
    )
    http_proxy: Optional[str] = Field(
        default_factory=lambda: os.getenv("HTTP_PROXY", "").strip() or None
    )

    # Google News RSS Search Queries (Real-time Indonesian Web Indexing)
    google_news_queries: list[str] = Field(
        default_factory=lambda: [
            '"hackathon" indonesia pendaftaran OR lomba',
            '"lomba IT" OR "kompetisi IT" mahasiswa indonesia',
            '"capture the flag" OR "lomba cyber security" indonesia',
            '"lomba UI/UX" OR "UI/UX design competition" mahasiswa indonesia',
            '"lomba data science" OR "datathon" OR "kompetisi AI" indonesia',
            '"competitive programming" OR "lomba coding" OR "lomba pemrograman" indonesia',
            'gemastik OR compfest OR arkavidia OR "schematics its" OR "find it ugm" OR "hology ub"',
        ]
    )

    # Bing News RSS Queries (Secondary Real-time Search Index)
    bing_news_queries: list[str] = Field(
        default_factory=lambda: [
            "hackathon mahasiswa indonesia pendaftaran",
            "lomba teknologi informasi nasional mahasiswa",
            "kompetisi cyber security CTF indonesia",
            "lomba UI UX design mahasiswa nasional",
        ]
    )

    # Public Telegram Broadcast Channels (Web Preview Scraper `https://t.me/s/<channel>`)
    telegram_public_channels: list[str] = Field(
        default_factory=lambda: [
            "kabarlomba",
        ]
    )

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)
