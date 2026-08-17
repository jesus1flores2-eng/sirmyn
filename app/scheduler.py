"""
Configuración del scheduler para tareas programadas
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncio
import logging

logger = logging.getLogger(__name__)

def iniciar_scheduler():
    try:
        scheduler = BackgroundScheduler()
        
        from app.tasks import revisar_reportes_urgentes, actualizar_ubicaciones_gps, verificar_vencimiento_gps
        
        # Wrapper para función async
        def wrapper_verificar_gps():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verificar_vencimiento_gps())
            loop.close()
        
        scheduler.add_job(
            func=revisar_reportes_urgentes,
            trigger=IntervalTrigger(hours=4),
            id='revisar_reportes_urgentes',
            name='Revisar reportes urgentes (>48hrs)',
            replace_existing=True
        )
        
        scheduler.add_job(
            func=actualizar_ubicaciones_gps,
            trigger=IntervalTrigger(seconds=30),
            id='actualizar_gps',
            name='Actualizar ubicaciones GPS',
            replace_existing=True
        )
        
        scheduler.add_job(
            func=wrapper_verificar_gps,  # ⭐ Usar wrapper
            trigger=IntervalTrigger(hours=24),
            id='verificar_vencimiento_gps',
            name='Alertas de vencimiento de planes GPS',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("✅ Scheduler iniciado correctamente")
        return scheduler
    except Exception as e:
        logger.error(f"❌ Error iniciando scheduler: {e}")
        return None
