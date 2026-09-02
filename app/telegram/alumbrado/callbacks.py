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


async def jefe_alumbrado_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    callback_data = query.data

    if not callback_data.startswith('alumbrado_'):
        return
    if not callback_data.startswith(('alumbrado_validar_', 'alumbrado_rechazar_')):
        return

    partes = callback_data.split('_')
    if len(partes) < 3:
        await query.answer("❌ Formato inválido", show_alert=True)
        return

    accion = partes[1]
    reporte_id = int(partes[2])

    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(query.from_user.id), area='alumbrado', is_active=True).first()
        if not usuario or usuario.rol_especifico not in ['jefe_area', 'director']:
            await query.edit_message_text("❌ No autorizado.")
            return

        reporte = Report.query.get(reporte_id)
        if not reporte:
            await query.edit_message_text("❌ Reporte no encontrado.")
            return

        asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
        if not asignacion:
            await query.edit_message_text("❌ No hay asignación.")
            return

        cuadrilla = Team.query.get(asignacion.team_id)

        if accion == 'validar':
            estado_finalizado = Status.query.filter_by(descripcion="Finalizado").first()
            if not estado_finalizado:
                estado_finalizado = Status(descripcion="Finalizado")
                db.session.add(estado_finalizado)
                db.session.commit()

            asignacion.status_id = estado_finalizado.id
            asignacion.observaciones = f"Validado por Jefe de Alumbrado {usuario.nombre} el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()

            await query.message.reply_text(
                f"✅ *VALIDADO POR JEFE DE ALUMBRADO*\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n👷 Cuadrilla: {cuadrilla.nombre if cuadrilla else 'N/D'}\n🏷️ Estado: Finalizado ✓",
                parse_mode=ParseMode.MARKDOWN
            )

            from app.services.notification_service import notificar_usuario_reporte_finalizado
            await notificar_usuario_reporte_finalizado(reporte, asignacion, "Jefe de Alumbrado")
            logger.info(f"✅ Jefe de Alumbrado validó reporte #{reporte_id}")
            await query.answer("✅ Reparación validada", show_alert=False)

        elif accion == 'rechazar':
            user_data[query.from_user.id] = {
                'modo_esperando_motivo_rechazo_alumbrado': True,
                'reporte_id': reporte_id,
                'cuadrilla_id': asignacion.team_id,
                'cuadrilla_nombre': cuadrilla.nombre if cuadrilla else 'Cuadrilla desconocida'
            }
            await query.edit_message_text(
                text=f"❌ *RECHAZO DE REPARACIÓN - Reporte #{reporte_id}*\n\nEscribe el *motivo del rechazo*:\n\n📌 *El reporte volverá a estado 'En proceso'.*",
                parse_mode=ParseMode.MARKDOWN, reply_markup=None
            )
            logger.info(f"❌ Jefe de Alumbrado inició rechazo para reporte #{reporte_id}")
            await query.answer("⚠️ Escribe el motivo del rechazo", show_alert=False)


async def manejar_motivo_rechazo_jefe_alumbrado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    motivo = update.message.text.strip()
    datos = user_data.get(user_id, {})
    reporte_id = datos.get('reporte_id')
    cuadrilla_id = datos.get('cuadrilla_id')
    cuadrilla_nombre = datos.get('cuadrilla_nombre', 'Cuadrilla desconocida')

    if not reporte_id:
        await update.message.reply_text("❌ No se encontró el reporte.")
        limpiar_estado(user_id)
        return

    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await update.message.reply_text("❌ Reporte no encontrado.")
                limpiar_estado(user_id)
                return

            jefe = User.query.filter_by(telegram_id=str(user_id)).first()
            nombre_jefe = jefe.nombre if jefe else "Jefe de Alumbrado"

            estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
            if not estado_en_proceso:
                estado_en_proceso = Status(descripcion="En proceso")
                db.session.add(estado_en_proceso)
                db.session.commit()

            asignacion = Assignment.query.filter_by(report_id=reporte_id).order_by(Assignment.timestamp.desc()).first()
            if asignacion:
                asignacion.status_id = estado_en_proceso.id
                asignacion.observaciones = f"Rechazado por Jefe de Alumbrado {nombre_jefe}. Motivo: {motivo}"
                db.session.commit()

            bot = context.bot
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id, is_active=True).all()
            for usuario in usuarios_cuadrilla:
                if usuario.telegram_id:
                    try:
                        mensaje = (
                            f"🚨 *REPORTE RECHAZADO - REQUIERE CORRECCIÓN*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"📋 *Folio:* #{reporte.id}\n📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                            f"👤 *Reportante:* {reporte.reportante}\n🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n\n"
                            f"❌ *RECHAZADO POR JEFE DE ALUMBRADO*\n*Motivo:* {motivo}\n\n"
                            f"*📌 Acción requerida:* Corrige y vuelve a subir evidencia.\n\n*📋 Acciones rápidas:*"
                        )
                        keyboard = [[InlineKeyboardButton("🔧 Subir evidencia reparación", callback_data=f"reparacion_{reporte_id}")]]
                        await bot.send_message(chat_id=int(usuario.telegram_id), text=mensaje, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
                    except Exception as e:
                        logger.error(f"❌ Error: {e}")

            await update.message.reply_text(f"✅ *Rechazo enviado*\n📋 Reporte: #{reporte.id}\n👷 Cuadrilla: {cuadrilla_nombre}\n📝 Motivo: {motivo}", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
            logger.info(f"✅ Jefe de Alumbrado rechazó reporte #{reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        await update.message.reply_text("❌ Error al procesar el rechazo.")
    finally:
        limpiar_estado(user_id)
