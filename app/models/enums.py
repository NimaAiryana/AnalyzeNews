"""Shared enumerations used across the engine."""

from enum import Enum


class SourceSite(str, Enum):
    """Hardcoded, per-site crawler identifiers."""

    CRYPTOPANIC = "cryptopanic"
    CRYPTO_NEWS = "crypto_news"
    CRYPTONEWS = "cryptonews"


class JobStatus(str, Enum):
    PENDING = "pending"
    CRAWLING = "crawling"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class MarketSentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
