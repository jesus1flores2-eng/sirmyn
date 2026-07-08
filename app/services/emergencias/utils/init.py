"""
Utilidades para el sistema de emergencias SIRMYN
"""
from .geolocalizacion import (
    obtener_direccion_osm,
    calcular_distancia,
    generar_mapa_url
)

__all__ = [
    'obtener_direccion_osm',
    'calcular_distancia', 
    'generar_mapa_url'
]