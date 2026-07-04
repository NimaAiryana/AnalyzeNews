"""Turn stored news into a single AI prompt and persist the structured analysis."""

import json
import logging
import re
from datetime import datetime, timezone

from app.ai.base import AIProvider
from app.ai.prompt import build_system_prompt, build_user_prompt
from app.config import Settings
from app.db.mongodb import ANALYSES, get_db
from app.models.domain import SymbolQuery

logger = logging.getLogger(__name__)

_VALID_SENTIMENTS = {"bullish", "bearish", "neutral", "mixed"}


class AnalysisService:
    def __init__(self, settings: Settings, ai_provider: AIProvider) -> None:
        self.settings = settings
        self.ai = ai_provider

    async def analyze(
        self,
        query: SymbolQuery,
        news: list[dict],
        date_from: datetime,
        date_to: datetime,
        job_id: str | None = None,
    ) -> dict:
        """💡 Build one unified prompt from all news and store the AI's assessment."""
        system_prompt = build_system_prompt(self.settings.ai_output_language)
        user_prompt = build_user_prompt(query, date_from, date_to, news)

        raw = await self.ai.complete(system_prompt, user_prompt)
        parsed = self._parse_response(raw)

        doc = {
            "symbol": query.symbol,
            "date_from": date_from,
            "date_to": date_to,
            "article_count": len(news),
            "ai_provider": self.ai.name,
            "model": self.ai.model,
            "summary": parsed.get("summary", ""),
            "coin_status": parsed.get("coin_status", ""),
            "market_sentiment": parsed.get("market_sentiment", "neutral"),
            "sentiment_score": parsed.get("sentiment_score"),
            "key_points": parsed.get("key_points", []),
            "confidence": parsed.get("confidence"),
            "sources": [
                {
                    "url": n.get("url", ""),
                    "title": n.get("title", ""),
                    "source_site": n.get("source_site", ""),
                    "published_at": n.get("published_at"),
                    "summary": n.get("summary", ""),
                }
                for n in news
            ],
            "raw_response": raw,
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc),
        }

        result = await get_db()[ANALYSES].insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    def _parse_response(self, raw: str) -> dict:
        """🧪 Robustly parse the model's JSON, coercing types and clamping ranges."""
        data = self._safe_json(raw)
        if data is None:
            logger.warning("AI response was not valid JSON; storing as plain summary")
            return {"summary": raw.strip(), "market_sentiment": "neutral"}

        sentiment = str(data.get("market_sentiment", "neutral")).strip().lower()
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"

        return {
            "summary": str(data.get("summary", "")).strip(),
            "coin_status": str(data.get("coin_status", "")).strip(),
            "market_sentiment": sentiment,
            "sentiment_score": self._to_float(data.get("sentiment_score"), -1.0, 1.0),
            "confidence": self._to_float(data.get("confidence"), 0.0, 1.0),
            "key_points": [str(k).strip() for k in data.get("key_points", []) if str(k).strip()],
        }

    @staticmethod
    def _safe_json(raw: str) -> dict | None:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 🔍 Fallback: extract the first {...} block if the model added prose
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
            return None

    @staticmethod
    def _to_float(value, lo: float, hi: float) -> float | None:
        try:
            return max(lo, min(hi, float(value)))
        except (TypeError, ValueError):
            return None
