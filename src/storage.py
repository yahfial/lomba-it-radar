# D:\alfa\Documents\Antigravity\lomba-it-radar\src\storage.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.classifier import is_deadline_valid_and_open, parse_deadline_date
from src.models import (
    CompetitionCategory,
    CompetitionItem,
    are_same_competition,
    extract_event_key,
)


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
                    event_key TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    relevance_score INTEGER NOT NULL DEFAULT 0,
                    registration_deadline TEXT,
                    published_at TEXT,
                    discovered_at TEXT NOT NULL,
                    notified INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            for alter_sql in (
                "ALTER TABLE seen_competitions ADD COLUMN registration_deadline TEXT;",
                "ALTER TABLE seen_competitions ADD COLUMN event_key TEXT NOT NULL DEFAULT '';",
            ):
                try:
                    conn.execute(alter_sql)
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_title_fingerprint
                ON seen_competitions (title_fingerprint);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_event_key
                ON seen_competitions (event_key);
                """
            )
            conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM bot_meta WHERE key = ?;", (key,)
            ).fetchone()
            return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO bot_meta (key, value) VALUES (?, ?);",
                (key, value),
            )
            conn.commit()

    def is_seen(self, item: CompetitionItem) -> bool:
        """
        Check whether this competition event has ALREADY been reported, using:
        1. Exact URL+title fingerprint or title_fingerprint
        2. Canonical flagship event_key (e.g. 'event::gemastik::2026')
        3. Semantic/fuzzy event similarity against previously stored titles
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT 1 FROM seen_competitions
                WHERE fingerprint = ? OR title_fingerprint = ?
                LIMIT 1;
                """,
                (item.fingerprint, item.title_fingerprint),
            )
            if cursor.fetchone() is not None:
                return True

            if item.event_key:
                ev_cur = conn.execute(
                    """
                    SELECT 1 FROM seen_competitions
                    WHERE event_key = ?
                    LIMIT 1;
                    """,
                    (item.event_key,),
                )
                if ev_cur.fetchone() is not None:
                    return True

            rows = conn.execute(
                """
                SELECT title, event_key FROM seen_competitions
                ORDER BY discovered_at DESC
                LIMIT 500;
                """
            ).fetchall()

        for row in rows:
            existing_title = str(row["title"])
            existing_key = str(row["event_key"] or "") or extract_event_key(existing_title)
            if are_same_competition(
                item.title, existing_title, item.event_key, existing_key
            ):
                return True

        return False

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
                    event_key,
                    title,
                    url,
                    source_name,
                    categories_json,
                    relevance_score,
                    registration_deadline,
                    published_at,
                    discovered_at,
                    notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    item.fingerprint,
                    item.title_fingerprint,
                    item.event_key,
                    item.title,
                    item.url,
                    item.source_name,
                    json.dumps(categories_list, ensure_ascii=False),
                    item.relevance_score,
                    item.registration_deadline,
                    published_iso,
                    discovered_iso,
                    1 if notified else 0,
                ),
            )
            conn.commit()

    def deduplicate_existing_records(self) -> int:
        """
        Remove semantic duplicates already present in seen_competitions, keeping the
        single best entry (with deadline & highest score) per distinct competition event.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fingerprint, title, event_key, relevance_score,
                       registration_deadline, discovered_at
                FROM seen_competitions
                ORDER BY
                    CASE WHEN registration_deadline IS NOT NULL AND registration_deadline != '' THEN 1 ELSE 0 END DESC,
                    relevance_score DESC,
                    discovered_at ASC;
                """
            ).fetchall()

            kept: list[tuple[str, str]] = []
            to_delete: list[str] = []

            for row in rows:
                fp = str(row["fingerprint"])
                title = str(row["title"])
                ev_key = str(row["event_key"] or "") or extract_event_key(title)

                # Backfill canonical event_key if missing
                if ev_key and not row["event_key"]:
                    conn.execute(
                        "UPDATE seen_competitions SET event_key = ? WHERE fingerprint = ?;",
                        (ev_key, fp),
                    )

                if any(
                    are_same_competition(title, k_title, ev_key, k_key)
                    for k_title, k_key in kept
                ):
                    to_delete.append(fp)
                else:
                    kept.append((title, ev_key))

            for fp in to_delete:
                conn.execute("DELETE FROM seen_competitions WHERE fingerprint = ?;", (fp,))

            conn.commit()
            return len(to_delete)

    def merge_from_sqlite(self, other_db_path: Path) -> int:
        """Merge competition rows from another SQLite snapshot (e.g., origin/main) without duplicates."""
        if not other_db_path.exists():
            return 0
        merged = 0
        src_conn = sqlite3.connect(str(other_db_path), timeout=10.0)
        src_conn.row_factory = sqlite3.Row
        try:
            cols = {
                r["name"]
                for r in src_conn.execute("PRAGMA table_info(seen_competitions);").fetchall()
            }
            select_deadline = "registration_deadline" if "registration_deadline" in cols else "NULL AS registration_deadline"
            select_evkey = "event_key" if "event_key" in cols else "'' AS event_key"
            src_rows = src_conn.execute(
                f"""
                SELECT fingerprint, title_fingerprint, {select_evkey}, title, url,
                       source_name, categories_json, relevance_score,
                       {select_deadline}, published_at, discovered_at, notified
                FROM seen_competitions;
                """
            ).fetchall()
        except sqlite3.Error:
            return 0
        finally:
            src_conn.close()

        with self._connect() as dst_conn:
            existing_rows = dst_conn.execute(
                "SELECT fingerprint, title, event_key FROM seen_competitions;"
            ).fetchall()
            existing_fps = {str(r["fingerprint"]) for r in existing_rows}
            existing_events = [
                (str(r["title"]), str(r["event_key"] or "") or extract_event_key(str(r["title"])))
                for r in existing_rows
            ]

            for r in src_rows:
                if not is_deadline_valid_and_open(r["registration_deadline"]):
                    continue
                fp = str(r["fingerprint"])
                title = str(r["title"])
                ev_key = str(r["event_key"] or "") or extract_event_key(title)
                if fp in existing_fps:
                    continue
                if any(
                    are_same_competition(title, e_title, ev_key, e_key)
                    for e_title, e_key in existing_events
                ):
                    continue
                dst_conn.execute(
                    """
                    INSERT OR IGNORE INTO seen_competitions (
                        fingerprint, title_fingerprint, event_key, title, url,
                        source_name, categories_json, relevance_score,
                        registration_deadline, published_at, discovered_at, notified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        fp,
                        str(r["title_fingerprint"]),
                        ev_key,
                        title,
                        str(r["url"]),
                        str(r["source_name"]),
                        str(r["categories_json"]),
                        int(r["relevance_score"]),
                        r["registration_deadline"],
                        r["published_at"],
                        str(r["discovered_at"]),
                        int(r["notified"]),
                    ),
                )
                existing_fps.add(fp)
                existing_events.append((title, ev_key))
                merged += 1
            dst_conn.commit()
        return merged

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
                       registration_deadline, published_at, discovered_at
                FROM seen_competitions
                ORDER BY discovered_at DESC, relevance_score DESC
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
                    registration_deadline=row["registration_deadline"],
                    relevance_score=int(row["relevance_score"]),
                    published_at=pub_dt,
                    discovered_at=disc_dt,
                )
            )
        return items

    def get_active_items(self, limit: int = 10) -> list[CompetitionItem]:
        """Return ONLY competitions with a verified, non-expired registration deadline (>= today WIB), sorted by closest deadline."""
        all_recent = self.get_recent_items(limit=200)
        active = [
            it
            for it in all_recent
            if is_deadline_valid_and_open(it.registration_deadline)
        ]
        active.sort(
            key=lambda it: parse_deadline_date(it.registration_deadline) or datetime.max.date()
        )
        return active[:limit]

    def prune_expired_or_undated(self) -> int:
        """Delete legacy rows that have no verified registration deadline or whose deadline already passed."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fingerprint, registration_deadline FROM seen_competitions;"
            ).fetchall()
            removed = 0
            for row in rows:
                dl = row["registration_deadline"]
                if not is_deadline_valid_and_open(dl):
                    conn.execute(
                        "DELETE FROM seen_competitions WHERE fingerprint = ?;",
                        (row["fingerprint"],),
                    )
                    removed += 1
            conn.commit()
            return removed
