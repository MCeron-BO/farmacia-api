from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routers import farmacias, medicamentos, chat
from app.routers.admin_vademecum import router as admin_vademecum_router
from app.auth.router import router as auth_router
from app.config import settings
from app.routers.health import router as health_router
from app.routers.graph_view import router as graph_view_router

app = FastAPI(title="Farmacias & Vademécum AI")

# CORS — ajusta dominios en producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en prod: ["https://tu-dominio.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers de API
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(farmacias.router, prefix="/farmacias", tags=["farmacias"])
app.include_router(medicamentos.router, prefix="/medicamentos", tags=["medicamentos"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(admin_vademecum_router, tags=["admin"])
app.include_router(health_router, prefix="/debug", tags=["debug"])
app.include_router(graph_view_router)

# Frontend estático (sirve / -> index.html)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
