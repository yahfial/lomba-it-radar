# D:\alfa\Documents\Antigravity\lomba-it-radar\src\storage.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.models import CompetitionCategory, CompetitionItem


class RadarStorage:
    """SQLite persistence layer for deduplicating discovered IT competitions."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_competitions (
                    fingerprint TEXT PRIMARY KEY,
                    title_fingerprint TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    relevance_score INTEGER NOT NULL DEFAULT 0,
                    published_at TEXT,
                    discovered_at TEXT NOT NULL,
                    notified INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_title_fingerprint
                ON seen_competitions (title_fingerprint);
                """
            )
            conn.commit()

    def is_seen(self, item: CompetitionItem) -> bool:
        """Check if competition has already been recorded by URL+title or identical normalized title."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT 1 FROM seen_competitions
                WHERE fingerprint = ? OR title_fingerprint = ?
                LIMIT 1;
                """,
                (item.fingerprint, item.title_fingerprint),
            )
            return cursor.fetchone() is not None

    def save_item(self, item: CompetitionItem, notified: bool = False) -> None:
        """Persist a competition item into SQLite."""
        categories_list = [c.value for c in item.categories]
        published_iso: Optional[str] = (
            item.published_at.isoformat() if item.published_at else None
        )
        discovered_iso = item.discovered_at.isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO seen_competitions (
                    fingerprint,
                    title_fingerprint,
                    title,
                    url,
                    source_name,
                    categories_json,
                    relevance_score,
                    published_at,
                    discovered_at,
                    notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    item.fingerprint,
                    item.title_fingerprint,
                    item.title,
                    item.url,
                    item.source_name,
                    json.dumps(categories_list, ensure_ascii=False),
                    item.relevance_score,
                    published_iso,
                    discovered_iso,
                    1 if notified else 0,
                ),
            )
            conn.commit()

    def mark_notified(self, fingerprint: str) -> None:
        """Mark a stored item as notified via Telegram."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE seen_competitions SET notified = 1 WHERE fingerprint = ?;",
                (fingerprint,),
            )
            conn.commit()

    def count_total(self) -> int:
        """Return total number of tracked competitions in history."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM seen_competitions;").fetchone()
            return int(row["cnt"]) if row else 0

    def get_recent_items(self, limit: int = 20) -> list[CompetitionItem]:
        """Retrieve most recently discovered items from SQLite."""
        items: list[CompetitionItem] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT title, url, source_name, categories_json, relevance_score,
                       published_at, discovered_at
                FROM seen_competitions
                ORDER BY relevance_score DESC, discovered_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        for row in rows:
            raw_cats = json.loads(row["categories_json"])
            cats = [
                CompetitionCategory(c)
                for c in raw_cats
                if c in {member.value for member in CompetitionCategory}
            ]
            pub_dt = (
                datetime.fromisoformat(row["published_at"])
                if row["published_at"]
                else None
            )
            disc_dt = (
                datetime.fromisoformat(row["discovered_at"])
                if row["discovered_at"]
                else datetime.now(timezone.utc)
            )
            items.append(
                CompetitionItem(
                    title=row["title"],
                    url=row["url"],
                    source_name=row["source_name"],
                    categories=cats or [CompetitionCategory.GENERAL_IT],
                    relevance_score=int(row["relevance_score"]),
                    published_at=pub_dt,
                    discovered_at=disc_dt,
                )
            )
        return items
