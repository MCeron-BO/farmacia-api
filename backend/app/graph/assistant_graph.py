# app/graph/assistant_graph.py

from __future__ import annotations
from typing import TypedDict, Optional, Literal, Dict, Any
import re

from langgraph.graph import StateGraph, END
from langgraph.checkpoint import MemorySaver

# Tools propios
from app.agents.tools_vademecum import search_vademecum
from app.agents.tools_farmacias import find_open_pharmacies


# ========= 1) Estado compartido =========
class AssistantState(TypedDict, total=False):
    # entrada
    input: str
    lat: Optional[float]
    lon: Optional[float]
    user_tz: Optional[str]
    user_name: Optional[str]
    last_drug: Optional[str]

    # control
    intent: Optional[Literal["pharmacy", "vademecum", "smalltalk", "unknown"]]
    pharmacy_mode: Optional[Literal["turno", "todas", "cercanas"]]

    # salida
    output: Optional[str]
    data: Optional[Dict[str, Any]]

    # efectos laterales
    updated_last_drug: Optional[str]


# ========= 2) SAFETY GUARD (antes que todo) =========
_DOSE_RE = re.compile(
    r"\b(dosis|cu[aá]nt[oa]s?|cada cu[aá]nt[oa]s?|mg\b|miligramos|tomas?|posolog|posolog[ií]a|"
    r"puedo tomar|deber[ií]a tomar|cu[aá]nto debo)\b",
    re.I,
)

_CRISIS_RE = re.compile(
    r"(suicid|quitarme la vida|matarme|no quiero vivir|autolesi[oó]n|hacerme da[nñ]o|"
    r"herirme|cortarme|me quiero morir)",
    re.I,
)

def safety_guard(state: AssistantState) -> AssistantState:
    msg = (state.get("input") or "").strip()

    # 1) Crisis / autolesión
    if _CRISIS_RE.search(msg):
        state["output"] = (
            "Siento mucho lo que estás pasando. No estás solo/a. "
            "Si estás en Chile y piensas en hacerte daño, por favor busca ayuda ahora mismo:\n\n"
            "• **✱4141** (línea de ayuda en crisis y prevención del suicidio)\n"
            "• **131** (SAMU – Emergencias de salud)\n\n"
            "Si puedes, comunícate con alguien de confianza o un profesional. Estoy aquí para escucharte."
        )
        # CTAs telefónicas (el front puede abrir tel: si quiere)
        state["data"] = {
            "ctas": [
                {"type": "tel", "label": "Llamar ✱4141", "value": "*4141"},
                {"type": "tel", "label": "Llamar 131", "value": "131"},
            ]
        }
        # Cortamos el flujo aquí
        return state

    # 2) Dosis/prescripción
    if _DOSE_RE.search(msg):
        state["output"] = (
            "Puedo ofrecer información descriptiva del vademécum, pero **no** puedo indicar dosis, "
            "tratamientos ni ajustar medicación. Para una indicación segura, consulta a un profesional "
            "de salud o Urgencias (131)."
        )
        return state

    # Si no activó safety, seguimos el flujo normal
    return state


# ========= 3) Clasificador determinista =========
_PHARMACY_RE = re.compile(r"\bfarmacia(s)?\b|\bde\s+turno\b|\bguardia\b|24\s*h", re.I)
_VADEMECUM_HINTS = re.compile(
    r"para\s+que\s+sirve|efecto|efectos|contraindic|interacc|advertenc|posolog|mecanism",
    re.I,
)
_SMALLTALK_HELLO = re.compile(r"^\s*(hola|hello|hi|qué tal|que tal)\b", re.I)
_SMALLTALK_THANKS = re.compile(r"\bgracias\b|\bmuchas gracias\b|\bse agradece\b|\bvale\b|\bgraci[a|e]s\b", re.I)
_SMALLTALK_BYE = re.compile(r"\bchao\b|\bchau\b|\badios\b|\badiós\b|\bhasta luego\b|\bbye\b", re.I)

def classify(state: AssistantState) -> AssistantState:
    q = (state.get("input") or "").strip()

    if _PHARMACY_RE.search(q):
        state["pharmacy_mode"] = "turno" if re.search(r"\bturno\b|guardia|24\s*h", q, re.I) else "cercanas"
        state["intent"] = "pharmacy"
        return state

    if _VADEMECUM_HINTS.search(q):
        state["intent"] = "vademecum"
        return state

    if _SMALLTALK_HELLO.search(q) or _SMALLTALK_THANKS.search(q) or _SMALLTALK_BYE.search(q):
        state["intent"] = "smalltalk"
        return state

    state["intent"] = "unknown"
    return state


# ========= 4) Ubicación requerida para farmacias =========
def need_location(state: AssistantState) -> AssistantState:
    if state.get("lat") is None or state.get("lon") is None:
        state["output"] = "Para mostrar farmacias cercanas o de turno necesito tu ubicación."
        state["data"] = {
            "ctas": [{"type": "use_location", "label": "Usar mi ubicación"}]
        }
    return state


# ========= 5) Nodos que invocan tus tools =========
async def node_pharmacies(state: AssistantState) -> AssistantState:
    # find_open_pharmacies usa: input/lat/lon
    return await find_open_pharmacies(dict(state))

async def node_vademecum(state: AssistantState) -> AssistantState:
    # search_vademecum maneja smalltalk y seguimiento de last_drug
    return await search_vademecum(dict(state))

async def node_smalltalk(state: AssistantState) -> AssistantState:
    # Reutilizamos el smalltalk que ya implementaste dentro del vademécum
    return await search_vademecum(dict(state))

def node_fallback(state: AssistantState) -> AssistantState:
    q = (state.get("input") or "").strip()
    state["output"] = (
        f"No puedo ayudarte con tu duda: “{q}”. "
        "Puedo responder sobre medicamentos (p. ej. “¿Para qué sirve la aspirina?”) "
        "o mostrar 'farmacias cercanas' y de 'turno'. "
        "Si quieres, pregúntame por un medicamento o pídeme ver farmacias cerca de ti 🙂."
    )
    state["data"] = {"offtopic": True}
    return state


# ========= 6) Persistencia simple de last_drug =========
def persist_memory(state: AssistantState) -> AssistantState:
    last = state.get("last_drug") or (state.get("data") or {}).get("last_drug")
    if last:
        state["updated_last_drug"] = last
    return state


# ========= 7) Construcción del grafo =========
def build_graph():
    g = StateGraph(AssistantState)

    # Nodos
    g.add_node("safety", safety_guard)
    g.add_node("classify", classify)
    g.add_node("need_location", need_location)
    g.add_node("pharmacies", node_pharmacies)
    g.add_node("vademecum", node_vademecum)
    g.add_node("smalltalk", node_smalltalk)
    g.add_node("fallback", node_fallback)
    g.add_node("persist_memory", persist_memory)

    # Entry
    g.set_entry_point("safety")

    # safety → END (si ya dio salida) o → classify
    def route_from_safety(state: AssistantState):
        return "END" if state.get("output") else "classify"

    g.add_conditional_edges("safety", route_from_safety, {"END": END, "classify": "classify"})

    # classify → ramas
    def route_from_classify(state: AssistantState):
        intent = state.get("intent")
        if intent == "pharmacy":
            return "need_location"
        if intent == "vademecum":
            return "vademecum"
        if intent == "smalltalk":
            return "smalltalk"
        return "fallback"

    g.add_conditional_edges("classify", route_from_classify)

    # farmacias
    def after_need_location(state: AssistantState):
        if state.get("output"):  # ya dejamos CTA de ubicación
            return "persist_memory"
        return "pharmacies"

    g.add_conditional_edges("need_location", after_need_location)
    g.add_edge("pharmacies", "persist_memory")

    # vademécum / smalltalk / fallback → persist
    g.add_edge("vademecum", "persist_memory")
    g.add_edge("smalltalk", "persist_memory")
    g.add_edge("fallback", "persist_memory")

    # persist → END
    g.add_edge("persist_memory", END)

    # Checkpointer en memoria
    memory = MemorySaver()
    return g.compile(checkpointer=memory)
