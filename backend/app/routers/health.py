# app/routers/health.py
from fastapi import APIRouter
from app.services.minsal_client import (
    get_turnos_por_comuna_hoy,
    get_locales_cercanos,
)

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health_root():
    return {"status": "ok"}

@router.get("/minsal/turnos")
async def health_minsal_turnos():
    """
    Chequeo simple: intenta obtener 1 por comuna (hoy).
    No requiere lat/lon; solo valida que el servicio responda.
    """
    turnos = await get_turnos_por_comuna_hoy(user_lat=None, user_lon=None)
    return {"ok": True, "count": len(turnos)}

@router.get("/minsal/cercanas")
async def health_minsal_cercanas():
    """
    Chequeo simple para 'todas las cercanas': usa una ubicación fija (Santiago Centro).
    """
    sample_lat, sample_lon = -33.45, -70.66
    cercanas = await get_locales_cercanos(user_lat=sample_lat, user_lon=sample_lon, radius_km=3.0, limit=5)
    return {"ok": True, "count": len(cercanas)}
