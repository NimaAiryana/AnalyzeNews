"""crypto.news crawler (WordPress-based site with tag + global RSS feeds).

Strategy:
  1. Try the coin-specific tag feed  -> https://crypto.news/tag/{slug}/feed/
  2. Merge with the global feed       -> https://crypto.news/feed/  (keyword-filtered)
"""

import logging
import re
from datetime import datetime

from app.crawlers.base import BaseCrawler
from app.models.domain import CrawledArticle, SymbolQuery
from app.models.enums import SourceSite

logger = logging.getLogger(__name__)

_GLOBAL_FEED = "https://crypto.news/feed/"
_TAG_FEED = "https://crypto.news/tag/{slug}/feed/"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug


class CryptoNewsCrawler(BaseCrawler):
    site = SourceSite.CRYPTO_NEWS

    async def crawl(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        collected: dict[str, CrawledArticle] = {}

        # 🔍 Coin-specific tag feed (most relevant); try name and symbol slugs
        for term in {_slugify(query.name), _slugify(query.symbol)}:
            if not term:
                continue
            raw = await self._fetch_text(_TAG_FEED.format(slug=term))
            if raw:
                for art in self._parse_feed(raw, query, date_from, date_to):
                    collected.setdefault(art.url, art)

        # 📥 Global feed as a supplement, keyword-filtered by the base parser
        raw = await self._fetch_text(_GLOBAL_FEED)
        if raw:
            for art in self._parse_feed(raw, query, date_from, date_to):
                collected.setdefault(art.url, art)

        return list(collected.values())[: self.settings.crawl_max_articles_per_site]
