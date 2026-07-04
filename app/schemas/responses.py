"""Response models returned by the API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import JobStatus


class SymbolResponse(BaseModel):
    symbol: str
    name: str
    aliases: list[str]
    enabled: bool
    created_at: datetime | None = None


class JobCreatedResponse(BaseModel):
    job_id: str
    symbol: str
    status: JobStatus
    message: str = "Analysis job accepted. Poll GET /api/v1/jobs/{job_id} for the result."


class JobStatusResponse(BaseModel):
    job_id: str
    symbol: str
    status: JobStatus
    progress: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    result: dict[str, Any] | None = None


class NewsItemResponse(BaseModel):
    url: str
    title: str
    source_site: str
    published_at: datetime | None = None
    summary: str = ""


class AnalysisResponse(BaseModel):
    symbol: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    article_count: int
    ai_provider: str
    model: str
    summary: str
    coin_status: str
    market_sentiment: str
    sentiment_score: float | None = None
    key_points: list[str] = []
    sources: list[NewsItemResponse] = []
    created_at: datetime | None = None
