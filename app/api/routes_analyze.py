"""Crawl and Analyze endpoints: separate jobs for crawling and analysis."""

from fastapi import APIRouter, HTTPException, status

from app.models.enums import JobStatus, JobType
from app.schemas.requests import AnalyzeRequest, CrawlRequest
from app.schemas.responses import JobCreatedResponse, JobStatusResponse
from app.services.job_service import JobService
from app.services.symbol_service import SymbolNotFoundError, get_symbol

router = APIRouter(prefix="/api/v1", tags=["jobs"])
_jobs = JobService()


@router.post("/crawl", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def crawl(body: CrawlRequest):
    """Start an async crawl job.

    Crawls news sites for the given coin over the specified time window
    and stores articles in MongoDB. Does NOT run AI analysis.
    Returns immediately with a job_id; poll GET /api/v1/jobs/{job_id} for the result.
    """
    # ✅ Validate the symbol exists in the collection before spending work
    try:
        await get_symbol(body.symbol)
    except SymbolNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Symbol '{body.symbol}' is not registered. Add it via POST /api/v1/symbols first.",
        )

    job = await _jobs.create_crawl_job(
        symbol=body.symbol,
        days=body.days,
        date_from=body.date_from,
        date_to=body.date_to,
        sites=body.sites,
    )
    return JobCreatedResponse(
        job_id=job["_id"],
        symbol=job["symbol"],
        status=JobStatus(job["status"]),
        job_type=JobType.CRAWL.value,
        message="Crawl job accepted. Poll GET /api/v1/jobs/{job_id} for the result.",
    )


@router.post("/analyze", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze(body: AnalyzeRequest):
    """Start an async analysis job.

    Analyzes articles already stored in MongoDB (from a previous crawl job)
    using Gemini Flash + Pro in parallel to produce a reconciled verdict.
    Returns immediately with a job_id; poll GET /api/v1/jobs/{job_id} for the result.
    """
    # ✅ Validate the symbol exists in the collection before spending work
    try:
        await get_symbol(body.symbol)
    except SymbolNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Symbol '{body.symbol}' is not registered. Add it via POST /api/v1/symbols first.",
        )

    job = await _jobs.create_analyze_job(
        symbol=body.symbol,
        days=body.days,
        date_from=body.date_from,
        date_to=body.date_to,
    )
    return JobCreatedResponse(
        job_id=job["_id"],
        symbol=job["symbol"],
        status=JobStatus(job["status"]),
        job_type=JobType.ANALYZE.value,
        message="Analysis job accepted. Poll GET /api/v1/jobs/{job_id} for the result.",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
    """Poll the status and result of a job.

    Returns the job's current status (pending/crawling/analyzing/completed/failed),
    progress message, and the final result once complete.
    """
    job = await _jobs.get_job(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job '{job_id}' not found")
    return JobStatusResponse(
        job_id=job["_id"],
        symbol=job["symbol"],
        status=JobStatus(job["status"]),
        progress=job.get("progress"),
        error=job.get("error"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        result=job.get("result"),
    )


@router.post("/jobs/{job_id}/reprocess", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_job(job_id: str):
    """Reprocess an existing job.

    Takes a completed or failed job and creates a new job with the same parameters.
    The new job_id is returned immediately; poll GET /api/v1/jobs/{new_job_id} for the result.
    """
    old_job = await _jobs.get_job(job_id)
    if not old_job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job '{job_id}' not found")

    symbol = old_job.get("symbol")
    job_type = old_job.get("job_type", JobType.ANALYZE.value)
    params = old_job.get("params", {})
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    sites = params.get("sites")

    if job_type == JobType.CRAWL.value:
        new_job = await _jobs.create_crawl_job(
            symbol=symbol,
            days=None,
            date_from=date_from,
            date_to=date_to,
            sites=[s for s in sites] if sites else None,
        )
    else:  # ANALYZE
        new_job = await _jobs.create_analyze_job(
            symbol=symbol,
            days=None,
            date_from=date_from,
            date_to=date_to,
        )

    return JobCreatedResponse(
        job_id=new_job["_id"],
        symbol=new_job["symbol"],
        status=JobStatus(new_job["status"]),
        job_type=job_type,
        message=f"Job reprocessed. New job_id: {new_job['_id']}. Poll GET /api/v1/jobs/{new_job['_id']} for the result.",
    )
