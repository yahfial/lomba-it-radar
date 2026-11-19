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
        default_factory=lambda: int(os.getenv("MAX_AGE_DAYS", "14"))
    )
    min_days_before_deadline: int = Field(
        default_factory=lambda: int(os.getenv("MIN_DAYS_BEFORE_DEADLINE", "20"))
    )
    include_international: bool = Field(
        default_factory=lambda: os.getenv("INCLUDE_INTERNATIONAL", "true").strip().lower()
        in {"1", "true", "yes", "on"}
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

    # Google News RSS Search Queries (Clean syntax without nested parentheses so Google RSS returns full results)
    google_news_queries: list[str] = Field(
        default_factory=lambda: [
            "hackathon indonesia",
            "lomba IT OR kompetisi IT mahasiswa indonesia",
            "lomba cyber security OR capture the flag indonesia",
            "lomba UI UX OR desain aplikasi mahasiswa indonesia",
            "lomba data science OR datathon OR kompetisi AI indonesia",
            "lomba coding OR competitive programming mahasiswa indonesia",
            "gemastik OR compfest OR arkavidia OR schematics OR find it ugm OR hology",
            "lomba inovasi digital OR lomba aplikasi mahasiswa",
        ]
    )

    # Bing News RSS Queries (Concise keywords so Bing RSS doesn't drop headlines)
    bing_news_queries: list[str] = Field(
        default_factory=lambda: [
            "hackathon indonesia",
            "lomba IT mahasiswa",
            "kompetisi cyber security indonesia",
            "lomba UI UX mahasiswa",
            "kompetisi AI data science indonesia",
            "lomba inovasi teknologi mahasiswa",
        ]
    )

    # Direct RSS Feeds with full-text descriptions & deadlines
    direct_rss_feeds: list[tuple[str, str]] = Field(
        default_factory=lambda: [
            ("https://www.kabarlomba.com/feeds/posts/default?alt=rss", "KabarLomba Official RSS"),
            ("https://www.kabarlomba.com/feeds/posts/default?alt=rss&q=teknologi", "KabarLomba Tech RSS"),
            ("https://www.kabarlomba.com/feeds/posts/default?alt=rss&q=aplikasi", "KabarLomba App RSS"),
            ("https://www.kabarlomba.com/feeds/posts/default?alt=rss&q=website", "KabarLomba Web RSS"),
            ("https://www.dicoding.com/blog/feed/", "Dicoding Indonesia Blog RSS"),
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
