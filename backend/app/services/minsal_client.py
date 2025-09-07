import os, asyncio, httpx
from typing import List, Dict, Optional

BASE = "https://midas.minsal.cl/farmacia_v2/WS"
VERIFY_SSL = os.getenv("MINSAL_VERIFY_SSL", "true").lower() not in ("0", "false", "no")

DEFAULT_TIMEOUT = 12.0
RETRIES = 3
RETRY_DELAY = 0.8


async def _fetch_json(url: str) -> Optional[list]:
    for attempt in range(1, RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=VERIFY_SSL) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    for k in ("locales", "datos", "data", "result"):
                        v = data.get(k)
                        if isinstance(v, list):
                            return v
                return []
        except Exception as e:
            print(f"[MINSAL] intento {attempt} {url} -> {type(e).__name__}: {e}")
            if attempt < RETRIES:
                await asyncio.sleep(RETRY_DELAY)
    return None


async def get_locales_turno() -> List[Dict]:
    """Farmacias de turno (hoy, a nivel país)."""
    url = f"{BASE}/getLocalesTurnos.php"
    data = await _fetch_json(url)
    print(f"[MINSAL] turnos recibidos: {len(data) if data else 0}")
    return data or []


async def get_locales_all() -> List[Dict]:
    """Catálogo completo de locales (no sólo turno)."""
    url = f"{BASE}/getLocales.php"
    data = await _fetch_json(url)
    print(f"[MINSAL] locales recibidos: {len(data) if data else 0}")
    return data or []


async def get_turnos_por_comuna_hoy() -> List[Dict]:
    return await get_locales_turno()

async def get_turnos_hoy() -> List[Dict]:
    return await get_locales_turno()

async def get_locales() -> List[Dict]:
    return await get_locales_all()

async def get_locales_cercanos() -> List[Dict]:
    return await get_locales_all()


__all__ = [
    "get_locales_turno",
    "get_locales_all",
    "get_turnos_por_comuna_hoy",
    "get_turnos_hoy",
    "get_locales",
    "get_locales_cercanos",
]
