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


_FINAL_SYSTEM_TEMPLATE = """You are the lead crypto market analyst performing a FINAL REVIEW.
Two independent AI analyses of the same news were produced: one by a fast model and one by a deep model.
Your job is to reconcile them into a single, higher-quality final verdict.

Write ALL free-text fields in {language}.

Consider where the two analyses agree and disagree. Trust well-supported claims,
discount unsupported ones, and prefer the interpretation best grounded in the news.
If one analysis is empty or failed, rely on the other.

Respond with a SINGLE valid JSON object and nothing else, using EXACTLY this schema:
{{
  "summary": "1 to 3 short paragraphs: the reconciled, most important takeaways",
  "coin_status": "one to three sentences on the coin's current situation/outlook",
  "market_sentiment": "one of: bullish | bearish | neutral | mixed",
  "sentiment_score": "a number from -1.0 (very bearish) to 1.0 (very bullish)",
  "key_points": ["short bullet", "short bullet"],
  "confidence": "a number from 0.0 to 1.0 reflecting overall signal strength and model agreement"
}}

Rules:
- Base the verdict on the two analyses and the underlying news; do not invent facts or prices.
- Note briefly in the summary if the two models disagreed on the outlook."""

_FINAL_USER_TEMPLATE = """Coin: {name} ({symbol})
Time window: {date_from} to {date_to} (UTC)

--- Analysis A (fast model: {flash_model}) ---
{flash_block}

--- Analysis B (deep model: {pro_model}) ---
{pro_block}

Produce the final reconciled verdict."""


def build_system_prompt(language: str) -> str:
    return _SYSTEM_TEMPLATE.format(language=language)


def build_final_system_prompt(language: str) -> str:
    return _FINAL_SYSTEM_TEMPLATE.format(language=language)


def _render_run_block(run: dict) -> str:
    if run.get("error"):
        return f"(this model failed: {run['error']})"
    parsed = run.get("parsed", {})
    key_points = parsed.get("key_points", []) or []
    kp = "\n".join(f"  - {p}" for p in key_points) if key_points else "  (none)"
    return (
        f"summary: {parsed.get('summary', '')}\n"
        f"coin_status: {parsed.get('coin_status', '')}\n"
        f"market_sentiment: {parsed.get('market_sentiment', '')}\n"
        f"sentiment_score: {parsed.get('sentiment_score')}\n"
        f"confidence: {parsed.get('confidence')}\n"
        f"key_points:\n{kp}"
    )


def build_final_user_prompt(
    query: SymbolQuery,
    date_from: datetime,
    date_to: datetime,
    flash_run: dict,
    pro_run: dict,
) -> str:
    return _FINAL_USER_TEMPLATE.format(
        name=query.name,
        symbol=query.symbol,
        date_from=date_from.strftime("%Y-%m-%d %H:%M"),
        date_to=date_to.strftime("%Y-%m-%d %H:%M"),
        flash_model=flash_run.get("model", "flash"),
        pro_model=pro_run.get("model", "pro"),
        flash_block=_render_run_block(flash_run),
        pro_block=_render_run_block(pro_run),
    )


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
