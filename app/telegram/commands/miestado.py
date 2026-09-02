from telegram import Update
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

async def miestado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            from app.models.report import Report, Assignment
            
            usuario = User.query.filter_by(telegram_id=str(user_id)).first()
            
            if not usuario:
                await update.message.reply_text(
                    "❌ No tienes una cuenta vinculada.\n"
                    "Usa /registrar para vincular tu cuenta primero.",
                    parse_mode="Markdown"
                )
                return
            
            desde = datetime.utcnow() - timedelta(hours=24)
            
            reportes_asignados = Report.query.join(Assignment).filter(
                Assignment.team_id == usuario.team_id,
                Report.timestamp >= desde
            ).order_by(Report.timestamp.desc()).all()
            
            mensaje = (
                f"👷 *Estado de {usuario.nombre}*\n\n"
                f"*Username:* {usuario.username}\n"
                f"*Cuadrilla:* {usuario.team.nombre if usuario.team else 'Sin asignar'}\n\n"
                f"*Reportes asignados (últimas 24h):* {len(reportes_asignados)}\n\n"
            )
            
            if reportes_asignados:
                for i, reporte in enumerate(reportes_asignados[:5], 1):
                    asignacion = Assignment.query.filter_by(
                        report_id=reporte.id
                    ).order_by(Assignment.timestamp.desc()).first()
                    status = asignacion.status if asignacion else None
                    mensaje += (
                        f"{i}. *#{reporte.id}* - {reporte.tipo}\n"
                        f"   📍 {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
                        f"   🏷️ {status.descripcion if status else 'Sin estatus'}\n"
                        f"   ⏰ {reporte.timestamp.strftime('%H:%M') if reporte.timestamp else ''}\n\n"
                    )
                
                if len(reportes_asignados) > 5:
                    mensaje += f"... y {len(reportes_asignados) - 5} más\n"
            else:
                mensaje += "📭 No hay reportes asignados recientemente.\n"
            
            await update.message.reply_text(mensaje, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"❌ Error en /miestado: {e}")
        await update.message.reply_text("❌ Error al obtener estado. Intenta más tarde.")
