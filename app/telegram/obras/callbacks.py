from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def jefe_obras_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass
    callback_data = query.data
    if not callback_data.startswith('obras_') or not callback_data.startswith(('obras_validar_', 'obras_rechazar_')): return
    partes = callback_data.split('_')
    if len(partes) < 3: await query.answer("❌ Formato inválido", show_alert=True); return
    accion = partes[1]; reporte_id = int(partes[2])
    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(query.from_user.id), area='obras', is_active=True).first()
        if not usuario or usuario.rol_especifico not in ['jefe_area', 'director']: await query.edit_message_text("❌ No autorizado."); return
        reporte = Report.query.get(reporte_id)
        if not reporte: await query.edit_message_text("❌ Reporte no encontrado."); return
        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if not asignacion: await query.edit_message_text("❌ No hay asignación."); return
        cuadrilla = Team.query.get(asignacion.team_id)
        if accion == 'validar':
            estado_finalizado = Status.query.filter_by(descripcion="Finalizado").first()
            if not estado_finalizado: estado_finalizado = Status(descripcion="Finalizado"); db.session.add(estado_finalizado); db.session.commit()
            asignacion.status_id = estado_finalizado.id; asignacion.observaciones = f"Validado por Jefe de Obras {usuario.nombre}"; db.session.commit()
            await query.message.reply_text(f"✅ *VALIDADO POR JEFE DE OBRAS*\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n👷 Cuadrilla: {cuadrilla.nombre if cuadrilla else 'N/D'}\n🏷️ Estado: Finalizado ✓", parse_mode=ParseMode.MARKDOWN)
            from app.services.notification_service import notificar_usuario_reporte_finalizado
            await notificar_usuario_reporte_finalizado(reporte, asignacion, "Jefe de Obras")
            await query.answer("✅ Reparación validada", show_alert=False)
        elif accion == 'rechazar':
            user_data[query.from_user.id] = {'modo_esperando_motivo_rechazo_obras': True, 'reporte_id': reporte_id, 'cuadrilla_id': asignacion.team_id, 'cuadrilla_nombre': cuadrilla.nombre if cuadrilla else 'Cuadrilla desconocida'}
            await query.edit_message_text(text=f"❌ *RECHAZO - Reporte #{reporte_id}*\n\nEscribe el *motivo del rechazo*:", parse_mode=ParseMode.MARKDOWN, reply_markup=None)
            await query.answer("⚠️ Escribe el motivo", show_alert=False)


async def manejar_motivo_rechazo_jefe_obras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id; motivo = update.message.text.strip()
    datos = user_data.get(user_id, {}); reporte_id = datos.get('reporte_id'); cuadrilla_id = datos.get('cuadrilla_id'); cuadrilla_nombre = datos.get('cuadrilla_nombre', 'Cuadrilla desconocida')
    if not reporte_id: await update.message.reply_text("❌ No se encontró el reporte."); limpiar_estado(user_id); return
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte: await update.message.reply_text("❌ Reporte no encontrado."); limpiar_estado(user_id); return
            jefe = User.query.filter_by(telegram_id=str(user_id)).first(); nombre_jefe = jefe.nombre if jefe else "Jefe de Obras"
            estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
            if not estado_en_proceso: estado_en_proceso = Status(descripcion="En proceso"); db.session.add(estado_en_proceso); db.session.commit()
            asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
            if asignacion: asignacion.status_id = estado_en_proceso.id; asignacion.observaciones = f"Rechazado por Jefe de Obras. Motivo: {motivo}"; db.session.commit()
            bot = context.bot; calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'; localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            for usuario in User.query.filter_by(team_id=cuadrilla_id, is_active=True).all():
                if usuario.telegram_id:
                    try:
                        mensaje = f"🚨 *REPORTE RECHAZADO*\n━━━━━━━━━━━━━━━━━━━━━━\n\n📋 *Folio:* #{reporte.id}\n📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n👤 *Reportante:* {reporte.reportante}\n🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n\n❌ *RECHAZADO POR JEFE DE OBRAS*\n*Motivo:* {motivo}\n\n*📌 Acción requerida:* Corrige y vuelve a subir evidencia.\n\n*📋 Acciones rápidas:*"
                        await bot.send_message(chat_id=int(usuario.telegram_id), text=mensaje, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔧 Subir evidencia reparación", callback_data=f"reparacion_{reporte_id}")]]))
                    except Exception as e: logger.error(f"❌ Error: {e}")
            await update.message.reply_text(f"✅ *Rechazo enviado*\n📋 Reporte: #{reporte.id}\n👷 Cuadrilla: {cuadrilla_nombre}\n📝 Motivo: {motivo}", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    except Exception as e: logger.error(f"❌ Error: {e}"); await update.message.reply_text("❌ Error al procesar el rechazo.")
    finally: limpiar_estado(user_id)
