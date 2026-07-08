from telegram import Update
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
from app.telegram.utils import actualizar_timestamp_usuario, user_data
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def estado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            from app.models.team import Team
            from app.models.user import User
            
            # Obtener todos los reportes del usuario (por teléfono = telegram_id)
            reportes = Report.query.filter_by(telefono=str(user_id)).order_by(Report.timestamp.desc()).all()
            
            if not reportes:
                await update.message.reply_text(
                    "📭 *No tienes reportes registrados.*\n\n"
                    "Para crear uno, usa /start",
                    parse_mode="Markdown"
                )
                return
            
            # Filtrar solo los que NO están finalizados ni cancelados (opcional)
            estados_finales = ['Finalizado', 'Cancelado', 'Aceptado por usuario', 'Rechazado por usuario']
            reportes_activos = []
            reportes_finalizados = []
            
            for rep in reportes:
                asignacion = Assignment.query.filter_by(
                    report_id=rep.id
                ).order_by(Assignment.timestamp.desc()).first()
                estado_desc = asignacion.status.descripcion if asignacion and asignacion.status else "Sin estado"
                
                if estado_desc in estados_finales:
                    reportes_finalizados.append((rep, estado_desc))
                else:
                    reportes_activos.append((rep, estado_desc))
            
            # Construir mensaje
            mensaje = f"📋 *Tus reportes ({len(reportes)} totales)*\n\n"
            
            if reportes_activos:
                mensaje += "*🔴 Activos (pendientes):*\n"
                for i, (rep, estado) in enumerate(reportes_activos[:5], 1):
                    fecha = rep.timestamp.strftime('%d/%m %H:%M') if rep.timestamp else 'N/D'
                    mensaje += f"{i}. *#{rep.id}* - {rep.tipo}\n"
                    mensaje += f"   📍 {rep.calle.nombre if rep.calle else 'N/D'} #{rep.numero}\n"
                    mensaje += f"   🏷️ {estado} | ⏰ {fecha}\n\n"
                
                if len(reportes_activos) > 5:
                    mensaje += f"📝 ... y {len(reportes_activos) - 5} activos más\n\n"
            else:
                mensaje += "✅ *No tienes reportes activos.*\n\n"
            
            if reportes_finalizados:
                mensaje += "*✅ Finalizados:*\n"
                for rep, estado in reportes_finalizados[:3]:
                    fecha = rep.timestamp.strftime('%d/%m %H:%M') if rep.timestamp else 'N/D'
                    mensaje += f"• #{rep.id} - {rep.tipo} ({fecha}) - {estado}\n"
                
                if len(reportes_finalizados) > 3:
                    mensaje += f"📝 ... y {len(reportes_finalizados) - 3} más\n"
            
            mensaje += "\n💡 *Para ver detalles de un reporte:* /estado #ID (ej: /estado 123)"
            
            await update.message.reply_text(mensaje, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"❌ Error en /estado: {e}", exc_info=True)
        await update.message.reply_text("❌ Error al obtener tus reportes. Intenta más tarde.")
