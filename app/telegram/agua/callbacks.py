import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from app.telegram.common.utils import user_data
from app.telegram.agua.keyboards import SUBTIPOS_AGUA, SUBTIPOS_DRENAJE

logger = logging.getLogger(__name__)

async def agua_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los callbacks de Agua/Drenaje"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data.startswith("agua_asignar_"):
        reporte_id = int(callback_data.split("_")[-1])
        await mostrar_cuadrillas_agua(query, reporte_id)
    
    elif callback_data.startswith("agua_asignarc_"):
        partes = callback_data.split("_")
        reporte_id = int(partes[2])
        team_id = int(partes[3])
        await asignar_cuadrilla_agua(query, reporte_id, team_id)

async def mostrar_cuadrillas_agua(query, reporte_id):
    """Muestra las cuadrillas de agua disponibles"""
    try:
        from app.services.db_manager import DatabaseManager
        from app.models.team import Team
        
        app = DatabaseManager.get_app()
        with app.app_context():
            cuadrillas_agua = Team.query.filter_by(area='agua').all()
            
            if not cuadrillas_agua:
                await query.edit_message_text("❌ No hay cuadrillas de agua disponibles.")
                return
            
            keyboard = []
            for cuadrilla in cuadrillas_agua:
                keyboard.append([
                    InlineKeyboardButton(
                        f"👷 {cuadrilla.nombre}",
                        callback_data=f"agua_asignarc_{reporte_id}_{cuadrilla.id}"
                    )
                ])
            
            await query.edit_message_text(
                f"👷 *Asignar reporte #{reporte_id}*\n\nSelecciona una cuadrilla de agua:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        logger.error(f"❌ Error en mostrar_cuadrillas_agua: {e}")

async def asignar_cuadrilla_agua(query, reporte_id, team_id):
    """Asigna una cuadrilla de agua al reporte"""
    try:
        from app.services.db_manager import DatabaseManager
        from app.models.report import Report, Assignment
        from app.models.status import Status
        from app.extensions import db
        from datetime import datetime
        
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            cuadrilla = Team.query.get(team_id)
            
            if not reporte or not cuadrilla:
                await query.edit_message_text("❌ Datos no válidos.")
                return
            
            status_asignado = Status.query.filter_by(descripcion="Asignado").first()
            if not status_asignado:
                status_asignado = Status(descripcion="Asignado")
                db.session.add(status_asignado)
                db.session.commit()
            
            nueva_asignacion = Assignment(
                report_id=reporte_id,
                team_id=team_id,
                status_id=status_asignado.id,
                timestamp=datetime.utcnow(),
                observaciones=f"Asignado a {cuadrilla.nombre}"
            )
            db.session.add(nueva_asignacion)
            db.session.commit()
            
            await query.edit_message_text(
                f"✅ *Reporte #{reporte_id} asignado*\n\n"
                f"👷 *Cuadrilla:* {cuadrilla.nombre}\n"
                f"📅 *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Reporte {reporte_id} asignado a cuadrilla {cuadrilla.nombre}")
            
    except Exception as e:
        logger.error(f"❌ Error en asignar_cuadrilla_agua: {e}")
        await query.edit_message_text("❌ Error al asignar cuadrilla.")
