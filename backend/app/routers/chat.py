from __future__ import annotations

from fastapi import APIRouter, Depends
from app.models.schemas import ChatRequest, ChatResponse
from app.deps import get_user, get_graph, get_memory, get_retriever

router = APIRouter()


@router.post("/ask", response_model=ChatResponse)
async def ask(
    payload: ChatRequest,
    user=Depends(get_user),
    graph=Depends(get_graph),
    mem=Depends(get_memory),
    retriever=Depends(get_retriever),
):
    """
    Orquesta una vuelta de conversación con el grafo.
    - Carga y guarda historial en la memoria
    - Intenta deducir last_drug cuando no viene del cliente
    - Pasa lat/lon si el cliente las envió
    - Devuelve reply + data (ctas, pharmacies, last_drug, etc.)
    """
    user_id = user.get("id")
    user_tz = user.get("tz") or "America/Santiago"
    user_name = user.get("name") or None

    # 1) Historial del usuario
    try:
        history = mem.load(user_id)
    except Exception:
        history = []

    # 2) Preferir last_drug enviado por el cliente; si no, inferir rápido con el retriever
    last_drug = (payload.last_drug or "").strip()
    if not last_drug:
        try:
            last_drug = retriever.extract_name_from_text(payload.message) or ""
        except Exception:
            last_drug = ""

    # 3) Estado inicial para el grafo
    state = {
        "input": (payload.message or "").strip(),
        "history": history,
        "user": user,
        "retriever": retriever,
        "last_drug": last_drug,
        "user_tz": user_tz,
        "user_name": user_name,
    }
    if payload.lat is not None and payload.lon is not None:
        state["lat"] = payload.lat
        state["lon"] = payload.lon

    # 4) Ejecutar grafo
    try:
        result = await graph.ainvoke(state)
    except Exception as e:
        # Fallback seguro si algo truena dentro del grafo
        reply = "Ocurrió un error inesperado. ¿Puedes intentar reformular tu consulta?"
        data = {"error": str(e)}
        print(data)
        try:
            mem.save(user_id, history + [(payload.message, reply)])
        except Exception:
            pass
        return ChatResponse(reply=reply, data=data)

    reply = (result.get("output") or "").strip()

    # 5) Guardar historial (no romper si falla la memoria)
    try:
        mem.save(user_id, history + [(payload.message, reply)])
    except Exception:
        pass

    # 6) Preparar data de salida y consolidar last_drug
    data = result.get("data") or {}
    match = data.get("match") or {}

    # Consolidación: considerar cualquier campo por donde pueda venir
    last_drug_out = (
        result.get("updated_last_drug")  # ← si el grafo lo actualiza explícitamente
        or result.get("last_drug")
        or data.get("last_drug")
        or match.get("name_es")
        or match.get("generic_name_es")
        or match.get("name")
        or (last_drug if last_drug else None)
    )
    if last_drug_out:
        data["last_drug"] = last_drug_out

    # 7) Responder
    return ChatResponse(reply=reply, data=data)
