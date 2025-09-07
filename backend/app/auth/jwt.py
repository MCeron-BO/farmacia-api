from datetime import datetime, timedelta, timezone
from jose import jwt
from app.config import settings

def create_access_token(subject: str, expires_minutes: int | None = None):
    if expires_minutes is None:
        expires_minutes = settings.JWT_EXPIRES_MIN
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def create_refresh_token(subject: str):
    expire = datetime.now(tz=timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRES_DAYS)
    to_encode = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
