"""Base crawler abstraction and shared RSS/HTML helpers.

All crawling is done via plain HTTP requests (httpx) + HTML/RSS parsing.
No browser is ever launched, so the whole process runs fully in the background.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import feedparser
import httpx
from dateutil import parser as date_parser

from app.config import Settings
from app.models.domain import CrawledArticle, SymbolQuery
from app.models.enums import SourceSite
from app.utils.text import clean_text, matches_keywords, normalize_url

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """Contract every per-site crawler must implement."""

    site: SourceSite

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    @abstractmethod
    async def crawl(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        """Return articles about `query` published within [date_from, date_to]."""
        raise NotImplementedError

    # ---- Shared helpers available to all subclasses ----

    async def _fetch_text(self, url: str, params: dict | None = None) -> str | None:
        """🔗 Perform a resilient GET; return response text or None on failure."""
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("[%s] fetch failed for %s: %s", self.site.value, url, exc)
            return None

    async def _fetch_json(self, url: str, params: dict | None = None) -> dict | None:
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[%s] json fetch failed for %s: %s", self.site.value, url, exc)
            return None

    def _parse_feed(
        self,
        raw: str,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        """📥 Parse an RSS/Atom feed, then filter by keyword and date window."""
        parsed = feedparser.parse(raw)
        articles: list[CrawledArticle] = []
        for entry in parsed.entries:
            title = clean_text(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            summary = clean_text(getattr(entry, "summary", ""))
            if not title or not link:
                continue

            published = self._entry_datetime(entry)
            if not self._within_range(published, date_from, date_to):
                continue

            # 🎯 Keep only items whose title/summary reference the coin
            if not matches_keywords(f"{title} {summary}", query.keywords):
                continue

            articles.append(
                CrawledArticle(
                    title=title,
                    url=normalize_url(link),
                    source_site=self.site.value,
                    published_at=published,
                    summary=summary,
                )
            )
            if len(articles) >= self.settings.crawl_max_articles_per_site:
                break
        return articles

    @staticmethod
    def _entry_datetime(entry) -> datetime | None:
        for attr in ("published", "updated", "created"):
            value = getattr(entry, attr, None)
            if value:
                try:
                    return date_parser.parse(value).astimezone(timezone.utc)
                except (ValueError, TypeError, OverflowError):
                    continue
        return None

    @staticmethod
    def _within_range(
        published: datetime | None,
        date_from: datetime,
        date_to: datetime,
    ) -> bool:
        # 💡 Keep items with an unknown date (better recall); AI can weigh them later
        if published is None:
            return True
        return date_from <= published <= date_to

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return date_parser.parse(value).astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None
