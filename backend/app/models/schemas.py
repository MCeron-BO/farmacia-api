from pydantic import BaseModel, Field
from typing import Optional, List, Any

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class ChatRequest(BaseModel):
    message: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    last_drug: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    data: Optional[dict[str, Any]] = None
