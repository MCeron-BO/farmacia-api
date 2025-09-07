from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from app.config import settings

router = APIRouter()

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
embedder = SentenceTransformer(EMBED_MODEL)
client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

def ensure_collection():
    if not client.collection_exists(settings.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=qm.VectorParams(size=384, distance=qm.Distance.COSINE)
        )

@router.post("/medicamentos/upsert")
def upsert_items(items: List[Dict[str, Any]]):
    ensure_collection()
    points = []
    for i, doc in enumerate(items):
        text = " | ".join(filter(None, [
            doc.get("name"),
            doc.get("generic_name"),
            doc.get("indications"),
            doc.get("side_effects"),
            doc.get("contraindications"),
        ]))
        vec = embedder.encode(text).tolist()
        points.append(qm.PointStruct(id=doc.get("id", i), vector=vec, payload={**doc, "text": text}))
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return {"upserted": len(points)}
