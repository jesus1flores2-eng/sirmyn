# app/telegram/utils/buscadores.py
from .normalize import _normalize_text
import difflib

def buscar_coincidencias_flexibles(entrada: str, candidatos: list):
    """
    Búsqueda flexible que maneja errores ortográficos
    
    Args:
        entrada (str): Texto ingresado por el usuario
        candidatos (list): Lista de tuples (id, nombre)
    
    Returns:
        list: Lista de coincidencias ordenadas por relevancia
    """
    entrada_limpia = _normalize_text(entrada)
    
    if not entrada_limpia:
        return []
    
    resultados = []
    
    for id_item, nombre in candidatos:
        nombre_limpio = _normalize_text(nombre)
        
        # 1. Coincidencia exacta
        if entrada_limpia == nombre_limpio:
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": 1.0,
                "tipo": "exacta"
            })
            continue
        
        # 2. Coincidencia parcial (entrada está dentro del nombre)
        if entrada_limpia in nombre_limpio:
            score = 0.9 if nombre_limpio.startswith(entrada_limpia) else 0.8
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": score,
                "tipo": "parcial"
            })
            continue
        
        # 3. Coincidencia por contenido (nombre está dentro de la entrada)
        if nombre_limpio in entrada_limpia:
            resultados.append({
                "id": id_item,
                "nombre": nombre,
                "score": 0.7,
                "tipo": "contenido"
            })
            continue
        
        # 4. Coincidencia por palabras comunes
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
        
        # 5. Coincidencia difusa (usando SequenceMatcher)
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
        
        # 6. Coincidencia por primera palabra
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
