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


FLAGSHIP_EVENT_PATTERNS: list[tuple[str, str]] = [
    ("gemastik", r"\bgemastik\b"),
    ("compfest", r"\bcompfest\b"),
    ("arkavidia", r"\barkavidia\b"),
    ("schematics", r"\bschematics\b"),
    ("find_it_ugm", r"\bfind\s*it\s+ugm\b"),
    ("joints_ugm", r"\bjoints\s+ugm\b"),
    ("mage_its", r"\bmage\s+its\b"),
    ("hology_ub", r"\bhology\b"),
    ("it_today_ipb", r"\bit\s+today\b"),
    ("satria_data", r"\bsatria\s+data\b"),
    ("cyber_jawara", r"\bcyber\s+jawara\b"),
    ("technofest", r"\btechnofest\b"),
    ("techphoria", r"\btechphoria\b"),
    ("ifest", r"\bifest\b"),
    ("maju_hackathon", r"\bmaju[\s:\-]*on\b|\bmaju\s+university\s+hackathon\b"),
]

NEWS_STOPWORDS: set[str] = {
    "pendaftaran", "registrasi", "resmi", "dibuka", "buka", "membuka", "peserta",
    "ditantang", "tantang", "menantang", "ciptakan", "menciptakan", "hadirkan",
    "menghadirkan", "solusi", "gaet", "menggaet", "inovator", "lintas", "ilmu",
    "berhadiah", "ratusan", "juta", "jutaan", "rupiah", "hadiah", "gratis", "untuk",
    "mahasiswa", "pelajar", "siswa", "umum", "nasional", "indonesia", "tingkat",
    "digelar", "gelar", "menggelar", "incar", "mengincar", "talenta", "cabang",
    "perlombakan", "memperlombakan", "halaman", "all", "yang", "dan", "dengan",
    "dalam", "dari", "pada", "bagi", "para", "akan", "telah", "tahun", "lomba",
    "kompetisi", "competition", "event", "ajang", "kegiatan", "oleh", "di", "ke",
    "segera", "daftar", "ikuti", "mengikuti", "open", "registration", "early",
    "bird", "terbuka", "total", "hadir", "dorong", "mendorong", "wujudkan", "ini",
    "jadi", "tuan", "rumah", "dukung", "mendukung", "lahirnya", "lewat", "melalui",
    "kembali", "hadir", "siapkan", "ajak", "mengajak", "bersama", "hingga", "sampai",
    "batas", "deadline", "info", "berita", "update", "baru", "terbaru", "prizes",
    "prize", "pool", "for", "the", "and", "with", "of", "in", "to", "at", "by",
}

GENERIC_IT_EVENT_WORDS: set[str] = {
    "hackathon", "datathon", "ctf", "cyber", "security", "keamanan", "siber",
    "ketahanan", "data", "science", "machine", "learning", "deep", "ai",
    "artificial", "intelligence", "kecerdasan", "buatan", "ui", "ux", "design",
    "desain", "web", "website", "mobile", "app", "aplikasi", "software",
    "development", "coding", "koding", "code", "pemrograman", "competitive",
    "programming", "it", "tik", "teknologi", "informasi", "digital", "informatika",
    "inovasi", "innovation", "startup", "tech", "iot", "game", "sistem",
    "fintech", "healthtech", "edutech", "agritech", "deeptech", "foodtech",
    "greentech", "blockchain", "web3", "cloud", "energi", "kesehatan", "pendidikan",
    "smart", "city", "league", "cup", "fest", "festival", "challenge", "award",
    "awards", "olympiad", "olimpiade", "contest", "championship", "summit",
    "series", "season", "bootcamp", "academy", "national", "internasional",
    "international", "campus", "kampus", "university", "universitas", "tim",
}

YEAR_RE = re.compile(r"\b(202[5-9]|203\d)\b")
ROMAN_EDITION_RE = re.compile(r"\b(?:x{0,3}(?:ix|iv|v?i{1,3}))\b", re.IGNORECASE)


def strip_publisher_suffix(title: str) -> str:
    """Strip news outlet suffix like ' - PWM Jateng', ' - Kompasiana.com', or ' | Detik'."""
    cleaned = re.sub(r"\s+Halaman\s+all\b.*$", "", title, flags=re.IGNORECASE)
    cleaned = re.split(r"\s+[-–—|]\s+(?=[^-–—|]+$)", cleaned, maxsplit=1)[0]
    return cleaned.strip()


def split_camel_case(text: str) -> str:
    """Split acronym-prefixed joined words like 'UMSHealth' -> 'UMS Health' without breaking 'FinTech'."""
    return re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", text)


def extract_event_key(title: str) -> str:
    """Extract canonical event key for known recurring national IT competitions."""
    base = strip_publisher_suffix(title)
    years = YEAR_RE.findall(base)
    year_tag = years[0] if years else str(datetime.now(timezone.utc).year)
    for canonical_name, pattern in FLAGSHIP_EVENT_PATTERNS:
        if re.search(pattern, base, flags=re.IGNORECASE):
            return f"event::{canonical_name}::{year_tag}"
    return ""


def extract_event_tokens(title: str) -> tuple[set[str], set[str], set[str]]:
    """
    Extract (core_tokens, distinctive_tokens, year_tokens) from a competition headline
    for event-level semantic deduplication across different news sources.
    """
    base = split_camel_case(strip_publisher_suffix(title))
    years = set(YEAR_RE.findall(base))
    lowered = re.sub(r"[^a-z0-9]+", " ", base.lower()).strip()

    core_tokens: set[str] = set()
    for tok in lowered.split():
        if len(tok) < 2:
            continue
        if tok.isdigit() and tok not in years:
            continue
        if tok in NEWS_STOPWORDS:
            continue
        if ROMAN_EDITION_RE.fullmatch(tok):
            continue
        core_tokens.add(tok)

    distinctive_tokens = {
        tok
        for tok in core_tokens
        if tok not in GENERIC_IT_EVENT_WORDS and tok not in years
    }
    return core_tokens, distinctive_tokens, years


def are_same_competition(
    title_a: str,
    title_b: str,
    event_key_a: str = "",
    event_key_b: str = "",
) -> bool:
    """
    Determine whether two headlines refer to the exact same IT competition event,
    even if published by different media outlets with reworded titles.
    """
    key_a = event_key_a or extract_event_key(title_a)
    key_b = event_key_b or extract_event_key(title_b)
    if key_a and key_b and key_a == key_b:
        return True

    if normalize_title_slug(title_a) == normalize_title_slug(title_b):
        return True

    core_a, dist_a, years_a = extract_event_tokens(title_a)
    core_b, dist_b, years_b = extract_event_tokens(title_b)

    # Different explicit years mean different annual editions (e.g. 2026 vs 2027)
    if years_a and years_b and years_a.isdisjoint(years_b):
        return False

    if not core_a or not core_b:
        return False

    shared_dist = dist_a & dist_b
    shared_core = core_a & core_b

    # Must share at least 1 distinctive (brand/organizer/unique name) token
    if not shared_dist:
        return False

    min_dist = min(len(dist_a), len(dist_b))
    dist_overlap = len(shared_dist) / min_dist if min_dist > 0 else 0.0
    core_union = core_a | core_b
    core_jaccard = len(shared_core) / len(core_union) if core_union else 0.0
    min_core = min(len(core_a), len(core_b))
    core_overlap = len(shared_core) / min_core if min_core > 0 else 0.0

    # Rule 1: Share >= 2 distinctive brand/event tokens with high overlap (e.g. "ums", "health")
    if len(shared_dist) >= 2 and dist_overlap >= 0.65:
        return True

    # Rule 2: Strong overall Jaccard similarity with high distinctive token overlap
    if core_jaccard >= 0.60 and dist_overlap >= 0.60 and len(shared_core) >= 3:
        return True

    # Rule 3: One headline is a more concise subset of the other with high distinctive overlap
    if len(shared_dist) >= 1 and dist_overlap >= 0.80 and core_overlap >= 0.75 and len(shared_core) >= 3:
        return True

    return False


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
    registration_deadline: Optional[str] = Field(
        default=None, description="Batas akhir pendaftaran lomba yang terdeteksi"
    )
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def event_key(self) -> str:
        """Canonical competition event identifier (e.g. 'event::gemastik::2026')."""
        return extract_event_key(self.title)


class ScanSummary(BaseModel):
    """Structured report of a radar scan cycle."""

    started_at: datetime
    finished_at: datetime
    total_fetched: int = 0
    passed_filter: int = 0
    new_items_count: int = 0
    notified_count: int = 0
    errors: list[str] = Field(default_factory=list)
