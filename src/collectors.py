# D:\alfa\Documents\Antigravity\lomba-it-radar\src\collectors.py
from __future__ import annotations

import asyncio
import email.utils
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.classifier import (
    WIB_TZ,
    evaluate_competition_relevance,
    extract_registration_deadline,
    format_date_id,
    is_closed_event_text,
    is_deadline_valid_and_open,
    parse_deadline_date,
)
from src.config import RadarConfig
from src.models import CompetitionCategory, CompetitionItem, are_same_competition

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
    """
    Collects ONLY active, verified Indonesian IT competitions with concrete future
    registration deadlines (>= today WIB) across structured IT portals and news feeds.
    """

    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self.http_helper = RateLimitedHttpClient(config)

    def _is_within_age_limit(self, pub_date: Optional[datetime]) -> bool:
        if pub_date is None:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.max_age_days)
        return pub_date >= cutoff

    async def _verify_deadline_from_destination_page(
        self, client: httpx.AsyncClient, url: str
    ) -> Tuple[Optional[str], bool]:
        """
        Fetch destination article HTML to verify whether registration is still open
        and extract a concrete registration deadline.
        Returns (deadline_str, is_closed).
        """
        if "news.google.com" in url:
            return None, False

        html_text = await self.http_helper.get_text(client, url)
        if not html_text:
            return None, False

        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:6000]

        if is_closed_event_text(body_text):
            return None, True

        deadline = extract_registration_deadline(body_text)
        return deadline, False

    def _build_item_if_relevant(
        self,
        title: str,
        url: str,
        source_name: str,
        snippet: str = "",
        published_at: Optional[datetime] = None,
        organizer: str = "Penyelenggara Nasional",
        explicit_deadline: Optional[str] = None,
    ) -> Optional[CompetitionItem]:
        if not self._is_within_age_limit(published_at):
            return None

        clean_title = strip_html_tags(title)
        full_clean_snippet = strip_html_tags(snippet)
        if len(clean_title) < 5 or not url.startswith("http"):
            return None

        if is_closed_event_text(f"{clean_title} {full_clean_snippet[:1500]}"):
            return None

        # Evaluate IT relevance on title + lead summary (first 350 chars)
        is_valid, score, categories, matched_kws = evaluate_competition_relevance(
            clean_title, full_clean_snippet[:350]
        )
        if not is_valid:
            return None

        # HARD GATE: Every competition MUST have a concrete, non-expired future deadline (>= today WIB)
        deadline = explicit_deadline or extract_registration_deadline(
            f"{clean_title} {full_clean_snippet[:3500]}"
        )
        if not is_deadline_valid_and_open(deadline):
            return None

        parsed_dl = parse_deadline_date(deadline)
        formatted_deadline = format_date_id(parsed_dl) if parsed_dl else deadline

        clean_snippet = full_clean_snippet[:280]
        return CompetitionItem(
            title=clean_title,
            url=url.strip(),
            source_name=source_name,
            categories=categories,
            organizer=organizer,
            registration_deadline=formatted_deadline,
            snippet=clean_snippet,
            published_at=published_at,
            relevance_score=score,
            matched_keywords=matched_kws,
        )

    async def fetch_indonesia_hackathons(
        self, client: httpx.AsyncClient
    ) -> list[CompetitionItem]:
        """
        Scrape structured upcoming Indonesian hackathons from https://indonesiahackathons.com/
        using Schema.org JSON-LD (@type: ItemList -> @type: Event).
        """
        base_url = "https://indonesiahackathons.com/"
        html_text = await self.http_helper.get_text(client, base_url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        event_urls: list[str] = []

        for ld in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(ld.string or "{}")
            except json.JSONDecodeError:
                continue
            for node in data.get("@graph", []):
                if node.get("@type") == "ItemList":
                    for elem in node.get("itemListElement", []):
                        u = str(elem.get("url", "")).strip()
                        if u.startswith("http") and u not in event_urls:
                            event_urls.append(u)

        today_wib = datetime.now(WIB_TZ).date()
        results: list[CompetitionItem] = []

        for ev_url in event_urls[:12]:
            detail_html = await self.http_helper.get_text(client, ev_url)
            if not detail_html:
                continue
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            event_node: Optional[dict[str, object]] = None
            for ld in detail_soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(ld.string or "{}")
                except json.JSONDecodeError:
                    continue
                for node in data.get("@graph", []):
                    if node.get("@type") == "Event":
                        event_node = node
                        break
                if event_node:
                    break

            if not event_node:
                continue

            name = str(event_node.get("name", "")).strip()
            desc = str(event_node.get("description", "")).strip()
            start_raw = str(event_node.get("startDate", "")).strip()
            org_obj = event_node.get("organizer")
            organizer = (
                str(org_obj.get("name", "Hackathon Indonesia")).strip()
                if isinstance(org_obj, dict)
                else "Hackathon Indonesia"
            )

            start_dt = parse_rss_datetime(start_raw)
            if not start_dt:
                continue
            start_date_wib = start_dt.astimezone(WIB_TZ).date()
            if start_date_wib < today_wib:
                continue

            formatted_dl = format_date_id(start_date_wib)
            combined_lower = f"{name} {desc}".lower()
            cats: list[CompetitionCategory] = [CompetitionCategory.HACKATHON]
            kws: list[str] = ["hackathon"]
            if any(w in combined_lower for w in ("ai", "qwen", "machine learning", "data", "llm")):
                cats.append(CompetitionCategory.DATA_AI)
                kws.append("ai")
            if any(w in combined_lower for w in ("cyber", "security", "ctf")):
                cats.append(CompetitionCategory.CYBERSECURITY)
                kws.append("cybersecurity")

            results.append(
                CompetitionItem(
                    title=name,
                    url=ev_url,
                    source_name="IndonesiaHackathons.com",
                    categories=cats,
                    organizer=organizer,
                    registration_deadline=formatted_dl,
                    snippet=desc[:280],
                    published_at=datetime.now(timezone.utc),
                    relevance_score=95,
                    matched_keywords=kws,
                )
            )

        return results

    async def fetch_infolomba_it(
        self, client: httpx.AsyncClient
    ) -> list[CompetitionItem]:
        """
        Scrape dedicated IT Category (kategori=9) from https://www.infolomba.id/events?kategori=9.
        Only keeps competitions whose registration deadline is verified >= today WIB.
        """
        list_url = "https://www.infolomba.id/events?kategori=9"
        html_text = await self.http_helper.get_text(client, list_url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        results: list[CompetitionItem] = []

        for card in soup.select(".event-container"):
            title_el = card.select_one("h4.event-title, h3.event-title")
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)

            detail_a = card.find("a", href=re.compile(r"^info-"))
            if not detail_a:
                continue
            detail_url = urljoin("https://www.infolomba.id/", str(detail_a["href"]).strip())

            org_el = card.select_one(".penyelenggara")
            organizer = "InfoLomba IT"
            if org_el:
                org_txt = org_el.get_text(" ", strip=True)
                organizer = re.sub(r"^Diselenggarakan\s+oleh\s*", "", org_txt, flags=re.I).strip() or organizer

            card_text = card.get_text(" | ", strip=True)
            card_lower = card_text.lower()

            # Skip elementary/junior-high-only contests unless Mahasiswa/Umum/SMA is eligible
            if (
                ("sd /" in card_lower or "smp /" in card_lower)
                and not any(aud in card_lower for aud in ("mahasiswa", "umum", "sma"))
            ):
                continue

            # Extract card date range (e.g., "13 Okt - 24 Nov 2026") and immediately skip expired cards
            card_deadline = extract_registration_deadline(card_text)
            if not is_deadline_valid_and_open(card_deadline):
                continue

            # Fetch detail page to extract exact Penutupan Pendaftaran & full IT description
            detail_html = await self.http_helper.get_text(client, detail_url)
            detail_text = ""
            if detail_html:
                detail_soup = BeautifulSoup(detail_html, "html.parser")
                paragraphs = [
                    p.get_text(" ", strip=True)
                    for p in detail_soup.find_all("p")
                    if len(p.get_text(strip=True)) > 15
                ]
                detail_text = " ".join(paragraphs)

            if is_closed_event_text(detail_text):
                continue

            exact_deadline = extract_registration_deadline(detail_text) or card_deadline
            if not is_deadline_valid_and_open(exact_deadline):
                continue

            parsed_dl = parse_deadline_date(exact_deadline)
            formatted_dl = format_date_id(parsed_dl) if parsed_dl else exact_deadline

            # Classify IT categories based on title + detail text (already curated under kategori=9 IT)
            _, score, cats, kws = evaluate_competition_relevance(
                f"Lomba IT {title} pendaftaran dibuka",
                detail_text[:1200] or card_text,
            )
            if not cats:
                cats = [CompetitionCategory.GENERAL_IT]
            if not kws:
                kws = ["lomba it"]

            results.append(
                CompetitionItem(
                    title=title,
                    url=detail_url,
                    source_name="InfoLomba.id (Kategori IT)",
                    categories=cats,
                    organizer=organizer,
                    registration_deadline=formatted_dl,
                    snippet=(detail_text or card_text)[:280],
                    published_at=datetime.now(timezone.utc),
                    relevance_score=max(score, 85),
                    matched_keywords=kws,
                )
            )

        return results

    async def fetch_google_news_rss(
        self, client: httpx.AsyncClient, query: str
    ) -> list[CompetitionItem]:
        """Query Google News Indonesia RSS and keep ONLY items with verified future deadlines."""
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
        """Query Bing News RSS Indonesia with deep page deadline verification."""
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

                if not self._is_within_age_limit(pub_dt):
                    continue

                clean_title = strip_html_tags(title)
                clean_desc = strip_html_tags(desc)
                ok_prelim, _, _, _ = evaluate_competition_relevance(clean_title, clean_desc[:350])
                if not ok_prelim:
                    continue

                deadline = extract_registration_deadline(f"{clean_title} {clean_desc}")
                if not deadline:
                    # Deep page fetch to verify whether registration is genuinely open & extract deadline
                    page_dl, is_closed = await self._verify_deadline_from_destination_page(client, link)
                    if is_closed:
                        continue
                    deadline = page_dl

                built = self._build_item_if_relevant(
                    title=title,
                    url=link,
                    source_name="Bing Web Radar ID",
                    snippet=desc,
                    published_at=pub_dt,
                    explicit_deadline=deadline,
                )
                if built:
                    results.append(built)
        except ET.ParseError as exc:
            logger.warning("Failed parsing Bing RSS XML: %s", exc)

        return results

    async def fetch_direct_rss_feed(
        self, client: httpx.AsyncClient, feed_url: str, label: str
    ) -> list[CompetitionItem]:
        """Fetch direct competition RSS feeds (KabarLomba, Dicoding Blog) with mandatory future deadline."""
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
        """Scrape public Telegram broadcast web preview (`https://t.me/s/<channel>`) for open IT contests."""
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
        """Run all collectors and return semantically deduplicated, deadline-verified IT competitions."""
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
            # 1. Dedicated Structured Indonesian IT Portals (Highest Accuracy & Exact Dates)
            try:
                all_candidates.extend(await self.fetch_indonesia_hackathons(client))
            except Exception as exc:
                errors.append(f"IndonesiaHackathons: {exc}")

            try:
                all_candidates.extend(await self.fetch_infolomba_it(client))
            except Exception as exc:
                errors.append(f"InfoLombaIT: {exc}")

            # 2. Direct Competition Portal RSS Feeds (Full-text descriptions + explicit deadlines)
            for feed_url, label in self.config.direct_rss_feeds:
                try:
                    all_candidates.extend(await self.fetch_direct_rss_feed(client, feed_url, label))
                except Exception as exc:
                    errors.append(f"DirectRSS({label}): {exc}")

            # 3. Public Telegram Competition Channels
            for channel in self.config.telegram_public_channels:
                try:
                    all_candidates.extend(await self.fetch_telegram_public_channel(client, channel))
                except Exception as exc:
                    errors.append(f"Telegram({channel}): {exc}")

            # 4. Google News & Bing News Indonesia (Only passes with verified future deadline!)
            for q in self.config.google_news_queries:
                try:
                    all_candidates.extend(await self.fetch_google_news_rss(client, q))
                except Exception as exc:
                    errors.append(f"GoogleNews({q}): {exc}")

            for q in self.config.bing_news_queries:
                try:
                    all_candidates.extend(await self.fetch_bing_news_rss(client, q))
                except Exception as exc:
                    errors.append(f"BingNews({q}): {exc}")

        # In-memory semantic deduplication (1 announcement per distinct competition event)
        ranked_candidates = sorted(
            all_candidates,
            key=lambda x: (1 if x.registration_deadline else 0, x.relevance_score),
            reverse=True,
        )
        deduped_items: list[CompetitionItem] = []
        seen_fingerprints: set[str] = set()
        seen_titles: set[str] = set()
        for item in ranked_candidates:
            if item.fingerprint in seen_fingerprints or item.title_fingerprint in seen_titles:
                continue
            if any(
                are_same_competition(item.title, existing.title, item.event_key, existing.event_key)
                for existing in deduped_items
            ):
                continue
            deduped_items.append(item)
            seen_fingerprints.add(item.fingerprint)
            seen_titles.add(item.title_fingerprint)

        return deduped_items, errors
