from fastapi import APIRouter
from app.models.schemas import LoginRequest, TokenPair
from app.auth.jwt import create_access_token, create_refresh_token

router = APIRouter()

@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest):
    # Demo: no validamos contra DB; en prod reemplazar.
    user_id = payload.username
    return TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
