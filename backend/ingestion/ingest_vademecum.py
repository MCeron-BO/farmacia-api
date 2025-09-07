import os, sys, csv, json, asyncio, math, hashlib
from typing import Dict, Iterable, List, Tuple, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from sentence_transformers import SentenceTransformer

# ---------- Config ----------
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLL = os.getenv("QDRANT_COLLECTION", "vademecum_es")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VEC_SIZE = 384
BATCH = 256

CACHE_PATH = os.getenv("TRANSLATE_CACHE", "translate_cache.json")

SECTION_MAP = {
    "Indications": "indications",
    "Mechanism of Action": "mechanism",
    "Side Effects": "side_effects",
    "Contraindications": "contraindications",
    "Interactions": "interactions",
    "Warnings and Precautions": "warnings",
}

# ---------- Utils ----------
def normalize_space(s: Optional[str]) -> str:
    if not s:
        return ""
    return " ".join(str(s).replace("\n", " ").split())

def build_dosage(row: Dict[str, str]) -> str:
    parts = []
    for k in ("Dosage Form", "Strength", "Route of Administration"):
        v = normalize_space(row.get(k, ""))
        if v:
            parts.append(f"{k}: {v}")
    return " | ".join(parts)

def split_recursive(text: str, max_len: int = 420) -> List[str]:
    text = normalize_space(text)
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    delimiters = [". ", "; ", ", "]
    chunks: List[str] = []
    buf = text
    while len(buf) > max_len:
        cut = -1
        for d in delimiters:
            pos = buf.rfind(d, 0, max_len)
            if pos > 0:
                cut = pos + len(d)
                break
        if cut == -1:
            cut = max_len
        chunks.append(buf[:cut].strip())
        buf = buf[cut:].lstrip()
    if buf:
        chunks.append(buf.strip())
    return chunks

def ensure_collection(client: QdrantClient):
    if not client.collection_exists(COLL):
        client.create_collection(
            collection_name=COLL,
            vectors_config=qm.VectorParams(size=VEC_SIZE, distance=qm.Distance.COSINE),
        )
        client.update_collection(
            collection_name=COLL,
            hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=256),
            optimizers_config=qm.OptimizersConfigDiff(memmap_threshold=20000),
        )

def rows_from_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

# ---------- Translation with caching ----------
def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_cache(path: str) -> Dict[str, str]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(path: str, cache: Dict[str, str]):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def translate_texts(texts: List[str]) -> List[str]:
    """
    Traduce una lista de textos EN->ES usando OpenAI.
    Usa un cache local por hash para evitar costs.

    Nota: se invoca en lotes pequeños para evitar límites.
    """
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Simple batching
    outputs: List[str] = []
    for t in texts:
        if not t:
            outputs.append("")
            continue
        key = _cache_key("EN2ES::" + t)
        if key in _TRANSLATE_CACHE:
            outputs.append(_TRANSLATE_CACHE[key])
            continue

        prompt = (
            "Traduce al español, mantén términos farmacológicos precisos y evita inventar información. "
            "Solo devuelve la traducción sin comentarios:\n\n"
            f"{t}"
        )
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role":"system","content":"Eres un traductor médico EN->ES preciso y conciso."},
                {"role":"user","content":prompt},
            ],
            temperature=0.2,
        )
        es = resp.choices[0].message.content.strip()
        _TRANSLATE_CACHE[key] = es
        outputs.append(es)

    # persist cache cada vez
    save_cache(CACHE_PATH, _TRANSLATE_CACHE)
    return outputs

_TRANSLATE_CACHE: Dict[str,str] = load_cache(CACHE_PATH)

def row_to_chunks(row: Dict[str, str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    # text sections
    for csv_col, section in SECTION_MAP.items():
        txt = normalize_space(row.get(csv_col, ""))
        for i, chunk in enumerate(split_recursive(txt)):
            out.append((section, chunk))
    # dosage group
    dosage = build_dosage(row)
    for i, chunk in enumerate(split_recursive(dosage)):
        out.append(("dosage", chunk))
    return out

def ingest_csv_with_translation(path: str):
    if not QDRANT_URL:
        print("ERROR: QDRANT_URL no configurada en .env")
        sys.exit(1)
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY no configurada en .env (requerida para traducir)")
        sys.exit(1)

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    ensure_collection(client)

    embedder = SentenceTransformer(EMBED_MODEL)

    points: List[qm.PointStruct] = []
    total_chunks = 0
    local_id = 0

    for row in rows_from_csv(path):
        drug_id = row.get("Drug ID") or row.get("ID") or ""
        name_en = normalize_space(row.get("Drug Name"))
        gname_en = normalize_space(row.get("Generic Name"))
        dclass_en = normalize_space(row.get("Drug Class"))
        manufacturer = normalize_space(row.get("Manufacturer"))
        price = normalize_space(row.get("Price"))
        approval = normalize_space(row.get("Approval Date"))
        availability = normalize_space(row.get("Availability"))

        # translate a pequeños lotes: name, generic, class
        name_es, gname_es, dclass_es = translate_texts([name_en, gname_en, dclass_en])

        chunks = row_to_chunks(row)
        # traducir contenido de los chunks por lote (para ahorrar llamadas)
        texts_en = [t for _, t in chunks]
        texts_es = translate_texts(texts_en)

        for idx, ((section, text_en), text_es) in enumerate(zip(chunks, texts_es)):
            vec = embedder.encode(text_es or text_en).tolist()  # embeddeamos el texto ES si existe
            payload = {
                "doc_id": f"drug:{drug_id or name_en}",
                # originales
                "name": name_en,
                "generic_name": gname_en,
                "drug_class": dclass_en,
                "section": section,
                "chunk_index": idx,
                "source": "kaggle:comprehensive-drug-information-dataset",
                "manufacturer": manufacturer,
                "approval_date": approval,
                "availability": availability,
                "price": price,
                "text": text_en,
                "title": f"{name_en} ({gname_en}) - {section}",
                # traducidos
                "name_es": name_es,
                "generic_name_es": gname_es,
                "drug_class_es": dclass_es,
                "text_es": text_es,
                "title_es": f"{name_es} ({gname_es}) - {section}",
                "section_es": {
                    "indications":"indicaciones",
                    "mechanism":"mecanismo",
                    "side_effects":"efectos_secundarios",
                    "contraindications":"contraindicaciones",
                    "interactions":"interacciones",
                    "warnings":"advertencias",
                    "dosage":"posologia",
                }.get(section, section)
            }
            points.append(qm.PointStruct(id=local_id, vector=vec, payload=payload))
            local_id += 1
            total_chunks += 1

            if len(points) >= BATCH:
                client.upsert(collection_name=COLL, points=points)
                points = []
                print(f"[UPSERT] chunks totales: {total_chunks}")

    if points:
        client.upsert(collection_name=COLL, points=points)

    print(f"[DONE] Ingestados {total_chunks} chunks ES a '{COLL}'")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ingestion_kaggle_vademecum_es.py /ruta/DrugData.csv")
        sys.exit(1)
    ingest_csv_with_translation(sys.argv[1])
