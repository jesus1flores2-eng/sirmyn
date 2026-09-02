"""
Maneja los callbacks de rechazo del usuario
"""
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


async def rechazo_motivo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de motivo de rechazo del usuario"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    callback_data = query.data
    user_id = query.from_user.id

    if not callback_data.startswith('usuario_rechazo_motivo_'):
        return

    reporte_id = int(callback_data.split('_')[-1])

    # Mapeo de callbacks a texto del motivo
    motivo = None

    # Motivos de Aseo
    if "basura_incompleta" in callback_data:
        motivo = "No recogieron toda la basura"
    elif "no_paso_camion" in callback_data:
        motivo = "No pasó el camión recolector"
    elif "escombros" in callback_data:
        motivo = "Dejaron escombros tirados"
    elif "mal_olor" in callback_data:
        motivo = "El mal olor persiste"
    # Motivos de Alumbrado
    elif "lampara_sigue_mal" in callback_data:
        motivo = "La lámpara sigue sin funcionar"
    elif "cables_sueltos" in callback_data:
        motivo = "Los cables siguen sueltos/pelados"
    elif "poste_danado" in callback_data:
        motivo = "El poste sigue dañado"
    # Motivos de Parques y Jardines
    elif "no_podaron" in callback_data:
        motivo = "No podaron correctamente"
    elif "area_sucia" in callback_data:
        motivo = "El área verde sigue sucia"
    elif "no_regaron" in callback_data:
        motivo = "No regaron las plantas"
    elif "juegos_rotos" in callback_data:
        motivo = "Los juegos siguen rotos"
    # Motivos de Seguridad Pública
    elif "sin_respuesta" in callback_data:
        motivo = "No hubo respuesta policial"
    elif "no_resuelto" in callback_data:
        motivo = "No se resolvió el problema"
    # Motivos de Bomberos
    elif "incendio" in callback_data:
        motivo = "El incendio no fue controlado"
    elif "no_llego" in callback_data:
        motivo = "No llegó la unidad de emergencia"
    elif "falta_atencion" in callback_data:
        motivo = "Falta atención en la emergencia"
    # Motivos generales (Agua, Drenaje, etc.)
    elif "problema_persiste" in callback_data:
        motivo = "El problema persiste igual que antes"
    elif "reparacion_incompleta" in callback_data:
        motivo = "La reparación está incompleta"
    elif "no_termino_tapar" in callback_data:
        motivo = "No terminaron de tapar el área reparada"
    elif "causo_otro" in callback_data:
        motivo = "Causaron otro problema adicional"
    elif "otro" in callback_data:
        # Modo para escribir motivo personalizado
        user_data[user_id] = {
            'modo_rechazo_usuario': True,
            'reporte_id': reporte_id,
            'paso_actual': 'escribir_motivo',
            'motivo_seleccionado': 'Otro motivo'
        }
        await query.edit_message_text(
            text="📝 *ESCRIBE TU MOTIVO*\n\n"
                 "Por favor, describe detalladamente el motivo del rechazo:\n\n"
                 "📌 *Tu comentario será enviado al responsable para mejorar el servicio.*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")
            ]])
        )
        await query.answer("Escribe tu motivo", show_alert=False)
        return

    if not motivo:
        await query.answer("❌ Motivo no reconocido", show_alert=True)
        return

    # Guardar motivo y proceder a notificar
    await procesar_rechazo_usuario(update, context, reporte_id, motivo, user_id)


async def procesar_rechazo_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE, reporte_id: int, motivo: str, user_id: int):
    """Procesa el rechazo: notifica al responsable y cambia estado"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                if update.callback_query:
                    await update.callback_query.edit_message_text("❌ Reporte no encontrado.")
                else:
                    await update.message.reply_text("❌ Reporte no encontrado.")
                return

            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            if not asignacion:
                if update.callback_query:
                    await update.callback_query.edit_message_text("❌ No hay asignación para este reporte.")
                return

            # Cambiar estado a "Rechazado por usuario"
            estado_rechazado = Status.query.filter_by(descripcion="Rechazado por usuario").first()
            if not estado_rechazado:
                estado_rechazado = Status(descripcion="Rechazado por usuario")
                db.session.add(estado_rechazado)
                db.session.commit()

            asignacion.status_id = estado_rechazado.id
            asignacion.observaciones = f"❌ Rechazado por usuario. Motivo: {motivo} - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()

            # Confirmar al usuario
            mensaje_usuario = (
                f"❌ *RECHAZO REGISTRADO*\n\n"
                f"📋 *Reporte:* #{reporte_id}\n"
                f"📝 *Motivo:* {motivo}\n\n"
                f"*El responsable ha sido notificado.*\n"
                f"Se tomarán las medidas necesarias para resolver el problema."
            )

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    mensaje_usuario,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    mensaje_usuario,
                    parse_mode=ParseMode.MARKDOWN
                )

            # Notificar al responsable según departamento
            responsable = None
            rol_nombre = "Responsable"

            if reporte.tipo in ["Agua potable", "Drenaje"]:
                responsable = User.query.filter_by(
                    area='agua',
                    rol_especifico='jefe_area_tecnica',
                    is_active=True
                ).first()
                rol_nombre = "Jefe Técnico de Agua/Drenaje"
            elif reporte.tipo == "Aseo público":
                responsable = User.query.filter_by(
                    area='aseo',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='aseo',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Aseo"
            elif reporte.tipo == "Alumbrado público":
                responsable = User.query.filter_by(
                    area='alumbrado',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='alumbrado',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Alumbrado"
            elif reporte.tipo == "Parques y jardines":
                responsable = User.query.filter_by(
                    area='parques',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='parques',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Parques"
            elif reporte.tipo == "Ecología":
                responsable = User.query.filter_by(
                    area='ecologia',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='ecologia',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Ecología"
            elif reporte.tipo == "Seguridad pública":
                responsable = User.query.filter_by(
                    area='seguridad',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='seguridad',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Seguridad"
            elif reporte.tipo == "Obras públicas":
                responsable = User.query.filter_by(
                    area='obras',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='obras',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Obras"
            elif reporte.tipo == "Bomberos":
                responsable = User.query.filter_by(
                    area='bomberos',
                    rol_especifico='jefe_area',
                    is_active=True
                ).first()
                if not responsable:
                    responsable = User.query.filter_by(
                        area='bomberos',
                        rol_especifico='director',
                        is_active=True
                    ).first()
                rol_nombre = "Jefe de Área de Bomberos"

            if responsable and responsable.telegram_id:
                try:
                    calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
                    localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

                    mensaje_responsable = (
                        f"🚨 *RECHAZO DE USUARIO - Reporte #{reporte.id}*\n\n"
                        f"📋 *Folio:* #{reporte.id}\n"
                        f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                        f"👤 *Reportante:* {reporte.reportante}\n"
                        f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
                        f"👷 *Cuadrilla:* {asignacion.team.nombre if asignacion.team else 'N/D'}\n\n"
                        f"📝 *MOTIVO DEL RECHAZO:*\n_{motivo}_\n\n"
                        f"*⚠️ ACCIÓN REQUERIDA:* Revisar y reasignar o corregir el trabajo."
                    )

                    # Notificar también a la cuadrilla con botones para subir evidencia
                    if asignacion.team_id:
                        from app.telegram.common.keyboards import construir_botones_reporte
                        usuarios_cuadrilla = User.query.filter_by(
                            team_id=asignacion.team_id,
                            is_active=True
                        ).all()

                        for usuario_cuadrilla in usuarios_cuadrilla:
                            if usuario_cuadrilla.telegram_id:
                                try:
                                    # Construir mensaje con datos del reporte
                                    calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
                                    localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
                                    
                                    mensaje_cuadrilla = (
                                        f"❌ *REPORTE RECHAZADO POR EL USUARIO*\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                        f"📋 *Folio:* #{reporte.id}\n"
                                        f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                                        f"📞 *Reportante:* {reporte.reportante}\n"
                                        f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
                                        f"📄 *Descripción:* {reporte.descripcion_problema[:150]}...\n\n"
                                        f"📝 *Motivo del rechazo:* {motivo}\n\n"
                                        f"*📌 ACCIÓN REQUERIDA:* Corrige el trabajo y vuelve a subir evidencia.\n\n"
                                        f"*📋 Acciones rápidas:*"
                                    )
                                    
                                    # Solo botón de subir evidencia para corrección
                                    keyboard_simple = [[
                                        InlineKeyboardButton(
                                            "🔧 Subir evidencia reparación",
                                            callback_data=f"reparacion_{reporte_id}"
                                        )
                                    ]]
                                    reply_markup = InlineKeyboardMarkup(keyboard_simple)
                                    
                                    await context.bot.send_message(
                                        chat_id=int(usuario_cuadrilla.telegram_id),
                                        text=mensaje_cuadrilla,
                                        parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=reply_markup
                                    )
                                except Exception as e:
                                    logger.error(f"❌ Error notificando a cuadrilla: {e}")

                    await context.bot.send_message(
                        chat_id=int(responsable.telegram_id),
                        text=mensaje_responsable,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    logger.info(f"✅ {rol_nombre} {responsable.nombre} notificado sobre rechazo de reporte #{reporte_id}")
                except Exception as e:
                    logger.error(f"❌ Error notificando responsable: {e}")

            logger.info(f"✅ Rechazo de usuario procesado para reporte #{reporte_id}: {motivo}")

    except Exception as e:
        logger.error(f"❌ Error en procesar_rechazo_usuario: {e}", exc_info=True)
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Error al procesar el rechazo.")
            else:
                await update.message.reply_text("❌ Error al procesar el rechazo.")
        except:
            pass


async def rechazo_volver_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite al usuario volver atrás desde el formulario de rechazo"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    callback_data = query.data
    user_id = query.from_user.id

    if not callback_data.startswith('rech_volver_'):
        return

    reporte_id = int(callback_data.split('_')[-1])

    # Volver a mostrar opciones de aceptar/rechazar
    keyboard = [
        [
            InlineKeyboardButton("✅ Sí, está resuelto", callback_data=f"usuario_aceptar_{reporte_id}"),
            InlineKeyboardButton("❌ No, persiste el problema", callback_data=f"usuario_rechazar_{reporte_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="✅ *¡TU REPORTE HA SIDO ATENDIDO!*\n\n"
             "*¿La reparación fue satisfactoria?*\n\n"
             "⚠️ Tienes 48 horas para responder.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    await query.answer("↩️ Volviendo...", show_alert=False)


async def rechazo_otro_motivo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja cuando el usuario escribe su propio motivo de rechazo"""
    user_id = update.effective_user.id
    motivo = update.message.text.strip()

    if user_id not in user_data or not user_data[user_id].get('modo_rechazo_usuario'):
        return

    reporte_id = user_data[user_id].get('reporte_id')

    if not reporte_id:
        await update.message.reply_text("❌ No se encontró el reporte.")
        limpiar_estado(user_id)
        return

    # Procesar rechazo con el motivo personalizado
    await procesar_rechazo_usuario(update, context, reporte_id, motivo, user_id)

    # Limpiar estado
    if user_id in user_data:
        user_data[user_id].pop('modo_rechazo_usuario', None)
        user_data[user_id].pop('reporte_id', None)
        user_data[user_id].pop('paso_actual', None)
        user_data[user_id].pop('motivo_seleccionado', None)
