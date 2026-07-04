"""Async job lifecycle: create, run the crawl->analyze pipeline, track status."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.ai.factory import build_ai_provider
from app.config import Settings, get_settings
from app.db.mongodb import JOBS, get_db
from app.models.enums import JobStatus, SourceSite
from app.services.analysis_service import AnalysisService
from app.services.crawl_service import CrawlService
from app.services.symbol_service import get_symbol_query

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def create_job(
        self,
        symbol: str,
        days: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
        sites: list[SourceSite] | None,
    ) -> dict:
        """Create a job document and launch the pipeline as a background task."""
        resolved_to = date_to or datetime.now(timezone.utc)
        if date_from:
            resolved_from = date_from
        else:
            window = days or self.settings.crawl_default_days
            resolved_from = resolved_to - timedelta(days=window)

        job_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        doc = {
            "_id": job_id,
            "symbol": symbol.upper(),
            "params": {
                "date_from": resolved_from,
                "date_to": resolved_to,
                "sites": [s.value for s in sites] if sites else None,
            },
            "status": JobStatus.PENDING.value,
            "progress": "queued",
            "error": None,
            "result": None,
            "created_at": now,
            "updated_at": now,
        }
        await get_db()[JOBS].insert_one(doc)

        # 🚀 Fire-and-forget; API returns immediately while this runs in background
        asyncio.create_task(self._run(job_id, symbol, resolved_from, resolved_to, sites))
        return doc

    async def get_job(self, job_id: str) -> dict | None:
        return await get_db()[JOBS].find_one({"_id": job_id})

    async def _run(
        self,
        job_id: str,
        symbol: str,
        date_from: datetime,
        date_to: datetime,
        sites: list[SourceSite] | None,
    ) -> None:
        try:
            query = await get_symbol_query(symbol)

            # ---- Stage 1: crawl ----
            await self._update(job_id, JobStatus.CRAWLING, "crawling news sites")
            crawl_service = CrawlService(self.settings)
            crawl_stats = await crawl_service.crawl_and_store(query, date_from, date_to, sites)

            news = await CrawlService.get_news_for_analysis(symbol, date_from, date_to)

            # ---- Stage 2: analyze ----
            await self._update(
                job_id,
                JobStatus.ANALYZING,
                f"analyzing {len(news)} articles with AI",
            )
            ai_provider = build_ai_provider(self.settings)
            analysis_service = AnalysisService(self.settings, ai_provider)
            analysis = await analysis_service.analyze(query, news, date_from, date_to, job_id)

            # ---- Done ----
            await self._complete(job_id, crawl_stats, analysis)
            logger.info("Job %s completed (%s)", job_id, symbol)

        except Exception as exc:  # 🚫 any failure marks the job failed with a message
            logger.exception("Job %s failed: %s", job_id, exc)
            await self._fail(job_id, str(exc))

    async def _update(self, job_id: str, status: JobStatus, progress: str) -> None:
        await get_db()[JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": status.value,
                "progress": progress,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def _complete(self, job_id: str, crawl_stats: dict, analysis: dict) -> None:
        await get_db()[JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": JobStatus.COMPLETED.value,
                "progress": "done",
                "updated_at": datetime.now(timezone.utc),
                "result": {
                    "analysis_id": str(analysis["_id"]),
                    "crawl": crawl_stats,
                    "summary": analysis.get("summary"),
                    "coin_status": analysis.get("coin_status"),
                    "market_sentiment": analysis.get("market_sentiment"),
                    "sentiment_score": analysis.get("sentiment_score"),
                    "key_points": analysis.get("key_points", []),
                    "article_count": analysis.get("article_count", 0),
                },
            }},
        )

    async def _fail(self, job_id: str, error: str) -> None:
        await get_db()[JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": JobStatus.FAILED.value,
                "progress": "failed",
                "error": error,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
