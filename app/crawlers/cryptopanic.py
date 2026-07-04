"""CryptoPanic crawler.

Strategy:
  1. If a CRYPTOPANIC_API_TOKEN is configured -> use the official currency-filtered API
     (clean, structured, reliable).
  2. Otherwise -> fall back to the public RSS feed and keyword-filter locally.
"""

import logging
from datetime import datetime

from app.crawlers.base import BaseCrawler
from app.models.domain import CrawledArticle, SymbolQuery
from app.models.enums import SourceSite
from app.utils.text import clean_text, normalize_url

logger = logging.getLogger(__name__)

_API_URL = "https://cryptopanic.com/api/v1/posts/"
_RSS_URL = "https://cryptopanic.com/news/rss/"


class CryptoPanicCrawler(BaseCrawler):
    site = SourceSite.CRYPTOPANIC

    async def crawl(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        if self.settings.cryptopanic_api_token:
            articles = await self._crawl_api(query, date_from, date_to)
            if articles:
                return articles
            logger.info("[%s] API returned nothing, falling back to RSS", self.site.value)
        return await self._crawl_rss(query, date_from, date_to)

    async def _crawl_api(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        params = {
            "auth_token": self.settings.cryptopanic_api_token,
            "currencies": query.symbol,
            "kind": "news",
            "public": "true",
        }
        data = await self._fetch_json(_API_URL, params=params)
        if not data:
            return []

        articles: list[CrawledArticle] = []
        for item in data.get("results", []):
            published = self._parse_date(item.get("published_at"))
            if not self._within_range(published, date_from, date_to):
                continue
            title = clean_text(item.get("title"))
            url = item.get("url") or ""
            if not title or not url:
                continue
            source = (item.get("source") or {}).get("title", "")
            articles.append(
                CrawledArticle(
                    title=title,
                    url=normalize_url(url),
                    source_site=self.site.value,
                    published_at=published,
                    summary=source,
                )
            )
            if len(articles) >= self.settings.crawl_max_articles_per_site:
                break
        return articles

    async def _crawl_rss(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        raw = await self._fetch_text(_RSS_URL)
        if not raw:
            return []
        return self._parse_feed(raw, query, date_from, date_to)
