# app/telegram/utils/__init__.py
import time
from datetime import datetime
from .normalize import _normalize_text, extraer_numero_opcion
from .buscadores import buscar_coincidencias_flexibles

user_data = {}

def actualizar_timestamp_usuario(user_id: int):
    if user_id in user_data:
        user_data[user_id]["_timestamp"] = time.time()

def limpiar_estado(user_id: int):
    if user_id in user_data:
        tipo_guardado = user_data[user_id].get("tipo")
        tipo_key_guardado = user_data[user_id].get("tipo_key")
        user_data[user_id] = {}
        if tipo_guardado:
            user_data[user_id]["tipo"] = tipo_guardado
        if tipo_key_guardado:
            user_data[user_id]["tipo_key"] = tipo_key_guardado
        user_data[user_id]["_timestamp"] = time.time()

def get_saludo() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Buenos días"
    elif h < 19:
        return "Buenas tardes"
    else:
        return "Buenas noches"

# Exportar todo
__all__ = [
    'user_data',
    'actualizar_timestamp_usuario',
    'limpiar_estado',
    'get_saludo',
    '_normalize_text',
    'extraer_numero_opcion',
    'buscar_coincidencias_flexibles'
]
