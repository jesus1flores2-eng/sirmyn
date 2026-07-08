import os
import requests
import logging
from app.services.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

def obtener_coordenadas_osm(localidad_nombre, calle_nombre, numero):
    """
    Obtiene coordenadas de OpenStreetMap RESTRINGIENDO la búsqueda al área
    geográfica de la localidad reportada.
    
    Args:
        localidad_nombre (str): Nombre de la localidad.
        calle_nombre (str): Nombre de la calle.
        numero (str): Número exterior.
    
    Returns:
        tuple: (latitud, longitud) o (None, None) si no se encuentra.
    """
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Localidad
            
            # 1. Obtener coordenadas centrales de la localidad desde la BD
            localidad_obj = Localidad.query.filter_by(nombre=localidad_nombre).first()
            if not localidad_obj:
                logger.warning(f"❌ Localidad '{localidad_nombre}' no encontrada en la base de datos.")
                return None, None
            
            if localidad_obj.latitud_central is None or localidad_obj.longitud_central is None:
                logger.warning(f"⚠️ La localidad '{localidad_nombre}' no tiene coordenadas centrales definidas.")
                return None, None
            
            lat_centro = localidad_obj.latitud_central
            lon_centro = localidad_obj.longitud_central
            logger.info(f"📍 Centro de búsqueda para '{localidad_nombre}': {lat_centro}, {lon_centro}")
            
            # 2. Definir el área de búsqueda (viewbox)
            delta = 0.02  # Ajusta según el tamaño de tu localidad (0.02 ≈ 2.2 km)
            viewbox = f"{lon_centro - delta},{lat_centro - delta},{lon_centro + delta},{lat_centro + delta}"
            logger.info(f"🔲 Viewbox (área de búsqueda): {viewbox}")
            
            # 3. Preparar la dirección y la consulta a OSM
            calle = calle_nombre.strip()
            numero_str = str(numero).strip()
            if numero_str.upper() != 'S/N' and numero_str:
                direccion = f"{calle} {numero_str}, {localidad_nombre}, Jalisco, México"
            else:
                direccion = f"{calle}, {localidad_nombre}, Jalisco, México"
            
            logger.info(f"🗺️ Buscando en OSM (restringido): '{direccion}'")
            
            user_agent = os.getenv('OSM_USER_AGENT', 'SIRMYN-Bot/1.0')
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': direccion,
                'format': 'json',
                'limit': 1,
                'countrycodes': 'mx',
                'viewbox': viewbox,
                'bounded': 1,
                'dedupe': 1
            }
            headers = {'User-Agent': user_agent}
            
            # 4. Ejecutar la búsqueda restringida
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    lat = float(data[0]['lat'])
                    lon = float(data[0]['lon'])
                    direccion_encontrada = data[0].get('display_name', 'N/A')
                    logger.info(f"✅✅✅ COORDENADAS EXACTAS ENCONTRADAS en '{localidad_nombre}': {lat}, {lon}")
                    logger.info(f"   Dirección OSM: {direccion_encontrada[:150]}...")
                    return lat, lon
                else:
                    logger.warning(f"⚠️ OSM no encontró '{calle} {numero_str}' DENTRO del área de '{localidad_nombre}'.")
            else:
                logger.error(f"❌ Error HTTP de OSM: {response.status_code}")
            
            # 5. Fallback: buscar solo la calle en la localidad
            logger.info("🔄 Intentando fallback: buscando solo la calle en la localidad...")
            params_fallback = params.copy()
            params_fallback['q'] = f"{calle}, {localidad_nombre}, Jalisco, México"
            response_fallback = requests.get(url, params=params_fallback, headers=headers, timeout=10)
            
            if response_fallback.status_code == 200 and response_fallback.json():
                data_fb = response_fallback.json()[0]
                lat_fb = float(data_fb['lat'])
                lon_fb = float(data_fb['lon'])
                logger.info(f"📍 Fallback: Usando coordenadas aproximadas de '{calle}' en '{localidad}': {lat_fb}, {lon_fb}")
                return lat_fb, lon_fb
            
            logger.error(f"❌ No se pudo geolocalizar la dirección en el área de '{localidad_nombre}'.")
            return None, None
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout al conectar con OpenStreetMap.")
        return None, None
    except requests.exceptions.ConnectionError:
        logger.error("❌ Error de conexión con OpenStreetMap.")
        return None, None
    except Exception as e:
        logger.error(f"❌ Error inesperado en 'obtener_coordenadas_osm': {e}", exc_info=True)
        return None, None


def obtener_direccion_osm(latitud, longitud):
    """
    Obtiene la dirección (reverse geocoding) a partir de coordenadas usando OSM.
    
    Args:
        latitud (float): Latitud
        longitud (float): Longitud
    
    Returns:
        dict o None: Diccionario con 'road' y 'localidad'
    """
    try:
        user_agent = os.getenv('OSM_USER_AGENT', 'SIRMYN-Bot/1.0')
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': latitud,
            'lon': longitud,
            'format': 'json',
            'zoom': 18,
            'addressdetails': 1
        }
        headers = {'User-Agent': user_agent}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            road = address.get('road', '')
            localidad = (
                address.get('neighbourhood') or
                address.get('suburb') or
                address.get('village') or
                address.get('town') or
                address.get('city')
            )
            if road and localidad:
                logger.info(f"📍 Reverse geocoding exitoso: {localidad}, {road}")
                return {'road': road, 'localidad': localidad}
        return None
    except Exception as e:
        logger.error(f"Error en obtener_direccion_osm: {e}")
        return None


def buscar_localidad_flexible(nombre_buscado):
    """
    Busca una localidad en la BD con coincidencia flexible.
    Retorna (id, nombre_oficial) o None.
    """
    if not nombre_buscado:
        return None
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Localidad
            from app.telegram.utils.normalize import _normalize_text
            
            # 1. Búsqueda exacta
            localidad = Localidad.query.filter(Localidad.nombre.ilike(nombre_buscado)).first()
            if localidad:
                return localidad.id, localidad.nombre
            
            # 2. Normalizar
            nombre_normalizado = _normalize_text(nombre_buscado)
            if not nombre_normalizado:
                return None
            
            todas = Localidad.query.all()
            for loc in todas:
                loc_normalizado = _normalize_text(loc.nombre)
                if loc_normalizado and (nombre_normalizado == loc_normalizado or
                                        nombre_normalizado in loc_normalizado or
                                        loc_normalizado in nombre_normalizado):
                    return loc.id, loc.nombre
            
            # 3. Palabras clave
            palabras_buscadas = set(nombre_normalizado.split())
            for loc in todas:
                loc_normalizado = _normalize_text(loc.nombre)
                palabras_loc = set(loc_normalizado.split())
                if len(palabras_buscadas.intersection(palabras_loc)) >= 2:
                    return loc.id, loc.nombre
            return None
    except Exception as e:
        logger.error(f"Error en buscar_localidad_flexible: {e}")
        return None


def buscar_calle_flexible(nombre_calle, localidad_id):
    """
    Busca una calle en la BD para una localidad específica.
    Retorna (id, nombre_oficial) o None.
    """
    if not nombre_calle or not localidad_id:
        return None
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Calle
            from app.telegram.utils.normalize import _normalize_text
            
            # 1. Búsqueda exacta
            calle = Calle.query.filter(Calle.nombre.ilike(nombre_calle),
                                       Calle.localidad_id == localidad_id).first()
            if calle:
                return calle.id, calle.nombre
            
            # 2. Búsqueda flexible
            nombre_normalizado = _normalize_text(nombre_calle)
            if not nombre_normalizado:
                return None
            
            calles = Calle.query.filter_by(localidad_id=localidad_id).all()
            for c in calles:
                c_normalizado = _normalize_text(c.nombre)
                if c_normalizado and (nombre_normalizado == c_normalizado or
                                      nombre_normalizado in c_normalizado or
                                      c_normalizado in nombre_normalizado):
                    return c.id, c.nombre
            return None
    except Exception as e:
        logger.error(f"Error en buscar_calle_flexible: {e}")
        return None
