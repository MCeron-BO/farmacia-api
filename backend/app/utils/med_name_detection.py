# app/utils/med_name_detection.py
import re
from rapidfuzz import process, fuzz

def _normalize(s: str) -> str:
    return re.sub(r"[^a-záéíóúüñ0-9 ]", "", (s or "").lower()).strip()

def pick_drug_name(query: str, vocab: list[str], min_score: int = 80) -> str | None:
    """
    Devuelve el mejor nombre del vocabulario si la similitud >= min_score.
    Permite typos y sin tildes: 'aspirina', 'asprina', etc.
    """
    q = _normalize(query)
    if not q or not vocab:
        return None
    match = process.extractOne(q, vocab, scorer=fuzz.WRatio)
    if match and match[1] >= min_score:
        return match[0]
    return None

def normalize_for_overlap(s: str) -> str:
    return _normalize(s)