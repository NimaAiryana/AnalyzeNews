"""Read-only endpoints to inspect stored news and past analyses."""

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from app.db.mongodb import ANALYSES, NEWS, get_db
from app.schemas.responses import AnalysisResponse, NewsItemResponse

router = APIRouter(prefix="/api/v1", tags=["data"])


@router.get("/news", response_model=list[NewsItemResponse])
async def list_news(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = {"symbols": symbol.upper()} if symbol else {}
    cursor = get_db()[NEWS].find(query).sort("published_at", -1).limit(limit)
    return [
        NewsItemResponse(
            url=d.get("url", ""),
            title=d.get("title", ""),
            source_site=d.get("source_site", ""),
            published_at=d.get("published_at"),
            summary=d.get("summary", ""),
        )
        async for d in cursor
    ]


@router.get("/analyses/{symbol}/latest", response_model=AnalysisResponse)
async def latest_analysis(symbol: str):
    doc = await get_db()[ANALYSES].find_one(
        {"symbol": symbol.upper()}, sort=[("created_at", -1)]
    )
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No analysis found for '{symbol}'")
    return _analysis_to_response(doc)


@router.get("/analyses/id/{analysis_id}", response_model=AnalysisResponse)
async def analysis_by_id(analysis_id: str):
    try:
        oid = ObjectId(analysis_id)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid analysis id")
    doc = await get_db()[ANALYSES].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Analysis '{analysis_id}' not found")
    return _analysis_to_response(doc)


def _analysis_to_response(doc: dict) -> AnalysisResponse:
    return AnalysisResponse(
        symbol=doc["symbol"],
        date_from=doc.get("date_from"),
        date_to=doc.get("date_to"),
        article_count=doc.get("article_count", 0),
        ai_provider=doc.get("ai_provider", ""),
        model=doc.get("model", ""),
        summary=doc.get("summary", ""),
        coin_status=doc.get("coin_status", ""),
        market_sentiment=doc.get("market_sentiment", ""),
        sentiment_score=doc.get("sentiment_score"),
        key_points=doc.get("key_points", []),
        confidence=doc.get("confidence"),
        stages=doc.get("stages"),
        sources=[
            NewsItemResponse(
                url=s.get("url", ""),
                title=s.get("title", ""),
                source_site=s.get("source_site", ""),
                published_at=s.get("published_at"),
                summary=s.get("summary", ""),
            )
            for s in doc.get("sources", [])
        ],
        created_at=doc.get("created_at"),
    )
