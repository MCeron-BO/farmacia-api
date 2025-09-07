import json
from typing import List, Tuple
from redis.exceptions import RedisError, AuthenticationError, ConnectionError

TTL_SECONDS = 60 * 60 * 24 * 14  # 14 días


class RedisMemory:
    def __init__(self, redis_client):
        self.r = redis_client
        # Fallback en proceso por si Redis falla
        self._fallback_history = {}
        self._fallback_last_drug = {}

    # ---------- keys ----------
    def _key_history(self, user_id: str) -> str:
        return f"session:{user_id}:history"

    def _key_last_drug(self, user_id: str) -> str:
        return f"session:{user_id}:last_drug"

    # ---------- history ----------
    def load(self, user_id: str) -> List[Tuple[str, str]]:
        try:
            data = self.r.get(self._key_history(user_id))
            if not data:
                return self._fallback_history.get(user_id, [])
            return json.loads(data)
        except (RedisError, AuthenticationError, ConnectionError):
            return self._fallback_history.get(user_id, [])

    def save(self, user_id: str, history: List[tuple]):
        try:
            self.r.set(
                self._key_history(user_id),
                json.dumps(history, ensure_ascii=False),
                ex=TTL_SECONDS,
            )
        except (RedisError, AuthenticationError, ConnectionError):
            self._fallback_history[user_id] = history

    # ---------- last drug ----------
    def load_last_drug(self, user_id: str) -> str | None:
        try:
            v = self.r.get(self._key_last_drug(user_id))
            if v is None:
                return self._fallback_last_drug.get(user_id)
            return v
        except (RedisError, AuthenticationError, ConnectionError):
            return self._fallback_last_drug.get(user_id)

    def save_last_drug(self, user_id: str, drug: str | None):
        if not drug:
            return
        try:
            self.r.set(self._key_last_drug(user_id), drug, ex=TTL_SECONDS)
        except (RedisError, AuthenticationError, ConnectionError):
            self._fallback_last_drug[user_id] = drug
