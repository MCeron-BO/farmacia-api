# backend/app/agents/graph.py
import os
import re
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from app.agents.tools_farmacias import find_open_pharmacies
from app.agents.tools_vademecum import search_vademecum
from app.config import settings


def build_agent():
    _llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)

    graph = StateGraph(dict)

    # --------------------------- SAFETY / POLICY GUARD ---------------------------------
    SUICIDE_PATTERNS = [
            r"\b(suicid(ar|arme|arte|arnos|arse)|quitarme la vida|quitarse la vida|"
            r"matarme|matarse|matar|no quiero vivir|perdi la fe|"
            r"autolesi[oó]n|autolesion|cortarme|cortarse|hacerme daño|hacerse daño|"
            r"me voy a morir|quiero morir|dañarme)\b"
        ]
    
    CATASTROPHIC_PATTERNS = [
            r"\b(atentado|bomba|explosión|explosion|terrorista|terrorismo|amenaza)|"
            r"\b(incend(io|iarla|iar|iaria)|"
            r"homicidio|asesinato|matar[aá]|masacre|"
            r"terremoto|tsunami|maremoto|temblor|sismo|"
            r"alud|aluvi[oó]n|inundaci[oó]n|cat[aá]strofe|desastre|"
            r"emergencia|evacuaci[oó]n|p[aá]nico|caos)\b"
        ]
    
    DOSIS_PATTERNS = [
            r"\bdosis\b", r"\bcu[aá]nt[oa]s?\s+(tomo|debo tomar|puedo tomar)\b",
            r"\bmg\b", r"\bmiligramos?\b", r"\bposolog[ií]a\b",
            r"\brec[eé]t(a|ario|a(r|s)?)\b", r"\bprescripci[oó]n\b",
            r"\bpuedo tomar\b", r"\bpodr[ií]a tomar\b"
        ]

    def policy_guard(s: dict) -> dict:
        msg = (s.get("input") or "").lower()

        # 1) Señales de autolesión/suicidio -> salida inmediata con tono empático
        if any(re.search(p, msg) for p in SUICIDE_PATTERNS):
            s["output"] = (
                "Siento mucho que estés pasando por esto, la vida puede ser muy difícil a veces, "
                "pero no estás solo/a: hablar con alguien ahora puede marcar una gran diferencia.\n\n"
                "En Chile, puedes llamar gratis y de forma confidencial al ✱4141 (Salud Responde Salud Mental). "
                "Si hay riesgo inmediato, llama al 131 (SAMU) o dirígete a Urgencias.\n\n"
            )
            s["data"] = {
                **(s.get("data") or {}),
                "ctas": [
                    # Importante: mantener el asterisco
                    {"label": "📞 Llamar ✱4141 (Salud Mental)", "type": "telemed", "url": "tel:*4141"},
                    {"label": "🚑 Llamar 131 (SAMU)", "type": "telemed", "url": "tel:131"}
                ],
                "blocked": True,
            }
            s["__early_exit"] = True
            return s

        # 2) Señales de catástrofe/atentado -> salida inmediata con tono serio
        if any(re.search(p, msg) for p in CATASTROPHIC_PATTERNS):
            s["output"] = (
                "Lamentablemente, no puedo ayudar con eso. Te recomiendo que hables con un profesional de salud mental."
            )
            s["data"] = {
                **(s.get("data") or {}),
                "ctas": [
                    {"label": "📞 Llamar ✱4141 (Salud Mental)", "type": "telemed", "url": "tel:*4141"},
                    {"label": "🚑 Llamar 131 (SAMU)", "type": "telemed", "url": "tel:131"}
                ],
                "blocked": True,
            }
            s["__early_exit"] = True
            return s
            
        # 3) Pedidos de dosis / prescripción -> respuesta segura y salida
        if any(re.search(p, msg) for p in DOSIS_PATTERNS):
            s["output"] = (
                "Puedo ofrecer información descriptiva del vademécum, pero NO puedo recomendar tratamientos ni dosis. "
                "Para indicaciones personalizadas consulta con un profesional de salud o Urgencias (131)."
            )
            s["__early_exit"] = True
            return s

        return s

    # --------------------------- ROUTER ---------------------------------
    def _contains_care_query(msg: str) -> bool:
        care_words = [
            "receta", "hospital", "clinica", "clínica", "centro medico", "centro de salud",
            "centro atencion", "centro atención", "urgencia", "urgencias", "doctor", "médico", "medico"
        ]
        m = msg.lower()
        return any(w in m for w in care_words)

    def _is_pharmacy_query(msg: str) -> bool:
        m = msg.lower()
        has_farmacia = "farmacia" in m or "farmacias" in m
        mentions_turno = ("turno" in m) or ("guardia" in m) or ("24h" in m) or ("24 h" in m) or ("24 horas" in m)
        if has_farmacia and mentions_turno:
            return True
        if has_farmacia:
            return True
        if mentions_turno and not _contains_care_query(m):
            return True
        return False

    def router(s: dict) -> str:
        if s.get("__early_exit"):
            return "END"
        msg = (s.get("input") or "")
        if _is_pharmacy_query(msg):
            return "farmacias"
        return "meds"

    # --------------------------- GRAPH NODES ---------------------------------
    graph.add_node("guard", policy_guard)
    graph.add_node("farmacias", find_open_pharmacies)
    graph.add_node("meds", search_vademecum)

    def route_node(s: dict) -> dict:
        return s
    graph.add_node("route", route_node)

    graph.set_entry_point("guard")

    graph.add_conditional_edges(
        "guard",
        lambda s: "END" if s.get("__early_exit") else "route",
        {"END": END, "route": "route"},
    )

    graph.add_conditional_edges(
        "route",
        router,
        {"farmacias": "farmacias", "meds": "meds", "END": END},
    )

    graph.add_edge("farmacias", END)
    graph.add_edge("meds", END)

    return graph.compile()
