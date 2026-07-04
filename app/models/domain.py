"""Internal domain objects passed between crawlers and services."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SymbolQuery:
    """Everything a crawler needs to search for a coin's news."""

    symbol: str  # e.g. "BTC"
    name: str  # e.g. "Bitcoin"
    aliases: list[str] = field(default_factory=list)  # e.g. ["btc", "bitcoin", "xbt"]

    @property
    def keywords(self) -> list[str]:
        # 🔍 De-duplicated, lower-cased set of terms used for keyword matching
        terms = [self.symbol, self.name, *self.aliases]
        seen: dict[str, None] = {}
        for term in terms:
            key = (term or "").strip().lower()
            if key:
                seen.setdefault(key, None)
        return list(seen.keys())


@dataclass
class CrawledArticle:
    """A single news item produced by a crawler (before persistence)."""

    title: str
    url: str
    source_site: str
    published_at: datetime | None
    summary: str = ""
    content: str = ""
