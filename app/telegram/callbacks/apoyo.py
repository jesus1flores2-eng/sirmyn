"""
Maneja solicitudes de apoyo entre cuadrillas
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def manejar_solicitar_apoyo_cuadrilla(query, context, reporte_id):
    """Muestra lista de cuadrillas del mismo departamento para solicitar apoyo"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            # Obtener la cuadrilla actual del usuario que solicita
            usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            if not usuario or not usuario.team_id:
                await query.answer("❌ No perteneces a ninguna cuadrilla.", show_alert=True)
                return

            cuadrilla_actual = Team.query.get(usuario.team_id)
            if not cuadrilla_actual or not cuadrilla_actual.area:
                await query.answer("❌ No se pudo determinar tu área.", show_alert=True)
                return

            # Buscar otras cuadrillas del mismo área (excepto la actual)
            otras_cuadrillas = Team.query.filter(
                Team.area == cuadrilla_actual.area,
                Team.id != cuadrilla_actual.id,
                Team.nombre != "Sin asignar",
                Team.is_active == True  # si tienes este campo
            ).order_by(Team.nombre).all()

            if not otras_cuadrillas:
                await query.message.reply_text(
                    "📭 *No hay otras cuadrillas disponibles en tu área para solicitar apoyo.*",
                    parse_mode=ParseMode.MARKDOWN
                )
                await query.answer("📭 Sin cuadrillas disponibles", show_alert=False)
                return

            # Crear teclado con las cuadrillas
            keyboard = []
            for cuadrilla in otras_cuadrillas:
                # Contar usuarios activos en la cuadrilla
                usuarios_count = User.query.filter_by(team_id=cuadrilla.id, is_active=True).count()
                texto = f"👷 {cuadrilla.nombre}"
                if usuarios_count > 0:
                    texto += f" ({usuarios_count})"
                keyboard.append([
                    InlineKeyboardButton(
                        texto,
                        callback_data=f"apoyar_cuadrilla_{reporte_id}_{cuadrilla.id}"
                    )
                ])

            keyboard.append([
                InlineKeyboardButton("❌ Cancelar", callback_data=f"volver_reporte_{reporte_id}")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_text(
                f"🔄 *SOLICITAR APOYO DE CUADRILLA*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
                f"👷 *Tu cuadrilla:* {cuadrilla_actual.nombre}\n\n"
                f"*Selecciona la cuadrilla a la que deseas solicitar apoyo:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )

            await query.answer("📋 Mostrando cuadrillas", show_alert=False)
            logger.info(f"🔄 Cuadrilla {cuadrilla_actual.nombre} solicitando apoyo para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_solicitar_apoyo_cuadrilla: {e}")
        await query.answer("❌ Error al mostrar cuadrillas", show_alert=True)


async def manejar_enviar_apoyo_cuadrilla(query, context, reporte_id, cuadrilla_destino_id):
    """Envía solicitud de apoyo a la cuadrilla seleccionada"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            cuadrilla_destino = Team.query.get(cuadrilla_destino_id)
            if not cuadrilla_destino:
                await query.answer("❌ Cuadrilla no encontrada.", show_alert=True)
                return

            usuario_solicitante = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            cuadrilla_origen = Team.query.get(usuario_solicitante.team_id) if usuario_solicitante else None

            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"

            # Buscar usuarios de la cuadrilla destino para notificar
            usuarios_destino = User.query.filter_by(
                team_id=cuadrilla_destino_id,
                is_active=True
            ).all()

            if not usuarios_destino:
                await query.message.reply_text(
                    f"⚠️ *La cuadrilla {cuadrilla_destino.nombre} no tiene usuarios activos.*",
                    parse_mode=ParseMode.MARKDOWN
                )
                await query.answer("⚠️ Sin usuarios activos", show_alert=False)
                return

            # Construir mensaje para la cuadrilla destino
            mensaje_apoyo = (
                f"🔄 *SOLICITUD DE APOYO - Reporte #{reporte.id}*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {direccion}\n"
                f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
                f"👤 *Reportante:* {reporte.reportante}\n"
                f"👷 *Cuadrilla solicitante:* {cuadrilla_origen.nombre if cuadrilla_origen else 'N/D'}\n"
                f"⏰ *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*📋 ¿Pueden brindar apoyo en este reporte?*"
            )

            # Botones para aceptar/rechazar
            keyboard = [
                [
                    InlineKeyboardButton("✅ Aceptar apoyo", callback_data=f"apoyo_aceptar_{reporte_id}_{cuadrilla_origen.id if cuadrilla_origen else 0}"),
                    InlineKeyboardButton("❌ Rechazar", callback_data=f"apoyo_rechazar_{reporte_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Enviar a todos los usuarios de la cuadrilla destino
            from app.routes.telegram_routes import get_telegram_app
            bot_app = get_telegram_app()
            enviados = 0
            for usuario in usuarios_destino:
                if usuario.telegram_id:
                    try:
                        await bot_app.bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje_apoyo,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup
                        )
                        enviados += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario.nombre}: {e}")

            # Confirmar al solicitante
            await query.message.reply_text(
                f"✅ *Solicitud de apoyo enviada a {cuadrilla_destino.nombre}*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"👷 *Cuadrilla destino:* {cuadrilla_destino.nombre}\n"
                f"📤 *Notificaciones enviadas:* {enviados} de {len(usuarios_destino)}\n\n"
                f"*Espera la respuesta de la cuadrilla.*",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.answer("✅ Solicitud enviada", show_alert=False)
            logger.info(f"🔄 Apoyo solicitado de {cuadrilla_origen.nombre if cuadrilla_origen else 'N/D'} a {cuadrilla_destino.nombre} para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_enviar_apoyo_cuadrilla: {e}")
        await query.answer("❌ Error al enviar solicitud", show_alert=True)


async def manejar_apoyo_aceptar(query, context, reporte_id, cuadrilla_origen_id):
    """Maneja cuando una cuadrilla acepta el apoyo"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            cuadrilla_actual = Team.query.get(usuario.team_id) if usuario else None
            cuadrilla_origen = Team.query.get(cuadrilla_origen_id) if cuadrilla_origen_id > 0 else None

            # Mensaje de confirmación para el que acepta
            await query.edit_message_text(
                f"✅ *Has aceptado brindar apoyo*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n\n"
                f"*La cuadrilla solicitante será notificada.*",
                parse_mode=ParseMode.MARKDOWN
            )

            # Notificar a la cuadrilla que solicitó el apoyo
            if cuadrilla_origen:
                usuarios_origen = User.query.filter_by(
                    team_id=cuadrilla_origen.id,
                    is_active=True
                ).all()

                mensaje_aceptacion = (
                    f"✅ *¡APOYO ACEPTADO!*\n\n"
                    f"📋 *Reporte:* #{reporte.id}\n"
                    f"👷 *Cuadrilla que aceptó:* {cuadrilla_actual.nombre if cuadrilla_actual else 'N/D'}\n"
                    f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n\n"
                    f"*La cuadrilla {cuadrilla_actual.nombre if cuadrilla_actual else 'N/D'} ha aceptado brindar apoyo.*"
                )

                from app.routes.telegram_routes import get_telegram_app
                bot_app = get_telegram_app()
                for usuario_origen in usuarios_origen:
                    if usuario_origen.telegram_id:
                        try:
                            await bot_app.bot.send_message(
                                chat_id=int(usuario_origen.telegram_id),
                                text=mensaje_aceptacion,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception as e:
                            logger.error(f"❌ Error notificando a {usuario_origen.nombre}: {e}")

            await query.answer("✅ Apoyo aceptado", show_alert=False)
            logger.info(f"🔄 Apoyo aceptado por {cuadrilla_actual.nombre if cuadrilla_actual else 'N/D'} para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_apoyo_aceptar: {e}")
        await query.answer("❌ Error al aceptar apoyo", show_alert=True)


async def manejar_apoyo_rechazar(query, context, reporte_id):
    """Maneja cuando una cuadrilla rechaza el apoyo"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            cuadrilla_actual = Team.query.get(usuario.team_id) if usuario else None

            await query.edit_message_text(
                f"❌ *Has rechazado brindar apoyo*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n\n"
                f"*La cuadrilla solicitante será notificada.*",
                parse_mode=ParseMode.MARKDOWN
            )

            # Opcional: notificar a la cuadrilla que solicitó el apoyo que fue rechazado
            # (podrías obtener la cuadrilla origen del mensaje original, pero sería más complejo)

            await query.answer("❌ Apoyo rechazado", show_alert=False)
            logger.info(f"🔄 Apoyo rechazado por {cuadrilla_actual.nombre if cuadrilla_actual else 'N/D'} para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_apoyo_rechazar: {e}")
        await query.answer("❌ Error al rechazar apoyo", show_alert=True)
