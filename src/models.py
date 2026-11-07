# D:\alfa\Documents\Antigravity\lomba-it-radar\src\models.py
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CompetitionCategory(str, Enum):
    HACKATHON = "Hackathon & Software Dev"
    CYBERSECURITY = "Cyber Security & CTF"
    DATA_AI = "Data Science & AI/ML"
    UI_UX = "UI/UX & Product Design"
    COMPETITIVE_PROG = "Competitive Programming"
    GENERAL_IT = "Lomba IT & Inovasi Nasional"


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(raw_url: str) -> str:
    """Normalize URL by stripping tracking parameters and fragments."""
    cleaned = raw_url.strip()
    if not cleaned:
        return ""
    try:
        parsed = urlparse(cleaned)
        filtered_query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        normalized = urlunparse(
            (
                parsed.scheme.lower() or "https",
                parsed.netloc.lower(),
                parsed.path.rstrip("/") or "/",
                parsed.params,
                urlencode(filtered_query, doseq=True),
                "",
            )
        )
        return normalized
    except Exception:
        return cleaned


def normalize_title_slug(title: str) -> str:
    """Normalize title into an alphanumeric lowercase slug for fuzzy deduplication."""
    lowered = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    tokens = [t for t in lowered.split() if len(t) > 2]
    return " ".join(tokens[:12])


class CompetitionItem(BaseModel):
    """Strict data contract representing a discovered Indonesian IT competition."""

    model_config = ConfigDict(frozen=False, extra="ignore")

    title: str = Field(..., min_length=5, description="Judul lomba atau event IT")
    url: str = Field(..., min_length=8, description="URL sumber pengumuman lomba")
    source_name: str = Field(..., description="Nama sumber (Google News, Dicoding, Telegram, dll)")
    categories: list[CompetitionCategory] = Field(
        default_factory=lambda: [CompetitionCategory.GENERAL_IT]
    )
    organizer: str = Field(default="Penyelenggara Nasional", description="Instansi penyelenggara")
    snippet: str = Field(default="", description="Ringkasan atau deskripsi singkat lomba")
    published_at: Optional[datetime] = Field(
        default=None, description="Waktu publikasi artikel/pengumuman"
    )
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Waktu bot menemukan item ini",
    )
    relevance_score: int = Field(default=0, description="Skor relevansi lomba IT Indonesia")
    matched_keywords: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint combining canonical URL and title slug."""
        canon_url = canonicalize_url(self.url)
        slug = normalize_title_slug(self.title)
        payload = f"{canon_url}||{slug}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title_fingerprint(self) -> str:
        """Secondary hash based purely on normalized title to block cross-site duplicates."""
        slug = normalize_title_slug(self.title)
        return hashlib.sha256(slug.encode("utf-8")).hexdigest()


class ScanSummary(BaseModel):
    """Structured report of a radar scan cycle."""

    started_at: datetime
    finished_at: datetime
    total_fetched: int = 0
    passed_filter: int = 0
    new_items_count: int = 0
    notified_count: int = 0
    errors: list[str] = Field(default_factory=list)
