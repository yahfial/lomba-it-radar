# D:\alfa\Documents\Antigravity\lomba-it-radar\main.py
from __future__ import annotations

import argparse
import asyncio
import io
import logging
import sys

# Ensure UTF-8 terminal encoding on Windows PowerShell/CMD
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from src.config import RadarConfig
from src.engine import RadarEngine
from src.notifier import TelegramNotifier


def setup_logging() -> None:
    from pathlib import Path
    log_dir = Path("data")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "radar.log"

    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file, encoding="utf-8")
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bot Radar Lomba IT Nasional Indonesia 24/7 Real-time"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Jalankan 1 kali siklus pemindaian penuh lalu berhenti (cocok untuk tes / cron / GitHub Actions)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Jalankan pemindaian terus-menerus 24 jam nonstop sesuai interval di .env",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Uji pengiriman pesan ke akun/channel Telegram Anda",
    )
    parser.add_argument(
        "--list-history",
        type=int,
        nargs="?",
        const=15,
        default=None,
        help="Tampilkan daftar lomba IT terbaru yang sudah tersimpan di database lokal",
    )
    return parser.parse_args()


async def async_main() -> int:
    setup_logging()
    args = parse_args()
    config = RadarConfig()
    engine = RadarEngine(config)

    if args.test_telegram:
        notifier = TelegramNotifier(config)
        ok = await notifier.send_test_ping()
        return 0 if ok else 1

    if args.list_history is not None:
        items = engine.storage.get_recent_items(limit=args.list_history)
        print("=" * 85)
        print(f"📋 DAFTAR {len(items)} LOMBA IT NASIONAL TERBARU DI DATABASE RADAR")
        print("=" * 85)
        for idx, item in enumerate(items, start=1):
            cats = ", ".join(c.value for c in item.categories)
            print(f"{idx:2d}. [{cats}] (Skor: {item.relevance_score})")
            print(f"    Judul  : {item.title}")
            print(f"    Sumber : {item.source_name}")
            print(f"    Link   : {item.url}")
            print("-" * 85)
        return 0

    if args.daemon:
        await engine.run_daemon_forever()
        return 0

    # Default or --once: run a single scan cycle and print structured report
    summary = await engine.run_single_scan()
    recent = engine.storage.get_recent_items(limit=10)
    print("\n" + "=" * 85)
    print("🚀 RINGKASAN PEMINDAIAN REAL-TIME LOMBA IT INDONESIA")
    print("=" * 85)
    print(f"• Kandidat Lomba IT Valid Ditemukan : {summary.passed_filter}")
    print(f"• Lomba Baru Ditambahkan ke DB      : {summary.new_items_count}")
    print(f"• Terkirim ke Telegram              : {summary.notified_count}")
    print(f"• Total Lomba Tersimpan di Database : {engine.storage.count_total()}")
    print("=" * 85)

    if recent:
        print("\n🏆 10 LOMBA IT TERATAS YANG TERDETEKSI:")
        for idx, item in enumerate(recent, start=1):
            cats = ", ".join(c.value for c in item.categories)
            print(f"\n[{idx}] {item.title}")
            print(f"    🏷️  Kategori : {cats}")
            print(f"    🏛️  Sumber   : {item.source_name}")
            print(f"    🔗 URL      : {item.url}")
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(async_main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[INFO] Bot dihentikan oleh pengguna.")
        sys.exit(0)
