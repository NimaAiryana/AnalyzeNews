"""Request bodies accepted by the API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import SourceSite


class AddSymbolRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20, description="Ticker, e.g. BTC")
    name: str = Field(..., min_length=1, max_length=100, description="Full name, e.g. Bitcoin")
    aliases: list[str] = Field(default_factory=list, description="Extra search terms")
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()


class UpdateSymbolRequest(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    enabled: bool | None = None


class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="Ticker that must exist in the symbols collection")
    days: int | None = Field(
        default=None, ge=1, le=60, description="Look-back window in days (defaults to config)"
    )
    date_from: datetime | None = Field(default=None, description="Explicit range start (UTC)")
    date_to: datetime | None = Field(default=None, description="Explicit range end (UTC)")
    sites: list[SourceSite] | None = Field(
        default=None, description="Subset of sites to crawl; defaults to all"
    )

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()
