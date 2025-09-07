from __future__ import annotations
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from difflib import SequenceMatcher

from app.services.vademecum_retriever import retriever_singleton

# Qdrant models (opcional, para filtros exactos)
try:
    from qdrant_client.http import models as qm
except Exception:
    qm = None

# Zona horaria (opcional)
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# LLM opcional para humanizar (no inventa; si falla, hay fallback)
try:
    from langchain_openai import ChatOpenAI
    from app.config import settings
    _LLM = ChatOpenAI(
        model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
        api_key=settings.OPENAI_API_KEY,
        temperature=0.2,
        max_tokens=220,
    )
except Exception:
    _LLM = None

DEFAULT_TZ = "America/Santiago"

# ---------------------- Etiquetas y claves por sección ----------------------
SECTION_LABEL = {
    "indicaciones": "Para qué sirve",
    "efectos_secundarios": "Efectos secundarios",
    "contraindicaciones": "Contraindicaciones",
    "interacciones": "Interacciones",
    "advertencias": "Advertencias / Precauciones",
    "posologia": "Posología (solo informativa)",
    "mecanismo": "Mecanismo de acción",
}

SECTION_KEYS: Dict[str, List[str]] = {
    "indicaciones": ["indicaciones","indications_es","indications","para_que_sirve","para_qué_sirve","descripcion","descripción","resumen","text_es","text"],
    "efectos_secundarios": ["efectos_secundarios","efectos","reacciones_adversas","reacciones adversas","adverse_reactions","adverse_reactions_es","text_es","text"],
    "contraindicaciones": ["contraindicaciones","contraindications","contraindications_es","text_es","text"],
    "interacciones": ["interacciones","interactions","interactions_es","text_es","text"],
    "advertencias": ["advertencias","precauciones","warnings_es","warnings","precautions","precautions_es","text_es","text"],
    "posologia": ["posologia","posología","dosage","dosage_es","dosing","dosis","dosificacion","dosificación","text_es","text"],
    "mecanismo": ["mecanismo","mecanismo_de_accion","mecanismo de accion","mecanismo de acción","mechanism","mechanism_of_action","mechanism of action","text_es","text"],
}
ANY_TEXT_KEYS = ["text_es", "text", "descripcion", "descripción", "resumen"]

# Secciones en inglés (datasets bilingües)
EN_SECTIONS: Dict[str, List[str]] = {
    "indicaciones": ["indications"],
    "efectos_secundarios": ["adverse_reactions", "side effects", "side_effects"],
    "contraindicaciones": ["contraindications"],
    "interacciones": ["interactions"],
    "advertencias": ["warnings", "precautions"],
    "posologia": ["dosage", "dosing", "dose"],
    "mecanismo": ["mechanism", "mechanism_of_action"],
}

# ---------------------- Intents ----------------------
def _infer_section(q: str) -> str:
    ql = (q or "").lower()
    # Contraindicaciones
    if ("contraindic" in ql or any(k in ql for k in [
        "restriccion","restricción","restricciones","limitaciones",
        "no debo","no se debe","prohibido","quien no debe","quién no debe",
        "no debo tomar","no tomar","embarazo","gestación","gestacion",
        "lactancia","alergia","alérgico","alergico","insuficiencia renal",
        "insuficiencia hepática","insuficiencia hepatica"
    ])):
        return "contraindicaciones"
    # Mecanismo
    if any(k in ql for k in ["mecanismo","cómo funciona","como funciona","mechanism"]):
        return "mecanismo"
    # Posología
    if any(k in ql for k in ["posologia","posología","dosage","dosis","dosificación","dosificacion",
                             "cada cuantas","cada cuántas","cada cuántos","cada cuantos","cada horas","cada hora"]):
        return "posologia"
    # Efectos secundarios
    if ("reacciones adversas" in ql or "reacción adversa" in ql or "reaccion adversa" in ql
        or "efectos secundarios" in ql or "efecto secundario" in ql
        or ("efecto" in ql and "secundar" in ql) or "me hace mal" in ql
        or "me hará mal" in ql or "me hara mal" in ql
        or "tiene algun efecto" in ql or "tiene algún efecto" in ql):
        return "efectos_secundarios"
    # Interacciones
    if any(k in ql for k in ["interacciones","interacción","interaccion","interacc","interact","alcohol","comida","alimentos","pomelo","toronja"]):
        return "interacciones"
    # Advertencias
    if any(k in ql for k in ["advertencias","precauciones","advertenc","precauci","alerta","cuidado","conducir","manejar"]):
        return "advertencias"
    # Por defecto
    return "indicaciones"

_SMALLTALK = {
    "thanks": [r"\bgracias\b", r"\bmuchas gracias\b", r"\bse agradece\b", r"\bte pasaste\b", r"\bvale\b", r"\bvaya genial\b", r"\bbuenisimo\b", r"\bty\b", r"\bthanks\b", r"\bbuenisimo\b", r"\bbuenisima\b"],
    "bye": [r"\bchao\b", r"\bchau\b", r"\badios\b", r"\badiós\b", r"\bhasta luego\b", r"\bnos vemos\b", r"\bhasta pronto\b", r"\bbye\b", r"\bnos vimos\b"],
    "hello": [r"^\s*(hola|hi|hello|que tal|qué tal|como estas|cómo estás)\b"],
}
def _match_smalltalk(q: str) -> Optional[str]:
    ql = (q or "").lower().strip()
    for intent, pats in _SMALLTALK.items():
        for p in pats:
            if re.search(p, ql):
                return intent
    return None

# ---------------------- Normalización y fuzzy ----------------------
def _norm(s: str) -> str:
    import unicodedata, re as _re
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _re.sub(r"\s+", " ", s)

def _fuzzy_contains(text_norm: str, targets: List[str], threshold: float = 0.84) -> bool:
    tokens = text_norm.split()
    for t in tokens:
      if len(t) < 4:
          continue
      for k in targets:
          if t == k or SequenceMatcher(a=t, b=k).ratio() >= threshold:
              return True
    bigrams = [" ".join([tokens[i], tokens[i+1]]) for i in range(len(tokens)-1)]
    for bg in bigrams:
        for k in targets:
            if SequenceMatcher(a=bg, b=k).ratio() >= threshold:
                return True
    return False

# ---------------------- Telemedicina: solo consultas "puras" de atención ----------------------
CARE_PATTERNS = [
    r"\breceta(s)?\b", r"\brecetario\b", r"\bprescripci[oó]n(es)?\b",
    r"\bhospital(es)?\b", r"\bcl[ií]nica(s)?\b",
    r"\burgenci(as|a)\b",
    r"\bcentro(s)?\s+(m[eé]dic[oa]s?|de salud|de atenci[oó]n)\b",
    r"\btelemedicina\b", r"\bm[eé]dic[oa]\b", r"\bdoctor(es)?\b"
]
CLINICAL_KWS = [
    "para que sirve","para qué sirve","efecto","efectos","contraindic","interacc",
    "advertenc","precauci","posolog","dosis","mg","tableta","comprimido","mecanism"
]
def _is_pure_care_query(q: str) -> bool:
    """Solo deriva a telemedicina si hay intención de atención/receta y NO hay palabras clínicas."""
    ql = (q or "").lower()
    hits_care = any(re.search(p, ql) for p in CARE_PATTERNS)
    has_clinical = any(k in ql for k in CLINICAL_KWS)
    return hits_care and not has_clinical

_TELEMED_TEXT = (
    "Para tener ayuda profesional sobre tu estado de salud o para conseguir la receta de un medicamento "
    ", puedes tener tu sesión de telemedicina con un médico 24/7 en esta página: "
    "https://www.mediclic.cl/telemedicinainmediata"
)
_TELEMED_CTA = {"label": "Mediclic Telemedicina 24/7", "url": "https://www.mediclic.cl/telemedicinainmediata", "type": "telemed"}

# ---------------------- Detección de Farmacias ----------------------
def _detect_pharmacy(q: str) -> (bool, str):
    ql = _norm(q)
    has_farmacia = re.search(r"\bfarmacia(s)?\b", ql) is not None
    mentions_turno = bool(
        re.search(r"\b(de\s+)?turno\b", ql) or re.search(r"\bguardia\b", ql) or re.search(r"24\s*h(or)?as?", ql)
    )
    if has_farmacia and mentions_turno:
        return True, "turno"
    if has_farmacia:
        return True, "cercanas"
    if mentions_turno:
        return True, "turno"
    return False, ""

# ---------------------- Helpers ----------------------
def _first_nonempty(*vals: Optional[str]) -> str:
    for v in vals:
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _sanitize(name: str) -> str:
    import re as _re
    s = _re.sub(r"\s+", " ", name or "").strip()
    return s[:1].upper() + s[1:] if s else s

def _canon_section_name(raw: str) -> str:
    r = (raw or "").strip().lower()
    if "mecanism" in r or "mecanismo" in r: return "mecanismo"
    if "contraindic" in r: return "contraindicaciones"
    if "advertenc" in r or "precauc" in r or "warning" in r: return "advertencias"
    if "interacc" in r or "interaccion" in r or "interacción" in r: return "interacciones"
    if "efecto" in r or "adverse" in r or "side effect" in r: return "efectos_secundarios"
    if "posolog" in r or "dosage" in r or "dosing" in r or "dose" in r: return "posologia"
    if "indicac" in r or "uso" in r or "sirve" in r: return "indicaciones"
    return r

def _section_of(best: Dict[str, Any]) -> str:
    raw = best.get("section_es") or best.get("section") or ""
    return _canon_section_name(raw)

def _pick_section_text_strict(best: Dict[str, Any], section: str) -> str:
    """Devuelve texto SOLO si el payload es de la sección pedida."""
    if _section_of(best) != section:
        return ""
    for k in SECTION_KEYS.get(section, []):
        val = best.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for k in ANY_TEXT_KEYS:
        val = best.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""

def _pick_any_text(best: Dict[str, Any]) -> str:
    for k in ANY_TEXT_KEYS:
        val = best.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""

def _local_hour(tz_str: Optional[str]) -> int:
    try:
        if tz_str and ZoneInfo is not None:
            return datetime.now(ZoneInfo(tz_str)).hour
        if ZoneInfo is not None:
            return datetime.now(ZoneInfo(DEFAULT_TZ)).hour
    except Exception:
        pass
    return datetime.now().hour

def _greeting(tz_str: Optional[str], user_name: Optional[str]) -> str:
    h = _local_hour(tz_str)
    sal = "buenos días" if 5 <= h < 12 else ("buenas tardes" if 12 <= h < 20 else "buenas noches")
    nombre = f", {user_name}" if user_name else ""
    return f"Hola{nombre}, {sal}. Espero que estés muy bien."

# ---------------------- Humanización opcional ----------------------
_LLM_PROMPT = """Reformula EN ESPAÑOL, tono cálido y claro, el contenido clínico exactamente como está,
SIN agregar datos ni recomendaciones personalizadas. No inventes. No sugieras dosis.
Devuelve 2–3 frases como máximo.

Medicamento: {drug}
Sección: {label}
Texto fuente:
---
{text}
---
Responde en texto corrido, sin listas ni viñetas.
"""
async def _humanize(drug: str, label: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if _LLM is not None:
        try:
            resp = await _LLM.ainvoke(_LLM_PROMPT.format(drug=drug, label=label, text=text))
            out = (getattr(resp, "content", None) or "").strip()
            if out:
                return out
        except Exception:
            pass
    # Fallback plano
    if label == "Para qué sirve": return f"{drug} se utiliza para {text.lower()}."
    if label == "Efectos secundarios": return f"Como todo medicamento, {drug} puede causar {text.lower()}."
    if label == "Contraindicaciones": return f"{drug} no debe usarse en estas situaciones: {text}"
    if label == "Interacciones": return f"{drug} puede interactuar con otras sustancias o fármacos: {text}"
    if label == "Advertencias / Precauciones": return f"Úsalo con precaución: {text}"
    if label == "Mecanismo de acción": return f"En términos simples, {drug} actúa así: {text}"
    if label == "Posología (solo informativa)": return f"Sobre posología (orientativo, no personalizado): {text}"
    return f"{drug}: {text}"

# ---------------------- Guesser de nombre con typos ----------------------
def _guess_drug_loose(user_q: str) -> str:
    try:
        retriever_singleton.ensure_vocab()
        vocab = list(getattr(retriever_singleton, "_norm_to_display", {}).keys())
        display = getattr(retriever_singleton, "_norm_to_display", {})
    except Exception:
        return ""
    words = [_norm(w) for w in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]+", user_q)]
    words = [w for w in words if len(w) >= 5]
    if not words:
        return ""
    best = ("", 0.0)
    for w in words:
        for cand in vocab[:8000]:
            if w in cand or cand in w:
                return display.get(cand, cand)
            sim = SequenceMatcher(a=w, b=cand).ratio()
            if sim > best[1]:
                best = (cand, sim)
    if best[1] >= 0.80:
        return display.get(best[0], best[0])
    return ""

# ---------------------- NUEVO: seguimiento referencial ----------------------
def _is_referential_followup(q: str) -> bool:
    """
    True si la pregunta parece referirse al medicamento anterior:
    "y sus interacciones", "de ese medicamento", "del mismo", "lo mismo", etc.
    """
    qn = _norm(q)
    pats = [
        r"^\s*y\s",                     # "y ..."
        r"\bsus?\b",                    # "sus interacciones"
        r"\b(de(l| la)?\s+(mismo|anterior|medicamento))\b",
        r"\b(ese|esa|este|esta|eso|esto)\b",
        r"\brespecto (a|del|de la)\b",
        r"\blo mismo\b",
    ]
    for p in pats:
        if re.search(p, qn):
            return True
    return False

# ---------------------- Small talk replies ----------------------
def _reply_smalltalk(intent: str, last_drug: str, tz: Optional[str], user_name: Optional[str]) -> str:
    if intent == "thanks":
        return (f"¡De nada! Para eso estoy. Si te sirve, puedo contarte efectos secundarios, contraindicaciones, "
                f"interacciones o posología de {_sanitize(last_drug)}." if last_drug else
                "¡De nada! Si necesitas información sobre algún medicamento, aquí estaré.")
    if intent == "bye":
        return (f"¡Que te vaya muy bien! Si en otro momento necesitas revisar algo más sobre {_sanitize(last_drug)} u otro medicamento, me avisas. 🙂"
                if last_drug else "¡Que te vaya muy bien! Cuando quieras retomamos. 🙂")
    if intent == "hello":
        return _greeting(tz, user_name) + " ¿En qué medicamento te gustaría que te ayude?"
    return ""

# ---------------------- Búsqueda exacta (nombre + sección) en Qdrant ----------------------
def _by_name_and_section(name_hint: str, section: str) -> List[Dict[str, Any]]:
    if not qm or not hasattr(retriever_singleton, "q"):
        return []
    outs: List[Dict[str, Any]] = []
    try:
        name_should = []
        for key in ("name_es", "generic_name_es", "name", "generic_name"):
            name_should.append(qm.FieldCondition(key=key, match=qm.MatchText(text=name_hint)))
            name_should.append(qm.FieldCondition(key=key, match=qm.MatchValue(value=name_hint)))
        # Español
        es_filter = qm.Filter(
            must=[qm.FieldCondition(key="section_es", match=qm.MatchValue(value=section))],
            should=name_should
        )
        points, _ = retriever_singleton.q.scroll(
            collection_name=retriever_singleton.coll,
            scroll_filter=es_filter,
            limit=256,
            with_payload=True,
        )
        for p in points:
            pl = dict(p.payload or {})
            if _section_of(pl) == section:
                outs.append(pl)
        # Inglés
        for en_sec in EN_SECTIONS.get(section, []):
            en_filter = qm.Filter(
                must=[qm.FieldCondition(key="section", match=qm.MatchValue(value=en_sec))],
                should=name_should
            )
            points2, _ = retriever_singleton.q.scroll(
                collection_name=retriever_singleton.coll,
                scroll_filter=en_filter,
                limit=256,
                with_payload=True,
            )
            for p in points2:
                pl = dict(p.payload or {})
                if _section_of(pl) == section:
                    outs.append(pl)
    except Exception:
        return outs
    return outs

def _pick_best_payload(payloads: List[Dict[str, Any]], section: str) -> Optional[Dict[str, Any]]:
    if not payloads:
        return None
    with_text = [p for p in payloads if _pick_section_text_strict(p, section)]
    if with_text:
        return with_text[0]
    return payloads[0]

# ---------------------- Herramienta principal ----------------------
async def search_vademecum(state: dict):
    """
    Espera en state:
      - input: texto del usuario
      - last_drug: (opcional) último fármaco consultado
      - user_tz: (opcional) tz del usuario
      - user_name: (opcional) nombre
    """
    user_q: str = (state.get("input") or "").strip()
    last_drug_state: str = state.get("last_drug") or ""
    tz = state.get("user_tz")
    user_name = state.get("user_name")

    # Prefijo de saludo SOLO si el mensaje comienza con saludo
    greet_prefix = ""
    if re.search(_SMALLTALK["hello"][0], (user_q or "").lower().strip()):
        greet_prefix = _greeting(tz, user_name) + " "

    # 0) Telemedicina solo si la consulta es “pura” de atención/receta
    if _is_pure_care_query(user_q):
        state["output"] = _TELEMED_TEXT
        state["data"] = {
            "match": None, "last_drug": last_drug_state, "care": True,
            "cta": _TELEMED_CTA, "ctas": [_TELEMED_CTA]
        }
        return state

    # 0.1) Farmacias (cercanas o de turno): el frontend gestionará geolocalización y mapa
    is_pharm, mode = _detect_pharmacy(user_q)
    if is_pharm:
        heading = (
            "Estas son las farmacias de turno cercanas (una por comuna para hoy)."
            if mode == "turno"
            else "Estas son algunas farmacias cercanas."
        )
        ctas = [
            {"label": "Usar mi ubicación", "type": "use_location"},
            {"label": "Abrir mapa", "type": "open_map", "payload": {"mode": mode}},
        ]
        state["output"] = heading
        state["data"] = {
            "match": None, "last_drug": last_drug_state,
            "route": "pharmacies", "pharmacy_mode": mode,
            "ctas": ctas
        }
        return state

    # 1) Intent clínico
    section = _infer_section(user_q)

    # 1.1) Small talk “puro”
    st_intent = _match_smalltalk(user_q)
    has_clinical_kw = section != "indicaciones" or bool(re.search(r"(para\s+que\s+sirve|efect|contraindic|interacc|advertenc|posolog|mecanism)", user_q.lower()))
    if st_intent in ("thanks", "bye") and not has_clinical_kw:
        state["output"] = _reply_smalltalk(st_intent, last_drug_state, tz, user_name)
        state["data"] = {"match": None, "last_drug": last_drug_state}
        return state
    if st_intent == "hello" and not has_clinical_kw:
        state["output"] = _reply_smalltalk("hello", last_drug_state, tz, user_name)
        state["data"] = {"match": None, "last_drug": last_drug_state}
        return state

        # 2) Nombre del fármaco (exacto o guesser)
    # 2) Nombre del fármaco (exacto o guesser)
    try:
        name_from_text = retriever_singleton.extract_name_from_text(user_q, strict_only=False) or ""
    except Exception:
        name_from_text = ""
    if not name_from_text:
        name_from_text = _guess_drug_loose(user_q) or ""

    # ¿El mensaje parece referencial? (explícito o implícito si hay palabras clínicas y last_drug)
    referential = _is_referential_followup(user_q) or (bool(last_drug_state) and has_clinical_kw)

    # 2.1) Decidir si usamos last_drug o caemos a fallback
    if not name_from_text:
        if referential and last_drug_state:
            name_hint = last_drug_state
        else:
            q_echo = user_q.strip()
            state["output"] = (
                f"No puedo ayudarte con tu duda: “{q_echo}”. "
                f"En mi caso puedo responderte dudas sobre medicamentos por ejemplo: (¿Para qué sirve la aspirina?) "
                f"o a mostrar 'farmacias cercanas' y de 'turno'. "
                f"Si quieres, pregúntame por un medicamento o pídeme ver farmacias cerca de ti 🙂."
            )
            state["data"] = {"match": None, "last_drug": last_drug_state, "offtopic": True}
            return state
    else:
        name_hint = name_from_text

    # 3) Seguridad: si sigue sin nombre útil, solicita uno
    if not name_hint or len(name_hint) < 3:
        state["output"] = greet_prefix + 'Para ayudarte, dime el nombre del medicamento (por ejemplo: "aspirina").'
        state["data"] = {"match": None, "last_drug": last_drug_state}
        return state

    # 4) Buscar payload correcto (ES/EN); prioridad sección exacta
    best: Optional[Dict[str, Any]] = None
    exacts = _by_name_and_section(name_hint, section)
    if exacts:
        best = _pick_best_payload(exacts, section)

    def _best_for(prefer_section: str) -> Optional[Dict[str, Any]]:
        try:
            return retriever_singleton.best_metadata_first(name_hint=name_hint, prefer=[prefer_section])
        except Exception:
            return None

    if not best:
        maybe = _best_for(section)
        if maybe and _section_of(maybe) == section:
            best = maybe

    # 4.1) Fallback específico: contraindicaciones -> advertencias
    if (not best or _section_of(best) != section) and section == "contraindicaciones":
        adv_exact = _by_name_and_section(name_hint, "advertencias")
        if adv_exact:
            best = _pick_best_payload(adv_exact, "advertencias")
            section = "advertencias"
        else:
            alt = _best_for("advertencias")
            if alt and _section_of(alt) == "advertencias":
                best = alt
                section = "advertencias"

    # 5) Si no hay sección correcta, informar
    if not best or _section_of(best) != section:
        state["output"] = greet_prefix + f"No tengo información sobre {name_hint} para “{SECTION_LABEL.get(section, section)}” en este momento."
        state["data"] = {"match": None, "last_drug": name_hint}
        state["last_drug"] = name_hint
        return state

    # 6) Persistir last_drug
    last_drug = _first_nonempty(best.get("name_es"), best.get("generic_name_es"), best.get("name")) or name_hint
    state["last_drug"] = last_drug

    # 7) Construir respuesta humanizada de la sección correcta
    label = SECTION_LABEL.get(section, section.capitalize())
    main_text = _pick_section_text_strict(best, section)
    if not main_text:
        main_text = _pick_any_text(best)
    if not main_text:
        state["output"] = greet_prefix + f"No tengo texto específico para “{label.lower()}” de {last_drug} por ahora."
        state["data"] = {"match": best, "last_drug": last_drug}
        return state

    nice = await _humanize(_sanitize(last_drug), label, main_text)
    body = f"{nice}\n\nSi notas algo inusual o tomas otros fármacos, es mejor comentarlo con un profesional."

    state["output"] = greet_prefix + body
    state["data"] = {"match": best, "last_drug": last_drug}
    return state
