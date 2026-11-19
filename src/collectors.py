# D:\alfa\Documents\Antigravity\lomba-it-radar\src\collectors.py
from __future__ import annotations

import asyncio
import email.utils
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.classifier import (
    evaluate_competition_relevance,
    extract_registration_deadline,
    is_deadline_expired,
)
from src.config import RadarConfig
from src.models import CompetitionItem

logger = logging.getLogger("lomba_radar.collectors")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


class RateLimitedHttpClient:
    """Async HTTP client with strict rate limiting, timeout, and optional proxy."""

    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self._min_interval = 1.0 / max(0.5, config.max_requests_per_second)
        self._lock = asyncio.Lock()
        self._last_request_time: float = 0.0

    async def get_text(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = asyncio.get_running_loop().time()

        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("HTTP request failed for %s: %s", url, exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error fetching %s: %s", url, exc)
            return None


def parse_rss_datetime(raw_date: Optional[str]) -> Optional[datetime]:
    """Parse RFC-2822 or ISO-8601 date strings into timezone-aware UTC datetime."""
    if not raw_date:
        return None
    cleaned = raw_date.strip()
    try:
        dt = email.utils.parsedate_to_datetime(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def strip_html_tags(raw_html: str) -> str:
    """Clean HTML snippet into plain text."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


class MultiSourceRadarCollector:
    """Collects Indonesian IT competition info across Google News, Bing News, Dicoding, and Telegram."""

    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self.http_helper = RateLimitedHttpClient(config)

    def _is_within_age_limit(self, pub_date: Optional[datetime]) -> bool:
        if pub_date is None:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.max_age_days)
        return pub_date >= cutoff

    def _build_item_if_relevant(
        self,
        title: str,
        url: str,
        source_name: str,
        snippet: str = "",
        published_at: Optional[datetime] = None,
        organizer: str = "Penyelenggara Nasional",
    ) -> Optional[CompetitionItem]:
        if not self._is_within_age_limit(published_at):
            return None

        clean_title = strip_html_tags(title)
        full_clean_snippet = strip_html_tags(snippet)
        if len(clean_title) < 5 or not url.startswith("http"):
            return None

        # Evaluate IT relevance on title + lead summary (first 350 chars) so footer boilerplate doesn't cause false positives
        is_valid, score, categories, matched_kws = evaluate_competition_relevance(
            clean_title, full_clean_snippet[:350]
        )
        if not is_valid:
            return None

        # Extract deadline from full article text and reject if expired
        deadline = extract_registration_deadline(f"{clean_title} {full_clean_snippet[:3500]}")
        if is_deadline_expired(deadline):
            return None

        clean_snippet = full_clean_snippet[:280]

        return CompetitionItem(
            title=clean_title,
            url=url.strip(),
            source_name=source_name,
            categories=categories,
            organizer=organizer,
            registration_deadline=deadline,
            snippet=clean_snippet,
            published_at=published_at,
            relevance_score=score,
            matched_keywords=matched_kws,
        )

    async def fetch_google_news_rss(
        self, client: httpx.AsyncClient, query: str
    ) -> list[CompetitionItem]:
        """Query Google News Indonesia RSS for newly indexed pages matching keyword."""
        encoded_q = quote_plus(f"{query} when:{self.config.max_age_days}d")
        rss_url = (
            f"https://news.google.com/rss/search?q={encoded_q}&hl=id&gl=ID&ceid=ID:id"
        )
        xml_text = await self.http_helper.get_text(client, rss_url)
        if not xml_text:
            return []

        results: list[CompetitionItem] = []
        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                # Extract clean target URL if wrapped in Bing apiclick redirect
                try:
                    parsed_bing = urlparse(link)
                    qs = parse_qs(parsed_bing.query)
                    if "url" in qs and qs["url"]:
                        link = unquote(qs["url"][0])
                except Exception:
                    pass
                desc = (item_el.findtext("description") or "").strip()
                pub_raw = item_el.findtext("pubDate")
                source_el = item_el.find("source")
                publisher = (
                    source_el.text.strip()
                    if source_el is not None and source_el.text
                    else "Web Indonesia"
                )

                pub_dt = parse_rss_datetime(pub_raw)
                built = self._build_item_if_relevant(
                    title=title,
                    url=link,
                    source_name=f"Google Radar ({publisher})",
                    snippet=desc,
                    published_at=pub_dt,
                    organizer=publisher,
                )
                if built:
                    results.append(built)
        except ET.ParseError as exc:
            logger.warning("Failed parsing Google News RSS XML: %s", exc)

        return results

    async def fetch_bing_news_rss(
        self, client: httpx.AsyncClient, query: str
    ) -> list[CompetitionItem]:
        """Query Bing News RSS Indonesia for real-time keyword discovery."""
        encoded_q = quote_plus(query)
        rss_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&cc=id"
        xml_text = await self.http_helper.get_text(client, rss_url)
        if not xml_text:
            return []

        results: list[CompetitionItem] = []
        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                # Extract clean target URL if wrapped in Bing apiclick redirect
                try:
                    parsed_bing = urlparse(link)
                    qs = parse_qs(parsed_bing.query)
                    if "url" in qs and qs["url"]:
                        link = unquote(qs["url"][0])
                except Exception:
                    pass
                desc = (item_el.findtext("description") or "").strip()
                pub_raw = item_el.findtext("pubDate")
                pub_dt = parse_rss_datetime(pub_raw)

                built = self._build_item_if_relevant(
                    title=title,
                    url=link,
                    source_name="Bing Web Radar ID",
                    snippet=desc,
                    published_at=pub_dt,
                )
                if built:
                    results.append(built)
        except ET.ParseError as exc:
            logger.warning("Failed parsing Bing RSS XML: %s", exc)

        return results

    async def fetch_direct_rss_feed(
        self, client: httpx.AsyncClient, feed_url: str, label: str
    ) -> list[CompetitionItem]:
        """Fetch and parse direct competition portal RSS feeds (KabarLomba, Dicoding Blog, etc.)."""
        xml_text = await self.http_helper.get_text(client, feed_url)
        if not xml_text:
            return []

        results: list[CompetitionItem] = []
        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                desc = (item_el.findtext("description") or "").strip()
                pub_raw = item_el.findtext("pubDate")
                pub_dt = parse_rss_datetime(pub_raw)

                built = self._build_item_if_relevant(
                    title=title,
                    url=link,
                    source_name=label,
                    snippet=desc,
                    published_at=pub_dt,
                    organizer=label,
                )
                if built:
                    results.append(built)
        except ET.ParseError as exc:
            logger.warning("Failed parsing direct RSS XML (%s): %s", label, exc)

        return results

    async def fetch_telegram_public_channel(
        self, client: httpx.AsyncClient, channel_username: str
    ) -> list[CompetitionItem]:
        """Scrape public Telegram broadcast web preview (`https://t.me/s/<channel>`) without API login."""
        clean_handle = channel_username.lstrip("@").strip()
        url = f"https://t.me/s/{clean_handle}"
        html_text = await self.http_helper.get_text(client, url)
        if not html_text:
            return []

        results: list[CompetitionItem] = []
        soup = BeautifulSoup(html_text, "html.parser")
        message_wraps = soup.select(".tgme_widget_message_wrap")

        for wrap in message_wraps:
            text_div = wrap.select_one(".tgme_widget_message_text")
            if not text_div:
                continue

            raw_text = text_div.get_text("\n", strip=True)
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            if not lines:
                continue

            headline = lines[0][:140]
            if len(headline) < 10 and len(lines) > 1:
                headline = f"{lines[0]} - {lines[1]}"[:140]

            date_link = wrap.select_one("a.tgme_widget_message_date")
            post_url = (
                str(date_link["href"]).strip()
                if date_link and date_link.has_attr("href")
                else url
            )

            time_el = wrap.select_one("time[datetime]")
            pub_dt: Optional[datetime] = None
            if time_el and time_el.has_attr("datetime"):
                pub_dt = parse_rss_datetime(str(time_el["datetime"]))

            built = self._build_item_if_relevant(
                title=headline,
                url=post_url,
                source_name=f"Telegram @{clean_handle}",
                snippet=raw_text,
                published_at=pub_dt,
                organizer=f"Via @{clean_handle}",
            )
            if built:
                results.append(built)

        return results

    async def collect_all(self) -> Tuple[list[CompetitionItem], list[str]]:
        """Run all collectors and return deduplicated batch of candidate items + error logs."""
        errors: list[str] = []
        all_candidates: list[CompetitionItem] = []

        client_kwargs: dict[str, object] = {
            "headers": DEFAULT_HEADERS,
            "timeout": httpx.Timeout(self.config.request_timeout_seconds),
            "verify": False,
        }
        if self.config.http_proxy:
            client_kwargs["proxy"] = self.config.http_proxy

        async with httpx.AsyncClient(**client_kwargs) as client:  # type: ignore[arg-type]
            # 1. Google News Indonesia Real-Time Search
            for q in self.config.google_news_queries:
                try:
                    items = await self.fetch_google_news_rss(client, q)
                    all_candidates.extend(items)
                except Exception as exc:
                    errors.append(f"GoogleNews({q}): {exc}")

            # 2. Bing News Indonesia Search
            for q in self.config.bing_news_queries:
                try:
                    items = await self.fetch_bing_news_rss(client, q)
                    all_candidates.extend(items)
                except Exception as exc:
                    errors.append(f"BingNews({q}): {exc}")

            # 3. Direct Competition & Tech Portal RSS Feeds (KabarLomba, Dicoding Blog)
            for feed_url, label in self.config.direct_rss_feeds:
                try:
                    rss_items = await self.fetch_direct_rss_feed(client, feed_url, label)
                    all_candidates.extend(rss_items)
                except Exception as exc:
                    errors.append(f"DirectRSS({label}): {exc}")

            # 4. Public Telegram Channels
            for channel in self.config.telegram_public_channels:
                try:
                    tg_items = await self.fetch_telegram_public_channel(client, channel)
                    all_candidates.extend(tg_items)
                except Exception as exc:
                    errors.append(f"Telegram({channel}): {exc}")

        # In-memory deduplication by fingerprint & title_fingerprint
        unique_map: dict[str, CompetitionItem] = {}
        seen_titles: set[str] = set()
        for item in sorted(all_candidates, key=lambda x: x.relevance_score, reverse=True):
            if item.fingerprint in unique_map or item.title_fingerprint in seen_titles:
                continue
            unique_map[item.fingerprint] = item
            seen_titles.add(item.title_fingerprint)

        return list(unique_map.values()), errors
