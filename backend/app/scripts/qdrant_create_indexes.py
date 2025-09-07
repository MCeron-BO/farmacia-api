# app/scripts/qdrant_create_indexes.py
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

load_dotenv()

URL = os.getenv("QDRANT_URL")
KEY = os.getenv("QDRANT_API_KEY")
COLL = os.getenv("QDRANT_COLLECTION", "vademecum_es")
assert URL, "Falta QDRANT_URL en el .env"

client = QdrantClient(url=URL, api_key=KEY)

def ensure_index(field_name, schema):
    try:
        client.create_payload_index(collection_name=COLL, field_name=field_name, field_schema=schema)
        print(f"[OK] Index creado: {field_name}")
    except Exception as e:
        print(f"[INFO] '{field_name}' no creado (quizás ya existe): {e}")

# 1) Index KEYWORD para la sección (filtros exactos)
ensure_index("section_es", qm.PayloadSchemaType.KEYWORD)

# 2) Index TEXT para nombre y genérico (full-text)
#    Intento forma “nueva”: requiere type="text" y tokenizer válido
try:
    text_params = qm.TextIndexParams(
        type="text",                 # <- requerido por tu versión
        tokenizer="multilingual",    # opciones: prefix | whitespace | word | multilingual
        min_token_len=2,
        max_token_len=30,
        lowercase=True,              # opcional pero útil
    )
    ensure_index("name_es", text_params)
    ensure_index("generic_name_es", text_params)
except Exception as e:
    print(f"[WARN] Falling back a forma alternativa de TextIndexParams: {e}")
    # Forma alternativa para clientes más viejos (sin 'type' / enums distintos)
    try:
        text_params_alt = qm.TextIndexParams(
            tokenizer="word",
            min_token_len=2,
            max_token_len=30,
        )
        ensure_index("name_es", text_params_alt)
        ensure_index("generic_name_es", text_params_alt)
    except Exception as e2:
        print(f"[ERROR] No se pudo crear índice de texto: {e2}")

# 3) (Opcional) Index KEYWORD para doc_id
ensure_index("doc_id", qm.PayloadSchemaType.KEYWORD)

print("Listo.")
