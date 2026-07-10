"""
Utilidades compartidas para todo el bot de Telegram
"""
import time
import re
import unicodedata
import difflib
from typing import Dict, List, Optional, Tuple

# ============================================================
# ESTADO GLOBAL DE USUARIOS (en memoria)
# ============================================================
user_data: Dict[int, Dict] = {}

# ============================================================
# FUNCIONES DE GESTIÓN DE ESTADO
# ============================================================

def limpiar_estado(user_id: int):
    """Limpia el estado del usuario pero conserva el tipo para mensajes personalizados"""
    if user_id in user_data:
        # Conservar solo el tipo y tipo_key para mensajes personalizados
        tipo_guardado = user_data[user_id].get("tipo")
        tipo_key_guardado = user_data[user_id].get("tipo_key")
        
        # Limpiar todo
        user_data[user_id] = {}
        
        # Restaurar solo el tipo si existe
        if tipo_guardado:
            user_data[user_id]["tipo"] = tipo_guardado
        if tipo_key_guardado:
            user_data[user_id]["tipo_key"] = tipo_key_guardado
        
        # Agregar timestamp
        user_data[user_id]["_timestamp"] = time.time()
    else:
        user_data[user_id] = {"_timestamp": time.time()}


def actualizar_timestamp_usuario(user_id: int):
    """Actualiza timestamp de actividad del usuario"""
    if user_id in user_data:
        user_data[user_id]["_timestamp"] = time.time()
    else:
        user_data[user_id] = {"_timestamp": time.time()}


def get_saludo() -> str:
    """Retorna saludo según la hora del día"""
    h = time.localtime().tm_hour
    if h < 12:
        return "Buenos días"
    elif h < 19:
        return "Buenas tardes"
    else:
        return "Buenas noches"


# ============================================================
# FUNCIONES DE BÚSQUEDA FLEXIBLE (para localidades y calles)
# ============================================================

def _normalize_text(s: str) -> str:
    """Normaliza texto para búsqueda (sin acentos, minúsculas, sin artículos)"""
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


def buscar_coincidencias_flexibles(entrada: str, candidatos: List[Tuple[int, str]]) -> List[Dict]:
    """Búsqueda flexible que maneja errores ortográficos"""
    entrada_limpia = _normalize_text(entrada)
    
    if not entrada_limpia:
        return []
    
    resultados = []
    
    for id_item, nombre in candidatos:
        nombre_limpio = _normalize_text(nombre)
        
        if entrada_limpia == nombre_limpio:
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": 1.0,
                "tipo": "exacta"
            })
            continue
        
        if entrada_limpia in nombre_limpio:
            score = 0.9 if nombre_limpio.startswith(entrada_limpia) else 0.8
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": score,
                "tipo": "parcial"
            })
            continue
        
        if nombre_limpio in entrada_limpia:
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": 0.7,
                "tipo": "contenido"
            })
            continue
        
        palabras_entrada = set(entrada_limpia.split())
        palabras_nombre = set(nombre_limpio.split())
        
        palabras_comunes = palabras_entrada.intersection(palabras_nombre)
        if palabras_comunes:
            score_palabras = len(palabras_comunes) / max(len(palabras_entrada), len(palabras_nombre))
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": 0.5 + (score_palabras * 0.3),
                "tipo": "palabras"
            })
            continue
        
        umbral = 0.5 if len(entrada_limpia) > 5 else 0.6
        similitud = difflib.SequenceMatcher(a=entrada_limpia, b=nombre_limpio).ratio()
        
        if similitud >= umbral:
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": similitud,
                "tipo": "difusa"
            })
            continue
        
        palabras_nombre_lista = nombre_limpio.split()
        if len(palabras_nombre_lista) > 1:
            primera_palabra = palabras_nombre_lista[0]
            if difflib.SequenceMatcher(a=entrada_limpia, b=primera_palabra).ratio() >= 0.7:
                resultados.append({
                    "id": id_item,
                    "nombre": nombre,
                    "score": 0.65,
                    "tipo": "primera_palabra"
                })
    
    resultados.sort(key=lambda x: x["score"], reverse=True)
    return resultados


# ============================================================
# FUNCIÓN AUXILIAR PARA TECLADOS
# ============================================================

def extraer_numero_opcion(texto: str) -> Optional[str]:
    """Extrae números del texto para identificar opciones"""
    numeros = re.findall(r'\d+', texto)
    return numeros[0] if numeros else None
