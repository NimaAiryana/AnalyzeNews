"""Async MongoDB connection manager and index setup."""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---- Collection names (single source of truth) ----
SYMBOLS = "symbols"
NEWS = "news"
ANALYSES = "analyses"
JOBS = "jobs"


class _MongoManager:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


mongo = _MongoManager()


async def connect_to_mongo() -> None:
    """🗄️ Establish the Motor client, verify connectivity, and ensure indexes."""
    settings = get_settings()
    mongo.client = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    mongo.db = mongo.client[settings.mongo_db_name]
    await mongo.client.admin.command("ping")
    await _ensure_indexes()
    logger.info("Connected to MongoDB '%s' at %s", settings.mongo_db_name, settings.mongo_uri)


async def close_mongo_connection() -> None:
    if mongo.client is not None:
        mongo.client.close()
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    if mongo.db is None:
        raise RuntimeError("MongoDB is not initialised. Call connect_to_mongo() first.")
    return mongo.db


async def _ensure_indexes() -> None:
    db = get_db()
    # ✅ Unique symbol acts as the dynamic 'enum' of accepted coins
    await db[SYMBOLS].create_index("symbol", unique=True)
    # ✅ url_hash is the dedup key so the same article is never stored twice
    await db[NEWS].create_index("url_hash", unique=True)
    await db[NEWS].create_index([("symbols", 1), ("published_at", -1)])
    await db[NEWS].create_index("source_site")
    await db[ANALYSES].create_index([("symbol", 1), ("created_at", -1)])
    await db[JOBS].create_index("created_at")
    await db[JOBS].create_index([("symbol", 1), ("status", 1)])
