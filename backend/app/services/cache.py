import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class MemoryCache:
    def __init__(self):
        self._data: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, value)


class MongoCache:
    def __init__(self, uri: str, db_name: str, collection: str = "api_cache"):
        self._client = AsyncMongoClient(uri, serverSelectionTimeoutMS=3000)
        self._collection = self._client[db_name][collection]
        self._fallback = MemoryCache()
        self._ready = False

    async def _ensure_index(self) -> None:
        if not self._ready:
            await self._collection.create_index("expires_at", expireAfterSeconds=0)
            self._ready = True

    async def get(self, key: str) -> Any | None:
        try:
            await self._ensure_index()
            doc = await self._collection.find_one({"_id": key})
        except PyMongoError as exc:
            logger.warning("MongoDB indisponible, cache mémoire utilisé : %s", exc)
            return await self._fallback.get(key)
        # L'index TTL nettoie en différé (~60 s) : on revérifie l'expiration
        if doc and doc["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None):
            return doc["value"]
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=ttl_seconds)
        try:
            await self._ensure_index()
            await self._collection.replace_one(
                {"_id": key}, {"_id": key, "value": value, "expires_at": expires_at}, upsert=True
            )
        except PyMongoError as exc:
            logger.warning("MongoDB indisponible, cache mémoire utilisé : %s", exc)
            await self._fallback.set(key, value, ttl_seconds)

    async def close(self) -> None:
        await self._client.close()
