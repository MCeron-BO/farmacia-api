# scripts/check_qdrant_env.py
import os
import httpx
import dotenv

dotenv.load_dotenv(dotenv.find_dotenv())

u = os.getenv("QDRANT_URL")
k = os.getenv("QDRANT_API_KEY")
print("ENV QDRANT_URL =", u)
print("ENV QDRANT_API_KEY set? ", bool(k))

if not u:
    print("⚠️  No hay QDRANT_URL en el entorno. Revisa tu .env o cómo cargas settings.")
else:
    base = u.rstrip("/")
    try:
        headers = {"api-key": k} if k else {}
        r = httpx.get(base + "/collections", headers=headers, timeout=5.0)
        print("GET /collections ->", r.status_code)
        print((r.text or "")[:300])
    except Exception as e:
        print("HTTPX ERROR:", type(e).__name__, e)
