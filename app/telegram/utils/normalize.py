# app/telegram/utils/normalize.py
import re
import unicodedata

def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    stop_words = {"de", "la", "el", "y", "del", "los", "las", "en", "con"}
    words = s.split()
    filtered_words = [w for w in words if w not in stop_words and len(w) > 1]
    s = " ".join(filtered_words)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extraer_numero_opcion(texto: str):
    numeros = re.findall(r'\d+', texto)
    return numeros[0] if numeros else None
