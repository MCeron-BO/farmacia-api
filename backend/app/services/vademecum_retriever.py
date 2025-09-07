from __future__ import annotations
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from sentence_transformers import SentenceTransformer
import numpy as np
import dotenv

dotenv.load_dotenv()

try:
    from rapidfuzz import fuzz
except Exception:
    class _F:
        @staticmethod
        def token_set_ratio(a, b):
            a = a or ""
            b = b or ""
            set_a = set(a.lower().split())
            set_b = set(b.lower().split())
            inter = len(set_a & set_b)
            if not set_a or not set_b:
                return 0
            return int(100 * (2 * inter) / (len(set_a) + len(set_b)))
    fuzz = _F()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "vademecum_es")
_EMB_MODEL_NAME = os.getenv("EMB_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def _drug_key(p: Dict[str, Any]) -> str:
    for k in ("name_es", "generic_name_es", "name", "generic_name"):
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            return _norm(v)
    return ""


def detect_section(user_q: str) -> str:
    q = _norm(user_q)
    # Posología / dosis
    if re.search(r"\b(posologia|posología|dosage|dosis|dosing|cada cu[aá]ntas|cada cuantos|cada\s*horas)\b", q):
        return "posologia"
    # Mecanismo de acción
    if re.search(r"mecanismo|c[oó]mo\s+funciona|como\s+funciona|mechanism", q):
        return "mecanismo"
    # Forma farmacéutica (cápsulas, comprimidos) suele mapear a posología/uso
    if re.search(r"forma\s+farmaceutica|forma\s+farmac[eé]utica|dosage\s*form", q):
        return "posologia"
    # Efectos secundarios / reacciones adversas
    if re.search(r"(efecto(s)?\s+secundari)|(reacci[oó]n(es)?\s+adversa)", q) or re.search(r"me\s+(hara|har[aá])\s+mal|me\s+puede\s+hacer\s+mal", q):
        return "efectos_secundarios"
    # Interacciones (incluye alcohol, alimentos)
    if re.search(r"interacci|interact|mezcl(ar|o)|alcohol|comida|alimentos|jugo\s+de\s+toronja|pomelo", q):
        return "interacciones"
    # Contraindicaciones / restricciones
    if re.search(r"contraindicaci|restricci[oó]n|restricciones|no\s+debo|prohibid[oa]|embarazo|gestaci[oó]n|lactancia|alergi|insuficiencia\s+(renal|hep[aá]tica)|niñ[oa]s|adult[oa]s?\s+mayores", q):
        return "contraindicaciones"
    # Advertencias / precauciones
    if re.search(r"advertenc|precauci|alerta|cuidado|riesgo|precauci[oó]n|manejar|conducir", q):
        return "advertencias"
    # Indicaciones / para qué sirve
    if re.search(r"indicaci[oó]n|para\s+que\s+sirve|para\s+qu[eé]\s+sirve|utiliza|uso\b|para\s+qu[eé]\s+se\s+usa", q):
        return "indicaciones"
    return "indicaciones"

def _canon_section(payload: Dict[str, Any]) -> str:
    raw = _norm(payload.get("section_es") or payload.get("section") or "")
    if not raw: return ""
    if "mecanism" in raw or "mecanismo" in raw or "funciona" in raw: return "mecanismo"
    if "contraindic" in raw: return "contraindicaciones"
    if "advertenc" in raw or "precauc" in raw or "warning" in raw: return "advertencias"
    if "interacc" in raw: return "interacciones"
    if "efecto" in raw or "adverse" in raw or "side effect" in raw: return "efectos_secundarios"
    if "posolog" in raw or "dosage" in raw or "dosing" in raw or "dose" in raw: return "posologia"
    if "indicac" in raw or "uso" in raw or "beneficio" in raw or "sirve" in raw: return "indicaciones"
    return raw


class VademecumRetriever:
    """
    Estrategia metadata-first; incluye:
    - Vocabulario de nombres cacheado (para extracción por palabra exacta).
    - Búsqueda por nombre con filtros (sin vectores) y selección por sección.
    - Fallback semántico sólo si NO tenemos nombre.
    """

    def __init__(self, url: str, coll: str, api_key: Optional[str] = None, top_k_default: int = 12):
        self.q = QdrantClient(url=url, api_key=api_key) if api_key else QdrantClient(url=url)
        self.coll = coll
        self.emb = SentenceTransformer(_EMB_MODEL_NAME)
        self.top_k_default = top_k_default

        # vocab
        self._vocab_ready = False
        self._names_norm: List[str] = []
        self._norm_to_display: Dict[str, str] = {}

        # índices (best effort)
        try:
            def try_index(key: str, params: qm.PayloadIndexParams):
                try:
                    self.q.create_payload_index(collection_name=self.coll, field_name=key, field_schema=params)
                    print(f"[Qdrant] Index creado: {key}")
                except Exception:
                    pass
            txt = lambda: qm.TextIndexParams(tokenizer="multilingual", type="text", min_token_len=2, max_token_len=30)
            for k in ("name_es", "generic_name_es", "name", "generic_name", "section_es", "section"):
                try_index(k, txt())
        except Exception as e:
            print(f"[Qdrant] No se pudieron crear índices opcionales: {e}")

    # ---------- Vocabulario ----------
    def try_index(self, *args, **kwargs):
        pass  # backward-compat; ya manejado arriba

    def ensure_vocab(self):
        if self._vocab_ready:
            return
        seen = set()
        try:
            offset = None
            page = 256
            while True:
                points, next_page = self.q.scroll(
                    collection_name=self.coll,
                    limit=page,
                    with_payload=True,
                    offset=offset,
                )
                for p in points:
                    pl = p.payload or {}
                    for k in ("name_es", "generic_name_es", "name", "generic_name"):
                        v = pl.get(k)
                        if isinstance(v, str) and v.strip():
                            norm = _norm(v)
                            if norm and norm not in seen:
                                seen.add(norm)
                                display = pl.get("name_es") or pl.get("generic_name_es") or pl.get("name") or pl.get("generic_name") or v
                                self._norm_to_display[norm] = display
                if not next_page:
                    break
                offset = next_page
        except Exception as e:
            print(f"[Qdrant] ensure_vocab error: {e}")

        self._names_norm = sorted(seen, key=lambda s: len(s), reverse=True)
        self._vocab_ready = True

    def extract_name_from_text(self, text: str, strict_only: bool = False) -> Optional[str]:
        """
        Devuelve nombre SOLO si aparece como palabra exacta del vocab.
        Si strict_only=False, puede intentar fuzzy, pero solo en textos largos.
        """
        if not text:
            return None
        self.ensure_vocab()
        t = _norm(text)
        if not t:
            return None

        # 1) match exacto por palabra completa
        for cand in self._names_norm:
            if re.search(rf"(^|[\s\W]){re.escape(cand)}($|[\s\W])", t):
                return self._norm_to_display.get(cand, cand)

        if strict_only:
            return None

        # 2) fuzzy solo para textos largos
        if len(t) < 18:
            return None

        best = None
        best_score = 0
        for cand in self._names_norm[:5000]:
            sc = fuzz.token_set_ratio(t, cand)
            if sc > best_score:
                best_score = sc
                best = cand
        if best and best_score >= 92 and len(best) >= 6:
            return self._norm_to_display.get(best, best)
        return None

    # ---------- Búsqueda por metadata ----------
    def _scroll_by_name(self, name_hint: str, limit: int = 512) -> List[Dict[str, Any]]:
        text = name_hint
        filt = qm.Filter(should=[
            qm.FieldCondition(key="name_es", match=qm.MatchText(text=text)),
            qm.FieldCondition(key="generic_name_es", match=qm.MatchText(text=text)),
            qm.FieldCondition(key="name", match=qm.MatchText(text=text)),
            qm.FieldCondition(key="generic_name", match=qm.MatchText(text=text)),
        ])
        out: List[Dict[str, Any]] = []
        try:
            points, _ = self.q.scroll(
                collection_name=self.coll,
                scroll_filter=filt,
                limit=limit,
                with_payload=True,
            )
            for p in points:
                out.append(dict(p.payload or {}))
        except Exception as e:
            print(f"[Qdrant] scroll_by_name error: {e}")
        return out

    def _pick_best_in_group(self, group: List[Dict[str, Any]], order: List[str]) -> Dict[str, Any]:
        """
        Entre secciones del mismo fármaco, preferir la sección en `order` (si existe),
        y preferir registros con `text_es/text` presentes.
        """
        if not group:
            return {}
        group_sorted = sorted(group, key=lambda p: (order.index(_canon_section(p)) if _canon_section(p) in order else 99))
        group_sorted = sorted(group_sorted, key=lambda p: 0 if (p.get("text_es") or p.get("text")) else 1)
        return group_sorted[0]

    def best_metadata_first(self, name_hint: str, prefer: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        name_hint = (name_hint or "").strip()
        if len(name_hint) < 3:
            return None
        candidates = self._scroll_by_name(name_hint)
        if not candidates:
            return None

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for p in candidates:
            key = _drug_key(p) or _norm(p.get("doc_id") or "")
            groups.setdefault(key, []).append(p)

        best_key = None
        best_score = -1
        for k, items in groups.items():
            sample = items[0]
            disp = " ".join([
                sample.get("name_es") or "",
                sample.get("generic_name_es") or "",
                sample.get("name") or "",
                sample.get("generic_name") or "",
            ]).strip()
            sc = fuzz.token_set_ratio(_norm(name_hint), _norm(disp))
            if sc > best_score:
                best_score = sc
                best_key = k

        if best_key is None:
            return None

        order = (prefer or []) + ["indicaciones","efectos_secundarios","contraindicaciones","interacciones","advertencias","posologia","mecanismo"]
        return self._pick_best_in_group(groups[best_key], order)

    # ---------- Semántico (agrupado por fármaco) ----------
    def _embed(self, texts: List[str]) -> np.ndarray:
        return self.emb.encode(texts, normalize_embeddings=True)

    def _search_semantic(self, query: str, k: int) -> List[Dict[str, Any]]:
        # Busca k candidatos y agrupa por fármaco (doc_id/nombre canónico).
        # Devuelve SOLO el mejor grupo para evitar mezclar medicamentos.
        if not query:
            return []
        emb = self._embed([query])[0]
        try:
            res = self.q.search(
                collection_name=self.coll,
                query_vector=emb,
                limit=max(8, k),
                with_payload=True,
                score_threshold=None,
            )
        except Exception:
            return []

        payloads: List[Dict[str, Any]] = []
        for r in res:
            payload = dict(r.payload or {})
            payload["_score"] = float(r.score or 0.0)
            payloads.append(payload)

        if not payloads:
            return []

        # Agrupar por fármaco
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for p in payloads:
            key = _drug_key(p) or _norm(p.get("doc_id") or "")
            if not key:
                continue
            groups.setdefault(key, []).append(p)

        if not groups:
            return payloads

        # Score del grupo
        def group_score(items: List[Dict[str, Any]]) -> float:
            return max((i.get("_score") or 0.0) for i in items)

        best_key = max(groups.keys(), key=lambda k2: group_score(groups[k2]))
        best_items = groups[best_key]

        # Ordenar dentro del grupo por intención inferida
        intent = detect_section(query)
        preferred_order = ["indicaciones","efectos_secundarios","contraindicaciones","interacciones","advertencias","posologia","mecanismo"]
        def section_rank(p: Dict[str, Any]) -> int:
            sec = _canon_section(p)
            if sec == intent:
                return -1
            return preferred_order.index(sec) if sec in preferred_order else 99

        return sorted(best_items, key=section_rank)

    def best(self, query: str, k: int = 12) -> Optional[Dict[str, Any]]:
        return self.best_for(query, prefer=None, name_hint=None, k=k)

    def best_for(self, query: str, prefer: Optional[List[str]] = None, name_hint: Optional[str] = None, k: int = 12) -> Optional[Dict[str, Any]]:
        if name_hint:
            m = self.best_metadata_first(name_hint=name_hint, prefer=prefer)
            if m:
                return m
            # si hay name_hint pero no hay resultados, NO degrades a semántico (evita mezclar fármacos)
            return None
        if query:
            cand = self._search_semantic(query, k=max(12, k))
            if not cand:
                return None
            prefer_set = set(prefer or [])
            for p in cand:
                if _canon_section(p) in prefer_set:
                    return p
            return cand[0]
        return None

    def intent_from_query(self, query: str) -> str:
        return detect_section(query)


retriever_singleton = VademecumRetriever(
    url=QDRANT_URL, coll=QDRANT_COLLECTION, api_key=QDRANT_API_KEY
)
