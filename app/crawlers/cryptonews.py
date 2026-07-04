"""cryptonews.com crawler.

Strategy:
  1. Try known RSS feed endpoints (multiple candidates for resilience).
  2. Fall back to parsing the HTML news listing page if feeds are unavailable.
All results are keyword-filtered against the coin's terms.
"""

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler
from app.models.domain import CrawledArticle, SymbolQuery
from app.models.enums import SourceSite
from app.utils.text import clean_text, matches_keywords, normalize_url

logger = logging.getLogger(__name__)

_FEED_CANDIDATES = [
    "https://cryptonews.com/news/feed/",
    "https://cryptonews.com/feed/",
]
_HTML_LISTING = "https://cryptonews.com/news/"


class CryptoNewsComCrawler(BaseCrawler):
    site = SourceSite.CRYPTONEWS

    async def crawl(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        collected: dict[str, CrawledArticle] = {}

        # 📥 Try RSS feeds first
        for feed_url in _FEED_CANDIDATES:
            raw = await self._fetch_text(feed_url)
            if raw:
                for art in self._parse_feed(raw, query, date_from, date_to):
                    collected.setdefault(art.url, art)
            if collected:
                break

        # 🔍 HTML fallback when feeds yielded nothing
        if not collected:
            for art in await self._crawl_html(query):
                collected.setdefault(art.url, art)

        return list(collected.values())[: self.settings.crawl_max_articles_per_site]

    async def _crawl_html(self, query: SymbolQuery) -> list[CrawledArticle]:
        raw = await self._fetch_text(_HTML_LISTING)
        if not raw:
            return []

        soup = BeautifulSoup(raw, "lxml")
        articles: list[CrawledArticle] = []
        seen: set[str] = set()

        # 🏗️ Generic anchor scan: pick links that point to article pages
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            title = clean_text(anchor.get_text())
            if not title or len(title) < 25:
                continue
            if "cryptonews.com" not in href and href.startswith("http"):
                continue
            if not matches_keywords(title, query.keywords):
                continue

            url = normalize_url(href, base=_HTML_LISTING)
            if url in seen:
                continue
            seen.add(url)
            articles.append(
                CrawledArticle(
                    title=title,
                    url=url,
                    source_site=self.site.value,
                    published_at=None,
                    summary="",
                )
            )
            if len(articles) >= self.settings.crawl_max_articles_per_site:
                break
        return articles
