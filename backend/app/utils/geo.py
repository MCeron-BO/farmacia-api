# backend/app/utils/geo.py

from typing import Any, Dict, Iterable, List, Optional, Tuple
from haversine import haversine

LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)


def _to_float(v: Any) -> Optional[float]:
    """
    Convierte a float admitiendo:
    - int/float
    - strings con coma o punto decimal, con espacios.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def is_valid_coord(lat: Optional[float], lon: Optional[float]) -> bool:
    """Valida rango lat/lon."""
    if lat is None or lon is None:
        return False
    return (LAT_RANGE[0] <= lat <= LAT_RANGE[1]) and (LON_RANGE[0] <= lon <= LON_RANGE[1])


def normalize_coords(
    lat: Any, lon: Any, ndigits: int = 6
) -> Tuple[Optional[float], Optional[float]]:
    """
    Convierte y redondea; devuelve (None, None) si no son válidas.
    """
    _lat = _to_float(lat)
    _lon = _to_float(lon)
    if not is_valid_coord(_lat, _lon):
        return None, None
    return round(_lat, ndigits), round(_lon, ndigits)


def extract_coords(item: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """
    Intenta distintos nombres comunes del MINSAL / datasets:
      - lat / long
      - latitude / longitude
      - latitud / longitud
      - local_lat / local_lng / local_longitud
    Retorna (lat, lon) normalizados o (None, None).
    """
    lat_keys = ["lat", "latitude", "latitud", "local_lat", "local_latitud"]
    lon_keys = ["long", "lng", "longitude", "longitud", "local_lng", "local_longitud"]

    lat = None
    lon = None

    for k in lat_keys:
        if k in item and item[k] not in (None, ""):
            lat = _to_float(item[k])
            break
    for k in lon_keys:
        if k in item and item[k] not in (None, ""):
            lon = _to_float(item[k])
            break

    return normalize_coords(lat, lon)


def geodesic_distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Distancia geodésica en km (haversine)."""
    return float(haversine((a_lat, a_lon), (b_lat, b_lon)))


def attach_distance(
    items: Iterable[Dict[str, Any]],
    user_lat: float,
    user_lon: float,
    *,
    distance_key: str = "dist_km",
    limit: Optional[int] = None,
    radius_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Adjunta distancia en km a cada item que tenga coordenadas válidas.
    - Ordena por distancia ascendente.
    - Si radius_km se entrega, filtra por ese radio.
    - Si limit se entrega, corta la lista.

    Devuelve una NUEVA lista (no modifica los items originales).
    """
    out: List[Dict[str, Any]] = []
    for it in items:
        lat, lon = extract_coords(it)
        if lat is None or lon is None:
            continue
        d = geodesic_distance_km(user_lat, user_lon, lat, lon)
        if radius_km is not None and d > radius_km:
            continue
        rec = dict(it)
        rec["lat"] = lat
        rec["long"] = lon
        rec[distance_key] = round(d, 3)
        out.append(rec)

    out.sort(key=lambda r: r[distance_key])
    if limit is not None and limit > 0:
        out = out[:limit]
    return out


# Alias para compatibilidad con código existente
def nearest_by_coords(items: Iterable[Dict[str, Any]], user_lat: float, user_lon: float, limit: int = 10):
    """
    Versión clásica: top-N más cercanos.
    """
    return attach_distance(items, user_lat, user_lon, limit=limit)
