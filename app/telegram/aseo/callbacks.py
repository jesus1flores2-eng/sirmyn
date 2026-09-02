# app/telegram/aseo/callbacks.py
# Callbacks exclusivos del departamento de Aseo Público
# Validación del Jefe de Área (equivalente al supervisor en Agua)

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


async def jefe_aseo_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del Jefe de Área de Aseo (validar/rechazar reparación)"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    callback_data = query.data

    if not callback_data.startswith('aseo_'):
        return

    if not callback_data.startswith(('aseo_validar_', 'aseo_rechazar_')):
        logger.info(f"⏩ Callback {callback_data} ignorado por jefe_aseo_callback_handler")
        return

    partes = callback_data.split('_')
    if len(partes) < 3:
        await query.answer("❌ Formato inválido", show_alert=True)
        return

    accion = partes[1]
    reporte_id = int(partes[2])

    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(
            telegram_id=str(query.from_user.id),
            area='aseo',
            is_active=True
        ).first()

        if not usuario or usuario.rol_especifico not in ['jefe_area', 'director']:
            await query.edit_message_text("❌ No autorizado.")
            return

        reporte = Report.query.get(reporte_id)
        if not reporte:
            await query.edit_message_text("❌ Reporte no encontrado.")
            return

        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()

        if not asignacion:
            await query.edit_message_text("❌ No hay asignación para este reporte.")
            return

        cuadrilla = Team.query.get(asignacion.team_id)

        # VALIDAR
        if accion == 'validar':
            estado_finalizado = Status.query.filter_by(descripcion="Finalizado").first()
            if not estado_finalizado:
                estado_finalizado = Status(descripcion="Finalizado")
                db.session.add(estado_finalizado)
                db.session.commit()

            asignacion.status_id = estado_finalizado.id
            asignacion.observaciones = f"Validado por Jefe de Área de Aseo {usuario.nombre} el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()

            await query.message.reply_text(
                f"✅ *VALIDADO POR JEFE DE ASEO*\n"
                f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                f"👷 Cuadrilla: {cuadrilla.nombre if cuadrilla else 'N/D'}\n"
                f"🏷️ Estado: Finalizado ✓",
                parse_mode=ParseMode.MARKDOWN
            )

            from app.services.notification_service import notificar_usuario_reporte_finalizado
            await notificar_usuario_reporte_finalizado(reporte, asignacion, "Jefe de Área de Aseo")

            logger.info(f"✅ Jefe de Aseo {usuario.nombre} validó reporte #{reporte_id}")
            await query.answer("✅ Reparación validada", show_alert=False)

        # RECHAZAR
        elif accion == 'rechazar':
            user_data[query.from_user.id] = {
                'modo_esperando_motivo_rechazo_aseo': True,
                'reporte_id': reporte_id,
                'cuadrilla_id': asignacion.team_id,
                'cuadrilla_nombre': cuadrilla.nombre if cuadrilla else 'Cuadrilla desconocida'
            }

            await query.edit_message_text(
                text=f"❌ *RECHAZO DE REPARACIÓN - Reporte #{reporte_id}*\n\n"
                     f"Escribe el *motivo del rechazo*:\n"
                     f"(Ej: 'Falta recoger escombros en la esquina')\n\n"
                     f"📌 *El reporte volverá a estado 'En proceso' para que la cuadrilla corrija.*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=None
            )

            logger.info(f"❌ Jefe de Aseo {usuario.nombre} inició rechazo para reporte #{reporte_id}")
            await query.answer("⚠️ Escribe el motivo del rechazo", show_alert=False)


async def manejar_motivo_rechazo_jefe_aseo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el motivo de rechazo escrito por el Jefe de Área de Aseo."""
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

            jefe_aseo = User.query.filter_by(telegram_id=str(user_id)).first()
            nombre_jefe = jefe_aseo.nombre if jefe_aseo else "Jefe de Área de Aseo"

            estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
            if not estado_en_proceso:
                estado_en_proceso = Status(descripcion="En proceso")
                db.session.add(estado_en_proceso)
                db.session.commit()

            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            if asignacion:
                asignacion.status_id = estado_en_proceso.id
                asignacion.observaciones = f"Rechazado por Jefe de Aseo {nombre_jefe} el {datetime.now().strftime('%d/%m/%Y %H:%M')}. Motivo: {motivo}"
                db.session.commit()

            bot = context.bot
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

            # Notificar a la cuadrilla SOLO con botón de subir evidencia
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id, is_active=True).all()
            notificados = 0
            for usuario in usuarios_cuadrilla:
                if usuario.telegram_id:
                    try:
                        mensaje_cuadrilla = (
                            f"🚨 *REPORTE RECHAZADO - REQUIERE CORRECCIÓN*\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"📋 *Folio:* #{reporte.id}\n"
                            f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                            f"📞 *Reportante:* {reporte.reportante}\n"
                            f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
                            f"📄 *Descripción:* {reporte.descripcion_problema[:150]}...\n\n"
                            f"❌ *RECHAZADO POR JEFE DE ASEO*\n"
                            f"*Motivo:* {motivo}\n\n"
                            f"*📌 Acción requerida:* Corrige el trabajo y vuelve a subir evidencia.\n\n"
                            f"*📋 Acciones rápidas:*"
                        )

                        keyboard_simple = [[
                            InlineKeyboardButton(
                                "🔧 Subir evidencia reparación",
                                callback_data=f"reparacion_{reporte_id}"
                            )
                        ]]
                        reply_markup = InlineKeyboardMarkup(keyboard_simple)

                        await bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje_cuadrilla,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup
                        )
                        notificados += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario.nombre}: {e}")

            await update.message.reply_text(
                f"✅ *Rechazo enviado correctamente*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"👷 *Cuadrilla notificada:* {cuadrilla_nombre}\n"
                f"📝 *Motivo:* {motivo}\n\n"
                f"*📌 El reporte ha vuelto a estado 'En proceso'*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )

            logger.info(f"✅ Jefe de Aseo {nombre_jefe} rechazó reporte #{reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_motivo_rechazo_jefe_aseo: {e}")
        await update.message.reply_text("❌ Error al procesar el rechazo.")

    finally:
        limpiar_estado(user_id)
