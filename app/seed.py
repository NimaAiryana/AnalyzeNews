"""Idempotent seeding of a few default symbols on first boot."""

import logging

from app.db.mongodb import SYMBOLS, get_db
from app.services.symbol_service import add_symbol
from app.services.symbol_service import SymbolAlreadyExistsError

logger = logging.getLogger(__name__)

_DEFAULTS = [
    {"symbol": "BTC", "name": "Bitcoin", "aliases": ["bitcoin", "btc", "xbt"]},
    {"symbol": "ETH", "name": "Ethereum", "aliases": ["ethereum", "eth", "ether"]},
]


async def seed_default_symbols() -> None:
    # 🌱 Only seed when the collection is empty to avoid clobbering user edits
    count = await get_db()[SYMBOLS].count_documents({})
    if count > 0:
        return
    for item in _DEFAULTS:
        try:
            await add_symbol(item["symbol"], item["name"], item["aliases"])
            logger.info("Seeded default symbol %s", item["symbol"])
        except SymbolAlreadyExistsError:
            continue
