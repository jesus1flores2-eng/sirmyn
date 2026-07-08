import os
import shutil

def obtener_carpeta_departamento(tipo_reporte: str) -> str:
    mapeo = {
        "Agua potable": "agua_potable",
        "Drenaje": "drenaje",
        "Aseo público": "aseo_publico",
        "Alumbrado público": "alumbrado_publico",
        "Parques y jardines": "parques_jardines",
        "Ecología": "ecologia",
        "Seguridad pública": "seguridad_publica",
        "Obras públicas": "obras_publicas",
        "Bomberos": "bomberos"
    }
    return mapeo.get(tipo_reporte, "general")

def guardar_evidencia(carpeta_base, carpeta_departamento, nombre_temporal, nombre_definitivo):
    """Mueve un archivo de evidencia a su ubicación definitiva"""
    carpeta_destino = os.path.join(carpeta_base, carpeta_departamento)
    os.makedirs(carpeta_destino, exist_ok=True)
    
    origen = os.path.join(carpeta_base, nombre_temporal)
    destino = os.path.join(carpeta_destino, nombre_definitivo)
    
    if os.path.exists(origen):
        shutil.move(origen, destino)
        return f"{carpeta_departamento}/{nombre_definitivo}"
    return None
