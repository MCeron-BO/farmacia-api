from fastapi import APIRouter, Query
from typing import List, Dict, Optional
import math

from app.services.minsal_client import (
    get_locales_all,
    get_locales_turno,
)

router = APIRouter()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def _parse_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        try:
            s = str(v).replace(",", ".")
            return float(s)
        except Exception:
            return None


def _with_distance(items: List[Dict], lat: float, lon: float) -> List[Dict]:
    out = []
    for x in items:
        la = (
            _parse_float(x.get("lat"))
            or _parse_float(x.get("local_lat"))
        )
        lo = (
            _parse_float(x.get("long"))
            or _parse_float(x.get("lng"))
            or _parse_float(x.get("lon"))
            or _parse_float(x.get("local_lng"))
        )
        if la is None or lo is None:
            continue
        xx = dict(x)
        xx["lat"] = la
        xx["long"] = lo
        xx["dist_km"] = _haversine_km(lat, lon, la, lo)
        out.append(xx)
    out.sort(key=lambda r: r.get("dist_km", 9999))
    return out


def _dedup_by_comuna(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for x in items:
        comuna = (x.get("comuna_nombre") or x.get("comuna") or "").strip().lower()
        if not comuna:
            continue
        if comuna in seen:
            continue
        seen.add(comuna)
        out.append(x)
    return out


@router.get("/cercanas")
async def farmacias_cercanas(lat: float = Query(...), lon: float = Query(...), limit: int = 10):
    """
    Farmacias cercanas (no necesariamente de turno).
    """
    data = await get_locales_all()
    items = _with_distance(data, lat, lon)[: max(1, limit)]
    return {"pharmacies": items}


@router.get("/turno")
async def farmacias_turno(lat: float = Query(...), lon: float = Query(...), per_comuna: bool = True, limit: int = 10):
    """
    Farmacias de turno para hoy; por defecto 1 por comuna (la más cercana).
    """
    turnos = await get_locales_turno()
    items = _with_distance(turnos, lat, lon)
    if per_comuna:
        items = _dedup_by_comuna(items)
    return {"pharmacies": items[: max(1, limit)]}
