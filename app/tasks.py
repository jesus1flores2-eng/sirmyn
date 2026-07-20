"""
Tareas programadas para el sistema SIRMYN
"""
import logging
from datetime import datetime, timedelta
from app.services.db_manager import DatabaseManager
from app.services.notification_service import notificar_presidente_urgente
from app.extensions import db
import asyncio

logger = logging.getLogger(__name__)

def revisar_reportes_urgentes():
    """
    Revisa reportes que llevan más de 48 horas sin asignar.
    Notifica al presidente si no han sido notificados previamente.
    """
    try:
        logger.info("🔍 [TAREA] Revisando reportes urgentes (>48 hrs sin asignar)")
        
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            
            # Obtener estado "Sin asignar"
            estado_sin_asignar = Status.query.filter_by(descripcion="Sin Asignar").first()
            if not estado_sin_asignar:
                logger.warning("⚠️ Estado 'Sin Asignar' no encontrado")
                return
            
            # Buscar reportes >48 hrs sin asignar que NO han sido notificados
            hace_48_hrs = datetime.utcnow() - timedelta(hours=48)
            
            # Obtener IDs de reportes con asignación "Sin Asignar" (última asignación)
            from sqlalchemy import func, and_
            
            # Subconsulta: última asignación de cada reporte
            subq = db.session.query(
                Assignment.report_id,
                func.max(Assignment.timestamp).label('max_ts')
            ).filter(
                Assignment.report_id.isnot(None)
            ).group_by(Assignment.report_id).subquery()
            
            # Últimas asignaciones
            ultimas_asignaciones = Assignment.query.join(
                subq,
                and_(
                    Assignment.report_id == subq.c.report_id,
                    Assignment.timestamp == subq.c.max_ts
                )
            ).filter(
                Assignment.status_id == estado_sin_asignar.id
            ).all()
            
            reportes_sin_asignar_ids = [a.report_id for a in ultimas_asignaciones]
            
            # Reportes >48 hrs, sin asignar, no notificados
            reportes_urgentes = Report.query.filter(
                Report.id.in_(reportes_sin_asignar_ids),
                Report.timestamp < hace_48_hrs,
                Report.notificado_presidente == False
            ).all()
            
            if not reportes_urgentes:
                logger.info("✅ [TAREA] No hay reportes urgentes pendientes")
                return
            
            logger.info(f"⚠️ [TAREA] Encontrados {len(reportes_urgentes)} reportes urgentes")
            
            # Notificar al presidente por cada reporte
            async def notificar_todos():
                for reporte in reportes_urgentes:
                    try:
                        await notificar_presidente_urgente(reporte.id)
                        logger.info(f"✅ [TAREA] Notificado presidente sobre reporte #{reporte.id}")
                    except Exception as e:
                        logger.error(f"❌ [TAREA] Error notificando reporte #{reporte.id}: {e}")
            
            # Ejecutar notificaciones
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(notificar_todos())
            loop.close()
            
            logger.info(f"✅ [TAREA] Procesados {len(reportes_urgentes)} reportes urgentes")
            
    except Exception as e:
        logger.error(f"❌ [TAREA] Error en revisar_reportes_urgentes: {e}", exc_info=True)
