"""
Configuración del scheduler para tareas programadas
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

logger = logging.getLogger(__name__)

def iniciar_scheduler():
    """
    Inicia el scheduler con las tareas programadas.
    Se ejecuta al iniciar la aplicación Flask.
    """
    try:
        scheduler = BackgroundScheduler()
        
        # ⭐ Tarea cada 4 horas: Revisar reportes urgentes
        from app.tasks import revisar_reportes_urgentes
        
        scheduler.add_job(
            func=revisar_reportes_urgentes,
            trigger=IntervalTrigger(minutes=1),
            id='revisar_reportes_urgentes',
            name='Revisar reportes urgentes (>48hrs)',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("✅ Scheduler iniciado correctamente (cada 4 horas)")
        return scheduler
        
    except Exception as e:
        logger.error(f"❌ Error iniciando scheduler: {e}")
        return None
