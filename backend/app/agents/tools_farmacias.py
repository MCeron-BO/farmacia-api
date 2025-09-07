import math
from typing import List, Dict, Tuple
from app.services.minsal_client import get_locales_turno, get_locales_all

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1); dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return round(R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))), 2)

def _is_pharmacy_only(name: str) -> bool:
    if not name: return False
    u = name.upper()
    excl = ("VETERINARIA","CLÍNICA","CLINICA","HOSPITAL","CONSULTORIO","CENTRO MÉDICO","CENTRO MEDICO","CESFAM","SAPU")
    if any(bad in u for bad in excl): return False
    return ("FARMAC" in u) or ("SIMI" in u) or ("CRUZ VERDE" in u) or ("SALCO" in u) or ("AHUMADA" in u)

def _parse_intent(text: str) -> str:
    q = (text or "").lower()
    if "turno" in q or "guardia" in q or "24" in q:
        return "turno"
    if any(k in q for k in ("todas","toda","cerca","cercanas","farmacias","alrededor","cercanía","cercania")):
        return "todas"
    return "turno"

def _to_float(x) -> float | None:
    try:
        return float(x)
    except Exception:
        return None

async def find_open_pharmacies(state: dict):
    q = (state.get("input") or "").strip()
    lat = state.get("lat"); lon = state.get("lon")

    intent = _parse_intent(q)
    if intent == "turno":
        raw = await get_locales_turno()
        explanation = "Estas son las farmacias de turno cercanas (una por comuna para hoy)."
    else:
        raw = await get_locales_all()
        explanation = "Estas son algunas farmacias cercanas."

    pts: List[Dict] = []
    for it in raw or []:
        name = (it.get("local_nombre") or it.get("local") or "").strip()
        if not _is_pharmacy_only(name): continue

        plat = _to_float(it.get("local_lat")) or _to_float(it.get("lat"))
        plon = _to_float(it.get("local_lng")) or _to_float(it.get("lng")) or _to_float(it.get("long"))
        if plat is None or plon is None: continue

        dist = _haversine_km(lat or -33.45, lon or -70.66, plat, plon)
        it2 = {
            "local_nombre": name,
            "comuna_nombre": (it.get("comuna_nombre") or it.get("comuna") or "").strip(),
            "lat": plat,
            "long": plon,
            "direccion": (it.get("local_direccion") or it.get("direccion") or "").strip(),
            "telefono": (it.get("local_telefono") or it.get("telefono") or "").strip(),
            "dist_km": dist,
        }
        pts.append(it2)

    pts.sort(key=lambda x: x["dist_km"])

    if intent == "turno":
        by_comuna: Dict[str, Dict] = {}
        for p in pts:
            c = p["comuna_nombre"] or "DESCONOCIDA"
            if c not in by_comuna:
                by_comuna[c] = p
        markers = list(by_comuna.values())
        markers.sort(key=lambda x: x["dist_km"])
        markers = markers[:10]
    else:
        markers = pts[:25]

    state["output"] = explanation
    state["data"] = {
        "pharmacies": markers,
        "pharmacy_mode": intent,
        "ctas": [
            {"label": "Usar mi ubicación", "type": "use_location"},
            {"label": "Abrir mapa", "type": "open_map", "payload": {"mode": intent}},
        ]
    }
    return state
