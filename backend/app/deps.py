from fastapi import Depends
from app.services.redis_mem import RedisMemory
from app.services.vademecum_retriever import VademecumRetriever
from app.config import settings
from app.agents.graph import build_agent
import redis

_redis = None
_graph = None
_retriever = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def get_memory(r: redis.Redis = Depends(get_redis)) -> RedisMemory:
    return RedisMemory(r)


def get_retriever() -> VademecumRetriever:
    global _retriever
    if _retriever is None:
        _retriever = VademecumRetriever(
            url=settings.QDRANT_URL,
            coll=settings.QDRANT_COLLECTION,
            api_key=settings.QDRANT_API_KEY,
        )
    return _retriever


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_agent()
    return _graph


def get_user(token: str | None = None):
    # Demo: usuario anónimo si no hay auth (puedes forzar JWT en producción)
    return {"id": "anon", "name": "Anon"}
