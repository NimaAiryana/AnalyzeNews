"""Async job lifecycle: create, run the crawl->analyze pipeline, track status."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.ai.factory import build_gemini_flash, build_gemini_pro
from app.config import Settings, get_settings
from app.db.mongodb import JOBS, get_db
from app.models.enums import JobStatus, JobType, SourceSite
from app.services.analysis_service import AnalysisService
from app.services.crawl_service import CrawlService
from app.services.symbol_service import get_symbol_query

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def create_crawl_job(
        self,
        symbol: str,
        days: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
        sites: list[SourceSite] | None,
    ) -> dict:
        """Create a crawl-only job document and launch as a background task."""
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
            "job_type": JobType.CRAWL.value,
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
        asyncio.create_task(self._run_crawl(job_id, symbol, resolved_from, resolved_to, sites))
        return doc

    async def create_analyze_job(
        self,
        symbol: str,
        days: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> dict:
        """Create an analysis-only job document and launch as a background task."""
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
            "job_type": JobType.ANALYZE.value,
            "params": {
                "date_from": resolved_from,
                "date_to": resolved_to,
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
        asyncio.create_task(self._run_analyze(job_id, symbol, resolved_from, resolved_to))
        return doc

    async def get_job(self, job_id: str) -> dict | None:
        return await get_db()[JOBS].find_one({"_id": job_id})

    async def _run_crawl(
        self,
        job_id: str,
        symbol: str,
        date_from: datetime,
        date_to: datetime,
        sites: list[SourceSite] | None,
    ) -> None:
        """Crawl news sites and store articles in MongoDB."""
        try:
            query = await get_symbol_query(symbol)

            # ---- Crawl ----
            await self._update(job_id, JobStatus.CRAWLING, "crawling news sites")
            crawl_service = CrawlService(self.settings)
            crawl_stats = await crawl_service.crawl_and_store(query, date_from, date_to, sites)

            # ---- Done ----
            await self._update(job_id, JobStatus.COMPLETED, f"crawled {crawl_stats.get('total_articles', 0)} articles")
            logger.info("Crawl job %s completed (%s)", job_id, symbol)

        except Exception as exc:
            logger.exception("Crawl job %s failed: %s", job_id, exc)
            await self._fail(job_id, str(exc))

    async def _run_analyze(
        self,
        job_id: str,
        symbol: str,
        date_from: datetime,
        date_to: datetime,
    ) -> None:
        """Analyze articles already stored in MongoDB using Gemini."""
        try:
            query = await get_symbol_query(symbol)

            # ---- Fetch articles from MongoDB ----
            await self._update(job_id, JobStatus.ANALYZING, "fetching articles from MongoDB")
            news = await CrawlService.get_news_for_analysis(symbol, date_from, date_to)

            # 🚫 اگر هیچ خبری پیدا نشد
            if not news:
                await self._update(
                    job_id,
                    JobStatus.COMPLETED,
                    "no articles found in the specified date range",
                )
                logger.info("Analysis job %s completed with 0 articles (%s)", job_id, symbol)
                return

            # ---- Analyze with Gemini Flash + Pro ----
            await self._update(
                job_id,
                JobStatus.ANALYZING,
                f"analyzing {len(news)} articles with Gemini Flash + Pro",
            )
            flash_provider = build_gemini_flash(self.settings)
            pro_provider = build_gemini_pro(self.settings)
            analysis_service = AnalysisService(self.settings, flash_provider, pro_provider)
            analysis = await analysis_service.analyze(query, news, date_from, date_to, job_id)

            # ---- Done ----
            await self._update(job_id, JobStatus.COMPLETED, "analysis complete")
            logger.info("Analysis job %s completed (%s)", job_id, symbol)

        except Exception as exc:
            logger.exception("Analysis job %s failed: %s", job_id, exc)
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
