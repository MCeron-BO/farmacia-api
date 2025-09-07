import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY","")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL","gpt-4o-mini")
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY","")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT","farmacias-ai")

    REDIS_URL: str = os.getenv("REDIS_URL","redis://localhost:6379/0")
    QDRANT_URL: str = os.getenv("QDRANT_URL","http://localhost:6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY","")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION","vademecum_es")

    JWT_SECRET: str = os.getenv("JWT_SECRET","change_me")
    JWT_ALG: str = os.getenv("JWT_ALG","HS256")
    JWT_EXPIRES_MIN: int = int(os.getenv("JWT_EXPIRES_MIN","60"))
    JWT_REFRESH_EXPIRES_DAYS: int = int(os.getenv("JWT_REFRESH_EXPIRES_DAYS","15"))

    APP_ENV: str = os.getenv("APP_ENV","dev")
    TZ: str = os.getenv("TZ","America/Santiago")

settings = Settings()
