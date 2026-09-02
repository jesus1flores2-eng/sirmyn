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

def actualizar_ubicaciones_gps():
    """Tarea programada: actualiza ubicaciones GPS cada 30 segundos"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.services.tracksolid_service import TrackSolidService
            from app.models.gps_dispositivo import GpsDispositivo
            from app.extensions import db
            
            service = TrackSolidService()
            ubicaciones = service.obtener_ubicaciones()
            
            if not ubicaciones:
                return
            
            for ubicacion in ubicaciones:
                dispositivo = GpsDispositivo.query.filter_by(imei=ubicacion['imei']).first()
                if dispositivo:
                    dispositivo.ultima_latitud = ubicacion['latitud']
                    dispositivo.ultima_longitud = ubicacion['longitud']
                    dispositivo.ultima_velocidad = ubicacion['velocidad']
                    dispositivo.ultima_actualizacion = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"✅ {len(ubicaciones)} ubicaciones GPS actualizadas")
            
    except Exception as e:
        logger.error(f"❌ Error actualizando GPS: {e}")
        
async def verificar_vencimiento_gps():
    """Verifica planes de GPS próximos a vencer y notifica al jefe de área"""
    try:
        from datetime import datetime, timedelta
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.gps_dispositivo import GpsDispositivo
            from app.models.user import User
            from app.routes.telegram_routes import get_telegram_app
            
            hoy = datetime.utcnow().date()
            en_2_dias = hoy + timedelta(days=2)
            
            dispositivos = GpsDispositivo.query.filter(
                GpsDispositivo.fecha_vencimiento.isnot(None)
            ).all()
            
            for d in dispositivos:
                if d.fecha_vencimiento and d.fecha_vencimiento <= en_2_dias:
                    area = d.team.area if d.team else None
                    if area:
                        jefe = User.query.filter_by(area=area, rol_especifico='jefe_area', is_active=True).first()
                        if not jefe:
                            jefe = User.query.filter_by(area=area, rol_especifico='director', is_active=True).first()
                        
                        if jefe and jefe.telegram_id:
                            dias_restantes = (d.fecha_vencimiento - hoy).days
                            urgencia = "🚨 HOY" if dias_restantes <= 0 else f"⚠️ en {dias_restantes} días"
                            
                            mensaje = (
                                f"📡 *ALERTA DE GPS - VENCIMIENTO {urgencia}*\n\n"
                                f"*Dispositivo:* {d.nombre}\n"
                                f"*IMEI:* `{d.imei}`\n"
                                f"*Cuadrilla:* {d.team.nombre if d.team else 'Sin asignar'}\n"
                                f"*Teléfono chip:* {d.telefono_chip or 'No registrado'}\n"
                                f"*Plan:* {d.plan_datos or 'No especificado'}\n"
                                f"*Vence:* {d.fecha_vencimiento.strftime('%d/%m/%Y')}\n\n"
                                f"📞 *Acción:* Realizar recarga antes del vencimiento."
                            )
                            
                            try:
                                bot_app = get_telegram_app()
                                await bot_app.bot.send_message(
                                    chat_id=int(jefe.telegram_id),
                                    text=mensaje,
                                    parse_mode="Markdown"
                                )
                                logger.info(f"✅ Alerta GPS enviada a {jefe.nombre} por {d.nombre}")
                            except Exception as e:
                                logger.error(f"Error enviando alerta GPS: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error en verificar_vencimiento_gps: {e}")
