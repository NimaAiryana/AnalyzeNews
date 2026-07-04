"""Parallel, headless crawling + deduplicated persistence into MongoDB."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from pymongo import UpdateOne

from app.config import Settings
from app.crawlers.registry import CRAWLER_REGISTRY, all_sites
from app.db.mongodb import NEWS, get_db
from app.models.domain import CrawledArticle, SymbolQuery
from app.models.enums import SourceSite
from app.utils.text import url_hash

logger = logging.getLogger(__name__)


class CrawlService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def crawl_and_store(
        self,
        query: SymbolQuery,
        date_from: datetime,
        date_to: datetime,
        sites: list[SourceSite] | None = None,
    ) -> dict:
        """Crawl the requested sites concurrently and upsert results.

        Returns crawl statistics (per-site counts, new vs total stored).
        """
        sites = sites or all_sites()
        # ⚙️ One shared HTTP client; no browser is ever launched
        headers = {"User-Agent": self.settings.crawl_user_agent, "Accept": "*/*"}
        timeout = httpx.Timeout(self.settings.crawl_request_timeout)
        semaphore = asyncio.Semaphore(self.settings.crawl_concurrency)

        async with httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=True
        ) as client:

            async def run_site(site: SourceSite) -> tuple[SourceSite, list[CrawledArticle]]:
                async with semaphore:  # 🔄 bound concurrency across sites
                    crawler = CRAWLER_REGISTRY[site](client, self.settings)
                    try:
                        articles = await crawler.crawl(query, date_from, date_to)
                        logger.info("[%s] %s -> %d articles", query.symbol, site.value, len(articles))
                        return site, articles
                    except Exception as exc:  # 🚫 isolate failures per site
                        logger.exception("[%s] crawler %s failed: %s", query.symbol, site.value, exc)
                        return site, []

            results = await asyncio.gather(*(run_site(s) for s in sites))

        per_site = {site.value: len(articles) for site, articles in results}
        all_articles = [a for _, articles in results for a in articles]
        new_count = await self._persist(query.symbol, all_articles)

        return {
            "per_site": per_site,
            "crawled": len(all_articles),
            "new": new_count,
        }

    async def _persist(self, symbol: str, articles: list[CrawledArticle]) -> int:
        """🗄️ Upsert articles keyed by url_hash; never store the same article twice."""
        if not articles:
            return 0

        now = datetime.now(timezone.utc)
        ops: list[UpdateOne] = []
        seen: set[str] = set()
        for art in articles:
            h = url_hash(art.url)
            if h in seen:
                continue
            seen.add(h)
            ops.append(
                UpdateOne(
                    {"url_hash": h},
                    {
                        "$setOnInsert": {
                            "url_hash": h,
                            "url": art.url,
                            "title": art.title,
                            "source_site": art.source_site,
                            "published_at": art.published_at,
                            "summary": art.summary,
                            "content": art.content,
                            "first_crawled_at": now,
                        },
                        "$set": {"last_crawled_at": now},
                        # 🔗 Track which coins this article relates to
                        "$addToSet": {"symbols": symbol},
                    },
                    upsert=True,
                )
            )

        result = await get_db()[NEWS].bulk_write(ops, ordered=False)
        return result.upserted_count

    @staticmethod
    async def get_news_for_analysis(
        symbol: str,
        date_from: datetime,
        date_to: datetime,
    ) -> list[dict]:
        """📊 Fetch all stored news for a coin within the window (fresh + historical)."""
        query = {
            "symbols": symbol,
            "$or": [
                {"published_at": {"$gte": date_from, "$lte": date_to}},
                {"published_at": None},  # keep dateless items for recall
            ],
        }
        cursor = (
            get_db()[NEWS]
            .find(query)
            .sort("published_at", -1)
            .limit(200)
        )
        return [doc async for doc in cursor]
