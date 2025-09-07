from fastapi import APIRouter, Query, Depends
from app.deps import get_retriever

router = APIRouter()

@router.get("/buscar")
def buscar_medicamento(q: str = Query(...), retriever = Depends(get_retriever)):
    hits = retriever.search(q, k=5)
    return {"query": q, "hits": hits}
