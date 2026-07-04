"""Symbol management: the dynamic 'enum' of coins the engine accepts."""

import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.db.mongodb import SYMBOLS, get_db
from app.models.domain import SymbolQuery

logger = logging.getLogger(__name__)


class SymbolNotFoundError(Exception):
    pass


class SymbolAlreadyExistsError(Exception):
    pass


async def add_symbol(symbol: str, name: str, aliases: list[str], enabled: bool = True) -> dict:
    doc = {
        "symbol": symbol.upper(),
        "name": name,
        "aliases": [a.strip() for a in aliases if a.strip()],
        "enabled": enabled,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await get_db()[SYMBOLS].insert_one(doc)
    except DuplicateKeyError as exc:
        raise SymbolAlreadyExistsError(symbol) from exc
    return doc


async def list_symbols() -> list[dict]:
    cursor = get_db()[SYMBOLS].find().sort("symbol", 1)
    return [doc async for doc in cursor]


async def get_symbol(symbol: str) -> dict:
    doc = await get_db()[SYMBOLS].find_one({"symbol": symbol.upper()})
    if not doc:
        raise SymbolNotFoundError(symbol)
    return doc


async def update_symbol(symbol: str, updates: dict) -> dict:
    clean = {k: v for k, v in updates.items() if v is not None}
    if not clean:
        return await get_symbol(symbol)
    result = await get_db()[SYMBOLS].find_one_and_update(
        {"symbol": symbol.upper()},
        {"$set": clean},
        return_document=True,
    )
    if not result:
        raise SymbolNotFoundError(symbol)
    return result


async def delete_symbol(symbol: str) -> None:
    result = await get_db()[SYMBOLS].delete_one({"symbol": symbol.upper()})
    if result.deleted_count == 0:
        raise SymbolNotFoundError(symbol)


async def get_symbol_query(symbol: str) -> SymbolQuery:
    """✅ Resolve a stored, enabled symbol into a SymbolQuery for crawling."""
    doc = await get_symbol(symbol)
    if not doc.get("enabled", True):
        raise SymbolNotFoundError(f"{symbol} (disabled)")
    return SymbolQuery(
        symbol=doc["symbol"],
        name=doc["name"],
        aliases=doc.get("aliases", []),
    )
