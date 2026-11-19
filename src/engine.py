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
        self._scan_lock = asyncio.Lock()

    async def run_single_scan(
        self, max_notify_per_cycle: int = 15, process_commands: bool = True
    ) -> ScanSummary:
        """Execute one full scan cycle across all Indonesian sources."""
        async with self._scan_lock:
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

            # Process any incoming Telegram commands when running in --once / GitHub Actions mode
            if process_commands and self.config.is_telegram_configured:
                await self.notifier.process_pending_commands(self.storage, poll_timeout=1)

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

    async def _telegram_command_loop(self) -> None:
        """Continuously long-poll Telegram for instant /cek, /status, /terbaru, and /scan replies."""
        if not self.config.is_telegram_configured:
            return
        await self.notifier.register_bot_commands()
        logger.info("Telegram real-time command listener aktif (long-polling 24/7).")

        async def _manual_scan() -> tuple[int, int]:
            res = await self.run_single_scan(process_commands=False)
            return res.passed_filter, res.new_items_count

        while True:
            try:
                await self.notifier.process_pending_commands(
                    self.storage,
                    poll_timeout=20,
                    on_scan_request=_manual_scan,
                )
            except Exception as exc:
                logger.warning("Error pada Telegram command listener: %s", exc)
                await asyncio.sleep(3.0)
            await asyncio.sleep(0.5)

    async def _scanner_loop(self) -> None:
        """Periodically scan all competition sources."""
        interval_sec = max(60, self.config.scan_interval_minutes * 60)
        while True:
            try:
                await self.run_single_scan(process_commands=False)
            except Exception as exc:
                logger.exception("Terjadi kesalahan pada siklus pemindaian: %s", exc)

            logger.info(
                "Menunggu %d menit sebelum pemindaian kata kunci berikutnya...",
                self.config.scan_interval_minutes,
            )
            await asyncio.sleep(interval_sec)

    async def run_daemon_forever(self) -> None:
        """Run 24/7 continuous radar scanner + instant Telegram command listener concurrently."""
        logger.info(
            "Mode 24/7 Real-time Daemon aktif. Interval pemindaian: setiap %d menit.",
            self.config.scan_interval_minutes,
        )
        await asyncio.gather(
            self._scanner_loop(),
            self._telegram_command_loop(),
        )
