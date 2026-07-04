"""Analyze endpoints: kick off an async job and poll its status/result."""

from fastapi import APIRouter, HTTPException, status

from app.models.enums import JobStatus
from app.schemas.requests import AnalyzeRequest
from app.schemas.responses import JobCreatedResponse, JobStatusResponse
from app.services.job_service import JobService
from app.services.symbol_service import SymbolNotFoundError, get_symbol

router = APIRouter(prefix="/api/v1", tags=["analyze"])
_jobs = JobService()


@router.post("/analyze", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze(body: AnalyzeRequest):
    # ✅ Validate the symbol exists in the collection before spending work
    try:
        await get_symbol(body.symbol)
    except SymbolNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Symbol '{body.symbol}' is not registered. Add it via POST /api/v1/symbols first.",
        )

    job = await _jobs.create_job(
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
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
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
