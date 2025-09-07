# Farmacias & Vademécum AI (FastAPI + RAG)

Proyecto de referencia para un asistente conversacional que:
- Encuentra **farmacias de turno cercanas** usando coordenadas del usuario y API pública del MINSAL.
- Responde **consultas de medicamentos** en modo informativo (vademécum) usando **RAG con Qdrant**.
- Mantiene **historial por usuario** en Redis y traza con **LangSmith**.
- Expone un **frontend web-mobile** simple (HTML/JS) servido por FastAPI.

## Requisitos
- Python 3.12
- (Opcional) Docker / Docker Compose
- OpenAI API key

## Variables de entorno
Copia `.env.example` a `.env` y completa tu configuración:
```bash
cp .env.example .env
```

## Ejecutar local (sin Docker)
```bash
cd backend
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/Mac:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Abre: http://localhost:8000  (frontend)  
Docs API: http://localhost:8000/docs

## Ingesta de Vademécum (Qdrant)
1) Prepara el CSV con columnas sugeridas: `name, generic_name, indications, side_effects, contraindications, dosage`.
2) Con Qdrant corriendo (docker compose o local), ejecuta:
```bash
cd backend
python ingestion/ingest_vademecum.py ../data/sample_vademecum.csv
```

## Docker Compose (stack completo)
```bash
docker compose up --build
```
- API: http://localhost:8000  
- Redis: 6379  
- Qdrant: 6333 (UI opcional con `qdrant-ui`)

## Notas
- Este proyecto retorna información **descriptiva** de medicamentos (para qué sirve, efectos, contraindicaciones). **No** entrega **dosis** ni recomendaciones de tratamiento. Ante emergencias llama al 131.
- La API pública del MINSAL puede cambiar o tener límites; aquí se implementa un cliente simple con caché en Redis.
