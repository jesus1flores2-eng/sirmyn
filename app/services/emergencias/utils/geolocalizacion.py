"""
Utilidades de geolocalización para emergencias
VERSIÓN COMPLETA con todas tus funciones originales
"""
import os
import requests
import logging
import unicodedata
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def obtener_direccion_osm(latitud: float, longitud: float) -> Optional[Dict]:
    """
    Obtiene la dirección a partir de coordenadas usando OpenStreetMap
    COPIADO DE TU CÓDIGO ORIGINAL
    
    Args:
        latitud (float): Latitud
        longitud (float): Longitud
    
    Returns:
        dict o None: Diccionario con componentes de la dirección
    """
    try:
        user_agent = os.getenv('OSM_USER_AGENT', 'SIRMYN-Emergencias/1.0')
        url = "https://nominatim.openstreetmap.org/reverse"
        
        params = {
            'lat': latitud,
            'lon': longitud,
            'format': 'json',
            'zoom': 18,  # Nivel de detalle (10=ciudad, 18=casa)
            'addressdetails': 1  # Obtener detalles desglosados
        }
        
        headers = {'User-Agent': user_agent}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extraer componentes importantes
            address = data.get('address', {})
            
            direccion_info = {
                'display_name': data.get('display_name', ''),
                'road': address.get('road', ''),  # Calle
                'house_number': address.get('house_number', ''),  # Número
                'neighbourhood': address.get('neighbourhood', ''),  # Colonia/Barrio
                'suburb': address.get('suburb', ''),  # Colonia (alternativo)
                'village': address.get('village', ''),  # Pueblo
                'town': address.get('town', ''),  # Pueblo grande
                'city': address.get('city', ''),  # Ciudad
                'state': address.get('state', ''),
                'country': address.get('country', '')
            }
            
            # Determinar localidad (prioridad: neighbourhood > suburb > village > town > city)
            localidad = (direccion_info['neighbourhood'] or 
                        direccion_info['suburb'] or 
                        direccion_info['village'] or 
                        direccion_info['town'] or 
                        direccion_info['city'])
            
            direccion_info['localidad'] = localidad
            
            logger.info(f"📍 Reverse geocoding exitoso: {localidad}, {direccion_info['road']}")
            return direccion_info
            
        else:
            logger.error(f"❌ Error en reverse geocoding: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error en obtener_direccion_osm: {e}")
        return None


def calcular_distancia(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula distancia en kilómetros entre dos puntos usando fórmula Haversine
    """
    from math import radians, sin, cos, sqrt, atan2
    
    # Radio de la Tierra en kilómetros
    R = 6371.0
    
    # Convertir grados a radianes
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)
    
    # Diferencias
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    
    # Fórmula Haversine
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    distancia = R * c
    return round(distancia, 2)


def generar_mapa_url(latitud: float, longitud: float, provider: str = "google") -> str:
    """
    Genera URL para ver ubicación en mapas
    """
    if provider.lower() == "google":
        return f"https://maps.google.com/?q={latitud},{longitud}"
    elif provider.lower() == "osm":
        return f"https://www.openstreetmap.org/?mlat={latitud}&mlon={longitud}"
    else:  # what3words
        return f"https://what3words.com////{latitud:.6f},{longitud:.6f}"


def _normalize_text(text: str) -> str:
    """
    Normaliza texto para búsquedas flexibles
    COPIADO DE TU CÓDIGO
    """
    if not text:
        return ""
    # Quitar acentos
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    # Minúsculas y quitar artículos comunes
    text = text.lower()
    for articulo in ["colonia ", "fraccionamiento ", "barrio ", "el ", "la ", "los ", "las "]:
        if text.startswith(articulo):
            text = text[len(articulo):]
    return text.strip()


# Si necesitas fuzzywuzzy, instálalo: pip install fuzzywuzzy python-Levenshtein
try:
    from fuzzywuzzy import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("⚠️ fuzzywuzzy no instalado. Búsquedas flexibles limitadas.")