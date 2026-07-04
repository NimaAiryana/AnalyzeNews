"""Builds the unified system + user prompt sent to the AI for a coin analysis."""

from datetime import datetime

from app.models.domain import SymbolQuery

_SYSTEM_TEMPLATE = """You are a senior crypto market analyst.
You will be given a batch of recent news headlines and summaries about a single cryptocurrency.
Analyse them objectively and produce a concise, fact-grounded assessment.

Write ALL free-text fields in {language}.

Respond with a SINGLE valid JSON object and nothing else, using EXACTLY this schema:
{{
  "summary": "1 to 3 short paragraphs summarising the most important news",
  "coin_status": "one to three sentences on the coin's current situation/outlook based only on the news",
  "market_sentiment": "one of: bullish | bearish | neutral | mixed",
  "sentiment_score": "a number from -1.0 (very bearish) to 1.0 (very bullish)",
  "key_points": ["short bullet", "short bullet"],
  "confidence": "a number from 0.0 to 1.0 reflecting how much signal the news provided"
}}

Rules:
- Base every statement strictly on the provided articles; do not invent facts or prices.
- If the news is thin or contradictory, say so and lower the confidence.
- Keep the summary tight and readable."""

_USER_TEMPLATE = """Coin: {name} ({symbol})
Time window: {date_from} to {date_to} (UTC)
Number of articles: {count}

Articles:
{articles}"""


def build_system_prompt(language: str) -> str:
    return _SYSTEM_TEMPLATE.format(language=language)


def build_user_prompt(
    query: SymbolQuery,
    date_from: datetime,
    date_to: datetime,
    articles: list[dict],
) -> str:
    lines: list[str] = []
    for idx, art in enumerate(articles, start=1):
        published = art.get("published_at")
        published_str = published.strftime("%Y-%m-%d %H:%M") if isinstance(published, datetime) else "unknown"
        summary = (art.get("summary") or "").strip()
        block = (
            f"[{idx}] ({art.get('source_site', '?')} | {published_str})\n"
            f"Title: {art.get('title', '').strip()}\n"
        )
        if summary:
            block += f"Summary: {summary}\n"
        block += f"URL: {art.get('url', '')}"
        lines.append(block)

    return _USER_TEMPLATE.format(
        name=query.name,
        symbol=query.symbol,
        date_from=date_from.strftime("%Y-%m-%d %H:%M"),
        date_to=date_to.strftime("%Y-%m-%d %H:%M"),
        count=len(articles),
        articles="\n\n".join(lines) if lines else "(no articles found)",
    )
