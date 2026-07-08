"""
Utilidades de base de datos para emergencias
Integración con tu sistema existente
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def get_database_manager():
    """
    Obtiene el DatabaseManager de tu sistema existente
    Para evitar importaciones circulares
    """
    try:
        # Intenta importar tu DatabaseManager existente
        from app.services.telegram_bot import DatabaseManager
        return DatabaseManager
    except ImportError:
        logger.warning("⚠️ No se encontró DatabaseManager en telegram_bot")
        return None


def buscar_localidad_flexible_emergencia(nombre_buscado: str) -> Optional[Tuple[int, str]]:
    """
    Versión OPTIMIZADA para emergencias de tu función original
    Busca localidad pero con timeout corto para no retrasar emergencias
    """
    try:
        DatabaseManager = get_database_manager()
        if not DatabaseManager:
            return None
        
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models import Localidad
            
            # BÚSQUEDA RÁPIDA - máximo 2 intentos
            # 1. Búsqueda exacta (más rápida)
            localidad = Localidad.query.filter(
                Localidad.nombre.ilike(nombre_buscado)
            ).first()
            
            if localidad:
                return localidad.id, localidad.nombre
            
            # 2. Búsqueda por inicio (segunda opción rápida)
            if len(nombre_buscado) > 3:
                localidad = Localidad.query.filter(
                    Localidad.nombre.ilike(f"{nombre_buscado}%")
                ).first()
                
                if localidad:
                    return localidad.id, localidad.nombre
            
            # En emergencias, NO hacemos búsquedas flexibles lentas
            # Mejor devolver None y usar lo del GPS directamente
            return None
            
    except Exception as e:
        logger.error(f"❌ Error en buscar_localidad_flexible_emergencia: {e}")
        return None


def buscar_calle_flexible_emergencia(nombre_calle: str, localidad_id: int) -> Optional[Tuple[int, str]]:
    """
    Versión OPTIMIZADA para emergencias
    Si no encuentra, NO CREA NADA (más rápido)
    """
    try:
        DatabaseManager = get_database_manager()
        if not DatabaseManager:
            return None
        
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models import Calle
            
            # Solo búsqueda exacta (más rápida)
            calle = Calle.query.filter(
                Calle.nombre.ilike(nombre_calle),
                Calle.localidad_id == localidad_id
            ).first()
            
            if calle:
                return calle.id, calle.nombre
            
            # En emergencias, NO creamos nuevas calles
            return None
            
    except Exception as e:
        logger.error(f"❌ Error en buscar_calle_flexible_emergencia: {e}")
        return None


def guardar_emergencia_en_db(datos_emergencia: dict) -> Optional[int]:
    """
    Guarda una emergencia en la base de datos
    Retorna el ID de la emergencia guardada o None si falla
    """
    try:
        DatabaseManager = get_database_manager()
        if not DatabaseManager:
            logger.error("❌ No se pudo obtener DatabaseManager")
            return None
        
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.emergency import Emergency
            from app.extensions import db
            
            # Crear instancia de Emergency
            emergencia = Emergency(
                municipio_id=datos_emergencia.get('municipio_id', 1),
                municipio_nombre=datos_emergencia.get('municipio_nombre', 'SIRMYN'),
                tipo=datos_emergencia.get('tipo_emergencia'),
                subtipo=datos_emergencia.get('subtipo', ''),
                latitud=datos_emergencia.get('latitud'),
                longitud=datos_emergencia.get('longitud'),
                direccion_aproximada=datos_emergencia.get('direccion_aproximada', ''),
                reportante=datos_emergencia.get('nombre_reporte'),
                telegram_user_id=datos_emergencia.get('user_id'),
                telegram_username=datos_emergencia.get('username'),
                descripcion=datos_emergencia.get('descripcion', ''),
                nivel_urgencia=datos_emergencia.get('nivel_urgencia', 3),
                personas_heridas=datos_emergencia.get('personas_heridas', False),
                personas_atrapadas=datos_emergencia.get('personas_atrapadas', False),
                peligro_vida=datos_emergencia.get('peligro_critico', False),
                status='reportada'
            )
            
            db.session.add(emergencia)
            db.session.commit()
            
            # Actualizar folio público con el ID real
            emergencia.folio_publico = f"E-{emergencia.timestamp_reporte.year}-{emergencia.id:05d}"
            db.session.commit()
            
            logger.info(f"✅ Emergencia guardada en BD: #{emergencia.id} - {emergencia.folio_publico}")
            return emergencia.id
            
    except Exception as e:
        logger.error(f"❌ Error guardando emergencia en BD: {e}")
        return None