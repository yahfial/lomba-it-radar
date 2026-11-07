# D:\alfa\Documents\Antigravity\lomba-it-radar\src\notifier.py
from __future__ import annotations

import asyncio
import html
import logging
from datetime import timezone, timedelta

import httpx

from src.config import RadarConfig
from src.models import CompetitionItem

logger = logging.getLogger("lomba_radar.notifier")

WIB_TZ = timezone(timedelta(hours=7))


def format_telegram_message(item: CompetitionItem) -> str:
    """Format a CompetitionItem into a clean HTML Telegram notification message."""
    safe_title = html.escape(item.title)
    safe_source = html.escape(item.source_name)
    safe_organizer = html.escape(item.organizer)
    safe_cats = ", ".join(html.escape(c.value) for c in item.categories)
    safe_kws = ", ".join(f"#{html.escape(k.replace(' ', '_'))}" for k in item.matched_keywords[:6])

    if item.published_at:
        wib_time = item.published_at.astimezone(WIB_TZ).strftime("%d %b %Y %H:%M WIB")
    else:
        wib_time = item.discovered_at.astimezone(WIB_TZ).strftime("%d %b %Y %H:%M WIB")

    snippet_block = ""
    if item.snippet and item.snippet.lower() != item.title.lower():
        clean_snip = html.escape(item.snippet[:220])
        snippet_block = f"\n📝 <b>Ringkasan:</b>\n<i>{clean_snip}</i>\n"

    safe_url = html.escape(item.url, quote=True)

    return (
        f"🚨 <b>[RADAR LOMBA IT NASIONAL BARU]</b>\n\n"
        f"🏆 <b>{safe_title}</b>\n"
        f"🏷️ <b>Kategori:</b> {safe_cats}\n"
        f"🏛️ <b>Sumber / Instansi:</b> {safe_organizer} ({safe_source})\n"
        f"🕒 <b>Terdeteksi:</b> {wib_time}"
        f"{snippet_block}\n"
        f"🔗 <a href=\"{safe_url}\">Buka Link Informasi & Pendaftaran</a>\n\n"
        f"🔎 {safe_kws}"
    )


class TelegramNotifier:
    """Delivers real-time alerts to a Telegram chat or channel via Telegram Bot API."""

    def __init__(self, config: RadarConfig) -> None:
        self.config = config

    async def send_item(self, item: CompetitionItem) -> bool:
        """Send a single competition alert to Telegram. Returns True if delivered."""
        if not self.config.is_telegram_configured:
            logger.info(
                "[CONSOLE-ONLY MODE] Telegram belum dikonfigurasi. Lomba ditemukan: %s -> %s",
                item.title,
                item.url,
            )
            return False

        api_url = (
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": format_telegram_message(item),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        client_kwargs: dict[str, object] = {
            "timeout": httpx.Timeout(self.config.request_timeout_seconds)
        }
        if self.config.http_proxy:
            client_kwargs["proxy"] = self.config.http_proxy

        async with httpx.AsyncClient(**client_kwargs) as client:  # type: ignore[arg-type]
            for attempt in range(1, 4):
                try:
                    resp = await client.post(api_url, json=payload)
                    if resp.status_code == 429:
                        retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                        logger.warning("Telegram rate limit 429. Menunggu %d detik...", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    return True
                except Exception as exc:
                    logger.error(
                        "Gagal mengirim notifikasi Telegram (percobaan %d/3): %s",
                        attempt,
                        exc,
                    )
                    await asyncio.sleep(2.0 * attempt)

        return False

    async def send_test_ping(self) -> bool:
        """Send a test connection message to verify Bot Token and Chat ID."""
        if not self.config.is_telegram_configured:
            logger.error(
                "TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID kosong di file .env!"
            )
            return False

        api_url = (
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": (
                "✅ <b>Lomba IT Radar Indonesia Aktif!</b>\n\n"
                "Bot berhasil terhubung dan siap memantau seluruh kata kunci "
                "Lomba IT, Hackathon, CTF, Data Science, CP, dan UI/UX tingkat nasional secara 24 jam."
            ),
            "parse_mode": "HTML",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(api_url, json=payload)
                resp.raise_for_status()
                return True
            except Exception as exc:
                logger.error("Koneksi Telegram gagal: %s", exc)
                return False
