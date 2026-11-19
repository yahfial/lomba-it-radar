# D:\alfa\Documents\Antigravity\lomba-it-radar\src\notifier.py
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

import httpx

from src.config import RadarConfig
from src.models import CompetitionItem

if TYPE_CHECKING:
    from src.storage import RadarStorage

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

    if item.registration_deadline:
        deadline_str = html.escape(item.registration_deadline)
    else:
        deadline_str = "Cek detail tanggal pada link pendaftaran"

    safe_url = html.escape(item.url, quote=True)

    return (
        f"🚨 <b>[LOMBA IT NASIONAL — BUKA PENDAFTARAN]</b>\n\n"
        f"🏆 <b>{safe_title}</b>\n"
        f"🏷️ <b>Kategori:</b> {safe_cats}\n"
        f"⏳ <b>Batas Pendaftaran:</b> {deadline_str}\n"
        f"🏛️ <b>Sumber / Instansi:</b> {safe_organizer} ({safe_source})\n"
        f"🕒 <b>Terdeteksi:</b> {wib_time}"
        f"{snippet_block}\n"
        f"🔗 <a href=\"{safe_url}\">Daftar / Buka Info Resmi</a>\n\n"
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
            "timeout": httpx.Timeout(self.config.request_timeout_seconds),
            "verify": False,
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

    async def send_raw_html(self, html_text: str, chat_id: str = "") -> bool:
        """Send an arbitrary HTML message to Telegram."""
        if not self.config.is_telegram_configured:
            return False
        target_chat = chat_id or self.config.telegram_chat_id
        api_url = (
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": target_chat,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            try:
                resp = await client.post(api_url, json=payload)
                resp.raise_for_status()
                return True
            except Exception as exc:
                logger.error("Gagal mengirim pesan HTML Telegram: %s", exc)
                return False

    async def register_bot_commands(self) -> None:
        """Register native slash commands menu in Telegram."""
        if not self.config.is_telegram_configured:
            return
        api_url = (
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/setMyCommands"
        )
        commands = [
            {"command": "cek", "description": "Cek status bot & daftar lomba IT terbaru"},
            {"command": "status", "description": "Lihat status radar 24/7 saat ini"},
            {"command": "terbaru", "description": "Tampilkan 6 lomba IT terbaru"},
            {"command": "scan", "description": "Pindai internet sekarang juga secara manual"},
        ]
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            try:
                await client.post(api_url, json={"commands": commands})
            except Exception as exc:
                logger.debug("Gagal setMyCommands: %s", exc)

    async def process_pending_commands(
        self,
        storage: RadarStorage,
        poll_timeout: int = 1,
        on_scan_request: Optional[Callable[[], Awaitable[tuple[int, int]]]] = None,
    ) -> int:
        """Check Telegram getUpdates and reply to /status, /cek, /terbaru, /scan, or /start."""
        if not self.config.is_telegram_configured:
            return 0

        last_update_str = storage.get_meta("last_telegram_update_id", "0")
        offset = int(last_update_str) + 1 if last_update_str.isdigit() else 0
        api_url = (
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/getUpdates"
        )

        replied = 0
        req_timeout = max(10.0, float(poll_timeout) + 10.0)
        async with httpx.AsyncClient(timeout=req_timeout, verify=False) as client:
            try:
                resp = await client.get(
                    api_url, params={"offset": offset, "timeout": poll_timeout}
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])
            except Exception as exc:
                logger.debug("Gagal memeriksa getUpdates Telegram: %s", exc)
                return 0

        for upd in updates:
            upd_id = int(upd.get("update_id", 0))
            storage.set_meta("last_telegram_update_id", str(upd_id))

            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip().lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if not text or not chat_id:
                continue

            if text.startswith("/scan"):
                await self.send_raw_html(
                    "🔎 <b>Memulai pemindaian real-time sekarang...</b>\n"
                    "Mohon tunggu sekitar 15–30 detik.",
                    chat_id=chat_id,
                )
                if on_scan_request is not None:
                    valid_cnt, new_cnt = await on_scan_request()
                    await self.send_raw_html(
                        f"✅ <b>Pemindaian Selesai!</b>\n"
                        f"• Kandidat Lomba IT Valid: <b>{valid_cnt}</b>\n"
                        f"• Lomba Baru Ditemukan: <b>{new_cnt}</b>",
                        chat_id=chat_id,
                    )
                else:
                    await self.send_raw_html(
                        "ℹ️ Mode scan manual instan hanya tersedia saat daemon lokal aktif.",
                        chat_id=chat_id,
                    )
                replied += 1
            elif any(
                cmd in text
                for cmd in ["/start", "/status", "/cek", "/terbaru", "status", "cek", "lomba"]
            ):
                now_wib = datetime.now(WIB_TZ).strftime("%d %b %Y %H:%M WIB")
                recent = storage.get_recent_items(limit=6)
                lines = [
                    "📡 <b>STATUS RADAR LOMBA IT 24/7: AKTIF</b>",
                    f"🕒 <b>Waktu Server:</b> {now_wib}",
                    f"🗄️ <b>Total Lomba Terdata:</b> {storage.count_total()} lomba",
                    "",
                    "🏆 <b>6 Lomba IT &amp; Inovasi Terbaru yang Terdeteksi:</b>",
                ]
                for idx, it in enumerate(recent, start=1):
                    dl = html.escape(it.registration_deadline or "Cek di link")
                    t_esc = html.escape(it.title[:90])
                    u_esc = html.escape(it.url, quote=True)
                    lines.append(
                        f"\n{idx}. <a href=\"{u_esc}\"><b>{t_esc}</b></a>\n"
                        f"   ⏳ Batas: {dl} | 🏛️ {html.escape(it.source_name)}"
                    )
                lines.append(
                    "\n💡 <i>Perintah: /cek • /status • /terbaru • /scan</i>"
                )
                if await self.send_raw_html("\n".join(lines), chat_id=chat_id):
                    replied += 1

        return replied

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
