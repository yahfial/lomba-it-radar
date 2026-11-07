# D:\alfa\Documents\Antigravity\lomba-it-radar\src\engine.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.collectors import MultiSourceRadarCollector
from src.config import RadarConfig
from src.models import ScanSummary
from src.notifier import TelegramNotifier
from src.storage import RadarStorage

logger = logging.getLogger("lomba_radar.engine")


class RadarEngine:
    """Orchestrates collection, deduplication, persistence, and real-time Telegram alerts."""

    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self.storage = RadarStorage(config.db_path)
        self.collector = MultiSourceRadarCollector(config)
        self.notifier = TelegramNotifier(config)

    async def run_single_scan(self, max_notify_per_cycle: int = 15) -> ScanSummary:
        """Execute one full scan cycle across all Indonesian sources."""
        started_at = datetime.now(timezone.utc)
        logger.info("Memulai pemindaian Radar Lomba IT Nasional...")

        candidates, errors = await self.collector.collect_all()
        new_items_count = 0
        notified_count = 0

        for item in candidates:
            if self.storage.is_seen(item):
                continue

            new_items_count += 1
            # Save first to prevent duplicate sends on crash
            self.storage.save_item(item, notified=False)

            logger.info(
                "🔥 [BARU] [%s] %s (%s) -> %s",
                ", ".join(c.value for c in item.categories),
                item.title,
                item.source_name,
                item.url,
            )

            if self.config.is_telegram_configured and notified_count < max_notify_per_cycle:
                delivered = await self.notifier.send_item(item)
                if delivered:
                    self.storage.mark_notified(item.fingerprint)
                    notified_count += 1
                    await asyncio.sleep(1.2)  # Prevent Telegram flood limits

        finished_at = datetime.now(timezone.utc)
        summary = ScanSummary(
            started_at=started_at,
            finished_at=finished_at,
            total_fetched=len(candidates),
            passed_filter=len(candidates),
            new_items_count=new_items_count,
            notified_count=notified_count,
            errors=errors,
        )
        logger.info(
            "Siklus selesai dalam %.1f detik | Kandidat valid: %d | Lomba Baru: %d | Terkirim ke Telegram: %d | Total DB: %d",
            (finished_at - started_at).total_seconds(),
            summary.passed_filter,
            summary.new_items_count,
            summary.notified_count,
            self.storage.count_total(),
        )
        return summary

    async def run_daemon_forever(self) -> None:
        """Run 24/7 continuous monitoring loop with configurable interval."""
        interval_sec = max(60, self.config.scan_interval_minutes * 60)
        logger.info(
            "Mode 24/7 Real-time Daemon aktif. Interval pemindaian: setiap %d menit.",
            self.config.scan_interval_minutes,
        )
        while True:
            try:
                await self.run_single_scan()
            except Exception as exc:
                logger.exception("Terjadi kesalahan pada siklus pemindaian: %s", exc)

            logger.info(
                "Menunggu %d menit sebelum pemindaian kata kunci berikutnya...",
                self.config.scan_interval_minutes,
            )
            await asyncio.sleep(interval_sec)
