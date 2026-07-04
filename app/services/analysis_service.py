"""Two-stage Gemini analysis.

Stage 1: Flash and Pro analyse the same news IN PARALLEL; both runs are stored.
Stage 2: Pro reviews both stage-1 results and produces the final reconciled verdict.
Everything (both initial runs + the final verdict) is persisted as history.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

from app.ai.base import AIProvider
from app.ai.prompt import (
    build_final_system_prompt,
    build_final_user_prompt,
    build_system_prompt,
    build_user_prompt,
)
from app.config import Settings
from app.db.mongodb import ANALYSES, get_db
from app.models.domain import SymbolQuery

logger = logging.getLogger(__name__)

_VALID_SENTIMENTS = {"bullish", "bearish", "neutral", "mixed"}


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        flash_provider: AIProvider,
        pro_provider: AIProvider,
    ) -> None:
        self.settings = settings
        self.flash = flash_provider
        self.pro = pro_provider

    async def analyze(
        self,
        query: SymbolQuery,
        news: list[dict],
        date_from: datetime,
        date_to: datetime,
        job_id: str | None = None,
    ) -> dict:
        """💡 Run Flash+Pro in parallel, then let Pro reconcile them into a verdict."""
        language = self.settings.ai_output_language
        system_prompt = build_system_prompt(language)
        user_prompt = build_user_prompt(query, date_from, date_to, news)

        # ---- Stage 1: both models analyse the same news concurrently ----
        # Pro retries on transient errors (429/5xx), then falls back to Flash.
        flash_run, pro_run = await asyncio.gather(
            self._run_model(self.flash, "flash", system_prompt, user_prompt),
            self._run_with_fallback(self.pro, self.flash, "pro", system_prompt, user_prompt),
        )

        # ---- Stage 2: Pro reviews both stage-1 results for the final verdict ----
        final_system = build_final_system_prompt(language)
        final_user = build_final_user_prompt(query, date_from, date_to, flash_run, pro_run)
        final_run = await self._run_with_fallback(
            self.pro, self.flash, "final", final_system, final_user
        )

        final = final_run["parsed"]
        doc = {
            "symbol": query.symbol,
            "date_from": date_from,
            "date_to": date_to,
            "article_count": len(news),
            "ai_provider": "gemini",
            "model": self.pro.model,  # the final verdict is produced by Pro
            # 🎯 Top-level fields mirror the FINAL verdict (back-compat with responses)
            "summary": final.get("summary", ""),
            "coin_status": final.get("coin_status", ""),
            "market_sentiment": final.get("market_sentiment", "neutral"),
            "sentiment_score": final.get("sentiment_score"),
            "key_points": final.get("key_points", []),
            "confidence": final.get("confidence"),
            # 📊 Full history of every model run kept for auditing
            "stages": {
                "initial": [self._public_run(flash_run), self._public_run(pro_run)],
                "final": self._public_run(final_run),
            },
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
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc),
        }

        result = await get_db()[ANALYSES].insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def _run_with_fallback(
        self,
        primary: AIProvider,
        fallback: AIProvider,
        role: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """🚫➡️⚡ Try the primary model; if it still fails after retries, use Flash."""
        run = await self._run_model(primary, role, system_prompt, user_prompt)
        if run["error"] and fallback.model != primary.model:
            logger.warning(
                "%s: primary %s failed (%s); falling back to %s",
                role, primary.model, run["error"], fallback.model,
            )
            fb = await self._run_model(fallback, role, system_prompt, user_prompt)
            fb["fallback_used"] = True
            fb["primary_model"] = primary.model
            fb["primary_error"] = run["error"]
            return fb
        run["fallback_used"] = False
        return run

    async def _run_model(
        self,
        provider: AIProvider,
        role: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """🔄 Execute a single model call, capturing timing, output and any error."""
        start = time.monotonic()
        raw, error = "", None
        try:
            raw = await provider.complete(system_prompt, user_prompt)
        except Exception as exc:  # 🚫 isolate a single model failure
            error = str(exc)
            logger.exception("Gemini %s (%s) failed: %s", role, provider.model, exc)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "role": role,
            "model": provider.model,
            "parsed": self._parse_response(raw) if raw else {"market_sentiment": "neutral"},
            "raw_response": raw,
            "latency_ms": latency_ms,
            "error": error,
        }

    @staticmethod
    def _public_run(run: dict) -> dict:
        """Flatten a run into a storable history record."""
        parsed = run.get("parsed", {})
        return {
            "role": run.get("role"),
            "model": run.get("model"),
            "summary": parsed.get("summary", ""),
            "coin_status": parsed.get("coin_status", ""),
            "market_sentiment": parsed.get("market_sentiment", "neutral"),
            "sentiment_score": parsed.get("sentiment_score"),
            "key_points": parsed.get("key_points", []),
            "confidence": parsed.get("confidence"),
            "raw_response": run.get("raw_response", ""),
            "latency_ms": run.get("latency_ms"),
            "error": run.get("error"),
            # 🔄 Fallback bookkeeping (set when Pro was replaced by Flash)
            "fallback_used": run.get("fallback_used", False),
            "primary_model": run.get("primary_model"),
            "primary_error": run.get("primary_error"),
        }

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
