"""
Maneja todos los botones de cuadrillas y acciones generales
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
from app.services.db_manager import DatabaseManager
from app.telegram.keyboards import construir_botones_reporte, obtener_carpeta_departamento
from app.telegram.materiales import MATERIALES
import logging
import os
import re
import uuid
from datetime import datetime
from flask import url_for

logger = logging.getLogger(__name__)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los botones de cuadrillas y acciones generales"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    callback_data = query.data
    telegram_user_id = query.from_user.id

    logger.info(f"🔄 Callback recibido: {callback_data} de telegram_id {telegram_user_id}")

    # Ignorar callbacks que no son de este handler
    if callback_data.startswith(('dir_', 'pres_', 'dash_', 'super_', 'reasignar_', 'usuario_', 'enc_', 'rech_')):
        logger.info(f"⏩ Callback {callback_data} ignorado, va a su handler específico")
        return

    # ============================================================
    # DETECCIÓN PARA SOLICITUD DE RETROEXCAVADORA
    # ============================================================
    if callback_data.startswith('solicitar_retro_'):
        reporte_id = int(callback_data.split('_')[-1])
        await manejar_solicitar_retro(query, context, reporte_id)
        return

    # ============================================================
    # DETECCIÓN PARA SOLICITUD DE CAMIÓN
    # ============================================================
    if callback_data.startswith('solicitar_camion_'):
        reporte_id = int(callback_data.split('_')[-1])
        await manejar_solicitar_camion(query, context, reporte_id)
        return

    # ============================================================
    # DETECCIÓN PARA SELECCIÓN DE MATERIAL
    # ============================================================
    if callback_data.startswith('material_camion_'):
        partes = callback_data.split('_')
        reporte_id = int(partes[-1])
        material_parts = partes[2:-1]
        material = ' '.join(material_parts).replace('_', ' ')
        await manejar_material_seleccionado(query, context, reporte_id, material, 'camion')
        return

    # ============================================================
    # DETECCIÓN PARA VOLVER AL REPORTE
    # ============================================================
    if callback_data.startswith('volver_reporte_'):
        reporte_id_str = callback_data.split('_')[-1]
        if not reporte_id_str.isdigit():
            logger.error(f"❌ ID inválido en volver_reporte: {callback_data}")
            await query.answer("❌ Error: ID de reporte inválido", show_alert=True)
            return
        reporte_id = int(reporte_id_str)
        await manejar_volver_reporte(query, context, reporte_id)
        return

    # ============================================================
    # SPLIT GENERAL PARA OTROS CALLBACKS
    # ============================================================
    if '_' in callback_data:
        partes = callback_data.split('_', 1)
        accion = partes[0]
        reporte_id_str = partes[1] if len(partes) > 1 else ''

        if accion == 'recibido':
            partes_callback = callback_data.split('_')
            if len(partes_callback) > 1:
                reporte_id_str = partes_callback[-1]
            else:
                logger.error(f"❌ No se pudo extraer ID de: {callback_data}")
                await query.answer("❌ Error: ID de reporte inválido", show_alert=True)
                return

        if not reporte_id_str.isdigit():
            if accion in ['confirmado', 'problema_ya']:
                await query.answer(f"Ya {accion} este reporte", show_alert=False)
                return
            elif accion == 'confirmado_ya':
                await query.answer("✅ Ya confirmaste este reporte", show_alert=False)
                return
            elif accion == 'problema_ya':
                await query.answer("⚠️ Ya reportaste problema con este reporte", show_alert=False)
                return
            else:
                logger.error(f"❌ reporte_id no es numérico: {reporte_id_str}")
                await query.answer("❌ Error: ID de reporte inválido", show_alert=True)
                return

        reporte_id = int(reporte_id_str)

        # Verificar usuario y reporte
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment, Localidad, Calle
            from app.models.user import User
            from app.models.team import Team
            from app.models.status import Status
            from app.extensions import db

            usuario = User.query.filter_by(telegram_id=str(telegram_user_id)).first()
            if not usuario:
                await query.edit_message_text("❌ No estás autorizado para esta acción.")
                return

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return

            # ============================================================
            # ACCIÓN: CONFIRMAR RECEPCIÓN
            # ============================================================
            if accion == 'confirmar':
                asignacion = Assignment.query.filter_by(
                    report_id=reporte.id
                ).order_by(Assignment.timestamp.desc()).first()

                if asignacion:
                    status_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
                    if not status_en_proceso:
                        status_en_proceso = Status(descripcion="En proceso")
                        db.session.add(status_en_proceso)
                        db.session.commit()

                    asignacion.status_id = status_en_proceso.id
                    asignacion.observaciones = f"Confirmado por {usuario.nombre} via Telegram"
                    db.session.commit()

                reply_markup = construir_botones_reporte(reporte.id, confirmado=True, context=context)

                calle_nombre = reporte.calle.nombre if reporte.calle else ''
                localidad_nombre = reporte.localidad.nombre if reporte.localidad else ''
                direccion = f"{calle_nombre} {reporte.numero}, {localidad_nombre}"
                direccion_url = direccion.replace(' ', '%20')
                maps_url = f"https://www.google.com/maps?q={direccion_url}"

                nuevo_texto = query.message.text + f"\n\n✅ <b>Confirmado por {usuario.nombre}</b>\n🗺️ <b>Mapa:</b> <a href='{maps_url}'>Ver ubicación</a>"

                try:
                    await query.edit_message_text(
                        text=nuevo_texto,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                except:
                    await query.edit_message_text(
                        text=nuevo_texto,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )

                try:
                    from app.routes.telegram_routes import get_telegram_app
                    bot_app = get_telegram_app()
                    admin_id = app.config.get('TELEGRAM_ADMIN_ID')
                    if admin_id:
                        await bot_app.bot.send_message(
                            chat_id=int(admin_id),
                            text=f"✅ <b>Confirmación de cuadrilla</b>\n\n"
                                 f"<b>Reporte:</b> #{reporte.id}\n"
                                 f"<b>Cuadrilla:</b> {usuario.nombre}\n"
                                 f"<b>Ubicación:</b> {calle_nombre} #{reporte.numero}\n"
                                 f"<b>Hora:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                            parse_mode=ParseMode.HTML
                        )
                except Exception as admin_error:
                    logger.error(f"⚠️ No se pudo notificar al admin: {admin_error}")

                await query.answer("✅ Reporte confirmado", show_alert=False)
                logger.info(f"✅ Reporte {reporte_id} confirmado por {usuario.nombre}")

            # ============================================================
            # ACCIÓN: PROBLEMA DE UBICACIÓN
            # ============================================================
            elif accion == 'problema':
                cuadrilla_nombre = usuario.team.nombre if usuario and usuario.team else "Cuadrilla desconocida"

                status_problema = Status.query.get(9)
                if not status_problema:
                    status_problema = Status(descripcion="Problema ubicación", color="warning")
                    db.session.add(status_problema)
                    db.session.commit()

                asignacion = Assignment.query.filter_by(
                    report_id=reporte.id
                ).order_by(Assignment.timestamp.desc()).first()

                if asignacion:
                    asignacion.status_id = status_problema.id
                    asignacion.observaciones = f"Problema de ubicación reportado por {usuario.nombre}"
                    db.session.commit()

                reply_markup = construir_botones_reporte(reporte.id, problema_reportado=True, context=context)
                nuevo_texto = query.message.text + f"\n\n⚠️ *Problema de ubicación reportado por {usuario.nombre}*"

                try:
                    await query.edit_message_text(
                        text=nuevo_texto,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )
                except:
                    pass

                # Solicitar ubicación al reportante
                try:
                    from app.telegram.handlers.ubicacion import solicitar_ubicacion_exacta_al_reportante

                    if reporte.telefono and str(reporte.telefono).strip().isdigit():
                        success = await solicitar_ubicacion_exacta_al_reportante(
                            reporte_id=reporte.id,
                            cuadrilla_nombre=cuadrilla_nombre,
                            context=context
                        )

                        if success:
                            logger.info(f"✅ Ubicación solicitada al reportante para reporte #{reporte.id}")
                            try:
                                await query.edit_message_text(
                                    text=nuevo_texto + f"\n\n📱 *Solicitud de ubicación enviada al reportante*",
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=reply_markup
                                )
                            except:
                                pass
                        else:
                            logger.warning(f"⚠️ No se pudo solicitar ubicación al reportante para reporte #{reporte.id}")
                            await context.bot.send_message(
                                chat_id=telegram_user_id,
                                text="⚠️ *No se pudo enviar solicitud al reportante.*\n\nEl reportante no tiene Telegram vinculado.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                    else:
                        logger.warning(f"⚠️ Reporte #{reporte.id} no tiene Telegram ID válido: {reporte.telefono}")
                        await context.bot.send_message(
                            chat_id=telegram_user_id,
                            text="⚠️ *El reportante no tiene Telegram vinculado.*\n\nNo se puede solicitar ubicación automáticamente.",
                            parse_mode=ParseMode.MARKDOWN
                        )

                except Exception as ubicacion_error:
                    logger.error(f"❌ Error solicitando ubicación: {ubicacion_error}")
                    await context.bot.send_message(
                        chat_id=telegram_user_id,
                        text=f"⚠️ *Error al solicitar ubicación:*\n{str(ubicacion_error)[:100]}",
                        parse_mode=ParseMode.MARKDOWN
                    )

                # Notificar al responsable
                try:
                    responsable = None
                    if reporte.tipo in ["Agua potable", "Drenaje"]:
                        responsable = User.query.filter_by(
                            area='agua',
                            rol_especifico='jefe_area_tecnica',
                            is_active=True
                        ).first()
                        rol_nombre = "Jefe Técnico de Agua/Drenaje"
                    else:
                        mapeo_tipo_a_area = {
                            "Aseo público": "aseo",
                            "Alumbrado público": "alumbrado",
                            "Parques y jardines": "parques",
                            "Ecología": "ecologia",
                            "Seguridad pública": "seguridad",
                            "Obras públicas": "obras",
                            "Bomberos": "bomberos"
                        }
                        area = mapeo_tipo_a_area.get(reporte.tipo)
                        if area:
                            responsable = User.query.filter_by(
                                area=area,
                                rol_especifico='director',
                                is_active=True
                            ).first()
                            rol_nombre = f"Director de {area.title()}"

                    if responsable and responsable.telegram_id:
                        calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
                        localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

                        mensaje_responsable = (
                            f"⚠️ *PROBLEMA DE UBICACIÓN - ATENCIÓN REQUERIDA*\n\n"
                            f"📋 *Reporte:* #{reporte.id}\n"
                            f"🔧 *Tipo:* {reporte.tipo}\n"
                            f"📝 *Subtipo:* {reporte.subtipo}\n"
                            f"📍 *Dirección reportada:*\n"
                            f"{calle_nombre} #{reporte.numero}\n"
                            f"{localidad_nombre}\n\n"
                            f"👷 *Cuadrilla:* {cuadrilla_nombre}\n"
                            f"👤 *Reportante:* {reporte.reportante}\n"
                            f"📱 *Teléfono:* {reporte.telefono}\n\n"
                            f"*🔄 ACCIÓN REALIZADA:*\n"
                            f"• Se ha solicitado al reportante su ubicación exacta\n"
                            f"• Tiene 24 horas para responder\n"
                            f"• Si no responde, el reporte se cancelará automáticamente\n\n"
                            f"*📋 Sistema monitoreando respuesta...*"
                        )

                        keyboard = [[InlineKeyboardButton("✅ Recibido", callback_data=f"recibido_ubicacion_{reporte.id}")]]
                        reply_markup_resp = InlineKeyboardMarkup(keyboard)

                        await context.bot.send_message(
                            chat_id=int(responsable.telegram_id),
                            text=mensaje_responsable,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup_resp
                        )
                        logger.info(f"✅ Notificación enviada a {responsable.nombre} ({rol_nombre})")
                    else:
                        logger.warning(f"⚠️ No se encontró responsable para {reporte.tipo}")

                except Exception as notif_error:
                    logger.error(f"❌ Error notificando responsable: {notif_error}")

                await query.answer("⚠️ Problema de ubicación reportado", show_alert=False)
                logger.info(f"⚠️ Problema de ubicación en reporte {reporte_id}")

            # ============================================================
            # ACCIÓN: RECIBIDO
            # ============================================================
            elif accion == 'recibido':
                await query.answer("✅ Notificación recibida", show_alert=False)
                await query.edit_message_text(
                    text=query.message.text + "\n\n✅ *Recibido por el responsable*",
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"✅ Responsable confirmó recepción de notificación para reporte {reporte_id}")

                try:
                    asignacion_actual = Assignment.query.filter_by(
                        report_id=reporte_id
                    ).order_by(Assignment.timestamp.desc()).first()

                    if asignacion_actual and asignacion_actual.team_id:
                        usuario_cuadrilla = User.query.filter_by(
                            team_id=asignacion_actual.team_id,
                            is_active=True
                        ).first()

                        if usuario_cuadrilla and usuario_cuadrilla.telegram_id:
                            responsable_telegram_id = query.from_user.id
                            responsable_user = User.query.filter_by(
                                telegram_id=str(responsable_telegram_id)
                            ).first()
                            nombre_responsable = responsable_user.nombre if responsable_user else "Responsable"

                            mensaje_cuadrilla = (
                                f"✅ *Notificación recibida*\n\n"
                                f"*{nombre_responsable}* ha confirmado que está enterado del problema de ubicación del reporte #{reporte_id}.\n\n"
                                f"📋 El reportante ha sido notificado para enviar su ubicación exacta.\n"
                                f"⏰ Tiene 24 horas para responder."
                            )

                            await context.bot.send_message(
                                chat_id=int(usuario_cuadrilla.telegram_id),
                                text=mensaje_cuadrilla,
                                parse_mode=ParseMode.MARKDOWN
                            )
                            logger.info(f"✅ Mensaje enviado a la cuadrilla {usuario_cuadrilla.nombre} sobre confirmación de {nombre_responsable}")
                        else:
                            logger.warning(f"⚠️ No se encontró usuario de cuadrilla para team_id {asignacion_actual.team_id}")
                except Exception as e:
                    logger.error(f"❌ Error al notificar a la cuadrilla: {e}")

            # ============================================================
            # ACCIÓN: MAPA
            # ============================================================
            elif accion == 'mapa':
                calle_nombre = reporte.calle.nombre if reporte.calle else 'Calle no especificada'
                localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'Localidad no especificada'

                direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"
                direccion_url = direccion.replace(' ', '+')

                if reporte.latitud and reporte.longitud:
                    maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                    waze_url = f"https://waze.com/ul?ll={reporte.latitud},{reporte.longitud}&navigate=yes"
                    mensaje_mapa = (
                        f"📍 *UBICACIÓN EXACTA - Reporte #{reporte.id}*\n\n"
                        f"*Coordenadas GPS:*\n`{reporte.latitud}, {reporte.longitud}`\n\n"
                        f"*🗺️ Google Maps:* [Abrir]({maps_url})\n"
                        f"*🚗 Waze:* [Abrir]({waze_url})\n\n"
                        f"*Dirección original:* {direccion}"
                    )
                else:
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={direccion_url}"
                    waze_url = f"https://www.waze.com/ul?q={direccion_url}&navigate=yes"
                    mensaje_mapa = (
                        f"📍 *UBICACIÓN APROXIMADA - Reporte #{reporte.id}*\n\n"
                        f"{direccion}\n\n"
                        f"*🗺️ Google Maps:* [Abrir]({maps_url})\n"
                        f"*🚗 Waze:* [Abrir]({waze_url})"
                    )

                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=mensaje_mapa,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False
                )
                await query.answer("📍 Ubicación enviada", show_alert=False)
                logger.info(f"🗺️ Mapa enviado para reporte {reporte_id}")

            # ============================================================
            # ⭐ ACCIÓN: EVIDENCIA (CORREGIDO - soporta Cloudinary y local)
            # ============================================================
            elif accion == 'evidencia':
                if reporte.evidencia:
                    import os
                    from flask import url_for

                    # ⭐ DETECTAR SI ES URL DE CLOUDINARY O RUTA LOCAL
                    if reporte.evidencia.startswith('http'):
                        evidencia_url = reporte.evidencia
                        nombre_archivo = os.path.basename(reporte.evidencia.split('/')[-1])
                        # Si es una URL de Cloudinary, extraer solo el nombre del archivo
                        if '?' in nombre_archivo:
                            nombre_archivo = nombre_archivo.split('?')[0]
                    else:
                        evidencia_url = url_for('admin.uploaded_file', filename=reporte.evidencia, _external=True)
                        nombre_archivo = os.path.basename(reporte.evidencia)

                    mensaje = (
                        f"📎 *Evidencia del reporte #{reporte.id}*\n\n"
                        f"📄 *Archivo:* `{nombre_archivo}`\n\n"
                        f"🔗 [Ver evidencia]({evidencia_url})"
                    )

                    keyboard = [[
                        InlineKeyboardButton("↩️ Volver al menú", callback_data=f"volver_reporte_{reporte.id}")
                    ]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text=mensaje,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup,
                        disable_web_page_preview=False
                    )

                    await query.answer("🔗 Evidencia enviada", show_alert=False)
                    logger.info(f"🔗 Evidencia enviada para reporte {reporte_id} (solo nombre: {nombre_archivo})")
                else:
                    await query.answer("❌ No hay evidencia disponible", show_alert=True)

            # ============================================================
            # ACCIÓN: REPARACIÓN
            # ============================================================
            elif accion == 'reparacion':
                asignacion = Assignment.query.filter_by(
                    report_id=reporte_id
                ).order_by(Assignment.timestamp.desc()).first()

                if not usuario or not asignacion:
                    await query.answer("❌ No se pudo verificar la asignación", show_alert=True)
                    return

                if usuario.team_id != asignacion.team_id:
                    await query.answer("❌ No estás asignado a este reporte", show_alert=True)
                    return

                user_data[telegram_user_id] = {
                    'modo_reparacion': True,
                    'reporte_id': reporte_id,
                    'asignacion_id': asignacion.id,
                    'paso': 'evidencia',
                    'evidencias': [],
                    'materiales': [],
                    'comentario': ''
                }

                await query.message.reply_text(
                    "🔧 *EVIDENCIA DE REPARACIÓN*\n\n"
                    "Envía las fotos/videos del trabajo realizado:\n"
                    "• Puedes enviar múltiples archivos\n"
                    "• Cuando termines, escribe *'listo'*\n"
                    "• Para cancelar, escribe *'cancelar'*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardRemove()
                )
                await query.answer("🔧 Iniciando reparación", show_alert=False)

            else:
                await query.answer("⚠️ Acción no reconocida", show_alert=True)

    else:
        await query.answer("⚠️ Acción no reconocida", show_alert=True)


# ============================================================
# FUNCIÓN AUXILIAR PARA OBTENER OPERADOR UNIFICADO
# ============================================================

def obtener_operador_maquinaria():
    """
    Busca un operador que tenga rol 'retro' o 'camion_7m' (o variantes).
    Retorna el primero que encuentre con telegram_id configurado.
    """
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            
            # Buscar por roles específicos (insensible a mayúsculas)
            operador = User.query.filter(
                (User.rol_especifico.ilike('%retro%')) | 
                (User.rol_especifico.ilike('%camion%')) |
                (User.rol_especifico.ilike('%camion_7m%')) |
                (User.rol_especifico.ilike('%volteo%')),
                User.is_active == True,
                User.telegram_id.isnot(None)
            ).first()
            
            if operador:
                logger.info(f"✅ Operador de maquinaria encontrado: {operador.nombre} (rol: {operador.rol_especifico}, telegram_id: {operador.telegram_id})")
                return operador
            else:
                # Log de depuración
                todos_operadores = User.query.filter(
                    (User.rol_especifico.ilike('%retro%')) | 
                    (User.rol_especifico.ilike('%camion%')) |
                    (User.rol_especifico.ilike('%volteo%')),
                    User.is_active == True
                ).all()
                
                if todos_operadores:
                    logger.warning(f"⚠️ Se encontraron {len(todos_operadores)} operadores pero ninguno tiene telegram_id configurado:")
                    for op in todos_operadores:
                        logger.warning(f"   - {op.nombre} (rol: {op.rol_especifico}, telegram_id: {op.telegram_id})")
                else:
                    logger.warning("⚠️ No se encontró ningún operador con rol 'retro' o 'camion_7m'")
                
                return None
                
    except Exception as e:
        logger.error(f"❌ Error obteniendo operador de maquinaria: {e}")
        return None


# ============================================================
# SOLICITAR RETROEXCAVADORA
# ============================================================

async def manejar_solicitar_retro(query, context, reporte_id):
    """Envía solicitud al operador de retroexcavadora"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.routes.telegram_routes import get_telegram_app

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            # Usar el operador unificado
            operador = obtener_operador_maquinaria()

            if not operador:
                await query.answer("❌ No hay operador de maquinaria disponible", show_alert=True)
                await query.message.reply_text(
                    "⚠️ *No se pudo enviar la solicitud*\n\n"
                    "No hay un operador de retroexcavadora registrado en el sistema.\n\n"
                    "📌 *Acción:* Contacta al administrador para registrar un operador con rol 'retro' o 'camion_7m' y asignarle un Telegram ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            if not operador.telegram_id:
                await query.answer("❌ El operador no tiene Telegram configurado", show_alert=True)
                await query.message.reply_text(
                    f"⚠️ *El operador {operador.nombre} no tiene Telegram vinculado*\n\n"
                    "Contacta al administrador para configurar su Telegram ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"

            mensaje = (
                f"🛠️ *SOLICITUD DE RETROEXCAVADORA*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {direccion}\n"
                f"👷 *Solicitado por:* {query.from_user.first_name or 'Cuadrilla'}\n"
                f"⏰ *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*🚨 Se requiere retroexcavadora en el lugar.*"
            )

            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                mensaje += f"\n\n🗺️ [Ver en Google Maps]({maps_url})"

            bot_app = get_telegram_app()
            await bot_app.bot.send_message(
                chat_id=int(operador.telegram_id),
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN
            )

            await query.message.reply_text(
                f"✅ *Solicitud enviada a {operador.nombre}*\n\n"
                f"Se ha notificado al operador de retroexcavadora.\n"
                f"📍 Ubicación: {direccion}\n\n"
                f"*El operador se pondrá en contacto.*",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.answer("✅ Solicitud enviada", show_alert=False)
            logger.info(f"🛠️ Solicitud de retroexcavadora enviada a {operador.nombre} para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_solicitar_retro: {e}")
        await query.answer("❌ Error al enviar solicitud", show_alert=True)


# ============================================================
# SOLICITAR CAMIÓN DE MATERIAL
# ============================================================

async def manejar_solicitar_camion(query, context, reporte_id):
    """Muestra lista de materiales para solicitar camión"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            # Verificar operador antes de mostrar materiales
            operador = obtener_operador_maquinaria()

            if not operador:
                await query.answer("❌ No hay operador de maquinaria disponible", show_alert=True)
                await query.message.reply_text(
                    "⚠️ *No se puede solicitar camión*\n\n"
                    "No hay un operador de camión registrado en el sistema.\n\n"
                    "📌 *Acción:* Contacta al administrador para registrar un operador con rol 'camion_7m' y asignarle un Telegram ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            if not operador.telegram_id:
                await query.answer("❌ El operador no tiene Telegram configurado", show_alert=True)
                await query.message.reply_text(
                    f"⚠️ *El operador {operador.nombre} no tiene Telegram vinculado*\n\n"
                    "Contacta al administrador para configurar su Telegram ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Si todo está bien, mostrar materiales
            keyboard = []
            for i in range(0, len(MATERIALES), 2):
                fila = []
                for material in MATERIALES[i:i+2]:
                    callback_material = f"material_camion_{material.replace(' ', '_')}_{reporte_id}"
                    fila.append(InlineKeyboardButton(material, callback_data=callback_material))
                keyboard.append(fila)

            keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data=f"volver_reporte_{reporte_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_text(
                f"🚛 *SELECCIONA EL MATERIAL*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n\n"
                f"*Selecciona el material que necesita el camión:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )

            await query.answer("📋 Mostrando materiales", show_alert=False)
            logger.info(f"🚛 Mostrando materiales para solicitud de camión en reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_solicitar_camion: {e}")
        await query.answer("❌ Error al mostrar materiales", show_alert=True)


# ============================================================
# MATERIAL SELECCIONADO (enviar solicitud al operador)
# ============================================================

async def manejar_material_seleccionado(query, context, reporte_id, material, tipo):
    """Envía solicitud al operador con el material seleccionado"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.routes.telegram_routes import get_telegram_app

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            operador = obtener_operador_maquinaria()

            if not operador:
                await query.answer("❌ No hay operador disponible", show_alert=True)
                await query.message.reply_text(
                    "⚠️ *No se pudo enviar la solicitud*\n\n"
                    "No hay un operador de camión registrado en el sistema.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            if not operador.telegram_id:
                await query.answer("❌ Operador sin Telegram", show_alert=True)
                return

            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"

            mensaje = (
                f"🚛 *SOLICITUD DE MATERIAL*\n\n"
                f"📦 *Material solicitado:* {material}\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {direccion}\n"
                f"👷 *Solicitado por:* {query.from_user.first_name or 'Cuadrilla'}\n"
                f"⏰ *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*🚨 Se requiere camión de 7m para trasladar el material.*"
            )

            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                mensaje += f"\n\n🗺️ [Ver en Google Maps]({maps_url})"

            bot_app = get_telegram_app()
            await bot_app.bot.send_message(
                chat_id=int(operador.telegram_id),
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN
            )

            await query.message.reply_text(
                f"✅ *Solicitud enviada a {operador.nombre}*\n\n"
                f"📦 *Material:* {material}\n"
                f"📍 *Ubicación:* {direccion}\n\n"
                f"*El operador del camión se pondrá en contacto.*",
                parse_mode=ParseMode.MARKDOWN
            )

            # Eliminar el mensaje de selección de materiales
            try:
                await query.message.delete()
            except:
                pass

            await query.answer("✅ Solicitud enviada", show_alert=False)
            logger.info(f"🚛 Solicitud de material '{material}' enviada a {operador.nombre} para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_material_seleccionado: {e}")
        await query.answer("❌ Error al enviar solicitud", show_alert=True)


# ============================================================
# VOLVER AL REPORTE ORIGINAL
# ============================================================

async def manejar_volver_reporte(query, context, reporte_id):
    """Vuelve al mensaje original del reporte (cuadrilla)"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            from app.telegram.keyboards import construir_botones_reporte

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return

            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

            mensaje = (
                f"🚨 *REPORTE ASIGNADO*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📋 *Folio:* #{reporte.id}\n"
                f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                f"📞 *Reportante:* {reporte.reportante}\n"
                f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
                f"📄 *Descripción:* {reporte.descripcion_problema[:150]}...\n\n"
                f"*📋 Acciones rápidas:*"
            )

            asignacion = Assignment.query.filter_by(
                report_id=reporte.id
            ).order_by(Assignment.timestamp.desc()).first()

            confirmado = False
            problema_reportado = False
            if asignacion and asignacion.status:
                if asignacion.status.descripcion == "En proceso":
                    confirmado = True
                elif asignacion.status.descripcion == "Problema ubicación":
                    problema_reportado = True

            reply_markup = construir_botones_reporte(
                reporte.id,
                confirmado=confirmado,
                problema_reportado=problema_reportado,
                context=context
            )

            # Enviar NUEVO mensaje (no editar)
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

            # Eliminar el mensaje de evidencia si existe
            try:
                await query.message.delete()
            except:
                pass

            await query.answer("↩️ Volviendo al reporte", show_alert=False)
            logger.info(f"↩️ Cuadrilla volvió al mensaje original del reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_volver_reporte: {e}")
        await query.answer("❌ Error al volver", show_alert=True)
