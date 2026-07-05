"""CryptoPanic crawler.

Strategy: scrape the server-rendered per-coin news feed at
`https://cryptopanic.com/news/{coin-slug}/`.

  1. 🔗 Resolve the coin slug from the symbol query (e.g. Bitcoin -> "bitcoin").
  2. 📥 Fetch the SSR listing page and parse each `li.ssr-feed__item`
     (title, article URL, source, published time).
  3. 🔍 Filter by the requested date window.
  4. 📄 Fetch each article's detail page to enrich it with the
     `div.ssr-article__body` description text.

No browser is launched; everything runs over plain HTTP.
"""

import asyncio
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.crawlers.base import BaseCrawler
from app.models.domain import CrawledArticle, SymbolQuery
from app.models.enums import SourceSite
from app.utils.text import clean_text, normalize_url

logger = logging.getLogger(__name__)

_BASE_URL = "https://cryptopanic.com"
_FEED_URL = "https://cryptopanic.com/news/{slug}/"


class CryptoPanicCrawler(BaseCrawler):
    site = SourceSite.CRYPTOPANIC

    async def crawl(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        # 🔗 CryptoPanic uses the full coin name as the URL slug (bitcoin, ethereum, ...)
        for slug in self._candidate_slugs(query):
            url = _FEED_URL.format(slug=slug)
            raw = await self._fetch_text(url)
            if raw:
                articles = await self._parse_listing(raw, date_from, date_to)
                if articles:
                    logger.info("[%s] slug '%s' -> %d articles", self.site.value, slug, len(articles))
                    return articles
        return []

    async def _parse_listing(
        self,
        raw: str,
        date_from: datetime,
        date_to: datetime,
    ) -> list[CrawledArticle]:
        """📊 Parse the SSR feed list into date-filtered articles."""
        soup = BeautifulSoup(raw, "lxml")
        articles: list[CrawledArticle] = []

        for item in soup.select("li.ssr-feed__item"):
            link = item.select_one("a.ssr-feed__link")
            if not link or not link.get("href"):
                continue

            title = clean_text(link.get_text())
            url = normalize_url(link["href"], base=_BASE_URL)
            if not title:
                continue

            source, published = self._parse_meta(item)
            if not self._within_range(published, date_from, date_to):
                continue

            articles.append(
                CrawledArticle(
                    title=title,
                    url=url,
                    source_site=self.site.value,
                    published_at=published,
                    summary=source,
                )
            )
            if len(articles) >= self.settings.crawl_max_articles_per_site:
                break

        # 📄 Enrich each article with its full description body (concurrently)
        await self._enrich_bodies(articles)
        return articles

    async def _enrich_bodies(self, articles: list[CrawledArticle]) -> None:
        """🔄 Fetch each article's detail page and extract its description body."""
        semaphore = asyncio.Semaphore(self.settings.crawl_concurrency)

        async def fetch_body(article: CrawledArticle) -> None:
            async with semaphore:
                raw = await self._fetch_text(article.url)
            if not raw:
                return
            soup = BeautifulSoup(raw, "lxml")
            body = soup.select_one("div.ssr-article__body")
            if body:
                article.content = clean_text(body.get_text(separator=" "))

        await asyncio.gather(*(fetch_body(a) for a in articles))

    @staticmethod
    def _candidate_slugs(query: SymbolQuery) -> list[str]:
        """🎯 Build ordered, de-duplicated slug candidates from the coin's terms."""
        raw_terms = [query.name, *query.aliases, query.symbol]
        slugs: list[str] = []
        for term in raw_terms:
            slug = (term or "").strip().lower().replace(" ", "-")
            if slug and slug not in slugs:
                slugs.append(slug)
        return slugs

    @staticmethod
    def _parse_meta(item) -> tuple[str, datetime | None]:
        """Extract (source, published_at) from a `span.ssr-feed__meta` block."""
        meta = item.select_one("span.ssr-feed__meta")
        if not meta:
            return "", None

        published: datetime | None = None
        time_el = meta.find("time")
        if time_el and time_el.get("datetime"):
            try:
                parsed = date_parser.parse(time_el["datetime"])
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                published = parsed.astimezone(timezone.utc)
            except (ValueError, TypeError, OverflowError):
                published = None

        # 💡 Source name is the leading text node before the first '·' separator
        source = ""
        for node in meta.contents:
            text = getattr(node, "get_text", lambda: str(node))()
            text = text.strip().strip("·").strip()
            if text:
                source = text
                break
        return source, published
