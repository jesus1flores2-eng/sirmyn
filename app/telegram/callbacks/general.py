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
    # DETECCIÓN PARA SOLICITUD DE APOYO DE OTRA CUADRILLA
    # ============================================================
    if callback_data.startswith('solicitar_apoyo_cuadrilla_'):
        reporte_id = int(callback_data.split('_')[-1])
        await manejar_solicitar_apoyo_cuadrilla(query, context, reporte_id)
        return

    # ============================================================
    # DETECCIÓN PARA ASIGNAR APOYO
    # ============================================================
    if callback_data.startswith('apoyo_asignar_'):
        reporte_id = int(callback_data.split('_')[-1])
        await manejar_mostrar_cuadrillas_apoyo(query, context, reporte_id)
        return

    if callback_data.startswith('apoyo_asignarc_'):
        partes = callback_data.split('_')
        reporte_id = int(partes[2])
        cuadrilla_id = int(partes[3])
        await manejar_asignar_apoyo(query, context, reporte_id, cuadrilla_id)
        return

    if callback_data.startswith('apoyo_confirmar_'):
        logger.info(f"⏩ Callback {callback_data} manejado por supervisor.py")
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

                # ⭐ NOTIFICAR AL DIRECTOR/JEFE TÉCNICO DEL ÁREA
                try:
                    from app.services.notification_service import notificar_director_aceptacion_cuadrilla
                    cuadrilla_nombre = usuario.team.nombre if usuario.team else "Cuadrilla desconocida"
                    await notificar_director_aceptacion_cuadrilla(
                        reporte_id=reporte.id,
                        cuadrilla_nombre=cuadrilla_nombre,
                        usuario_nombre=usuario.nombre
                    )
                except Exception as e:
                    logger.error(f"⚠️ Error notificando al director sobre aceptación: {e}")

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
            # ACCIÓN: EVIDENCIA
            # ============================================================
            elif accion == 'evidencia':
                if reporte.evidencia:
                    import os
                    from flask import url_for

                    if reporte.evidencia.startswith('http'):
                        evidencia_url = reporte.evidencia
                        nombre_archivo = os.path.basename(reporte.evidencia.split('/')[-1])
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
            # ACCIÓN: REPARACIÓN (VERSIÓN SIMPLE Y CORRECTA)
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

            # ============================================================
            # ACCIÓN: NO RECONOCIDA
            # ============================================================
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
            from app.models.user import User
            from app.routes.telegram_routes import get_telegram_app

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            usuario_solicitante = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            nombre_solicitante = usuario_solicitante.nombre if usuario_solicitante else query.from_user.first_name or "Cuadrilla"

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
                f"👷 *Solicitado por:* {nombre_solicitante}\n"
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
            logger.info(f"🛠️ Solicitud de retroexcavadora enviada por {nombre_solicitante} para reporte {reporte_id}")

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
            from app.models.user import User

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            usuario_solicitante = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            nombre_solicitante = usuario_solicitante.nombre if usuario_solicitante else query.from_user.first_name or "Cuadrilla"

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
                f"*Solicitado por:* {nombre_solicitante}\n\n"
                f"*Selecciona el material que necesita el camión:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )

            await query.answer("📋 Mostrando materiales", show_alert=False)
            logger.info(f"🚛 Mostrando materiales para solicitud de camión por {nombre_solicitante} en reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_solicitar_camion: {e}")
        await query.answer("❌ Error al mostrar materiales", show_alert=True)


# ============================================================
# MATERIAL SELECCIONADO
# ============================================================

async def manejar_material_seleccionado(query, context, reporte_id, material, tipo):
    """Envía solicitud al operador con el material seleccionado"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.models.user import User
            from app.routes.telegram_routes import get_telegram_app

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            usuario_solicitante = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            nombre_solicitante = usuario_solicitante.nombre if usuario_solicitante else query.from_user.first_name or "Cuadrilla"

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
                f"👷 *Solicitado por:* {nombre_solicitante}\n"
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

            try:
                await query.message.delete()
            except:
                pass

            await query.answer("✅ Solicitud enviada", show_alert=False)
            logger.info(f"🚛 Solicitud de material '{material}' enviada por {nombre_solicitante} para reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_material_seleccionado: {e}")
        await query.answer("❌ Error al enviar solicitud", show_alert=True)


# ============================================================
# SOLICITAR APOYO DE OTRA CUADRILLA (CON ASIGNACIÓN)
# ============================================================

async def manejar_solicitar_apoyo_cuadrilla(query, context, reporte_id):
    """
    Envía solicitud de apoyo a los supervisores/directores del área.
    Incluye botón "👷 Asignar cuadrilla de apoyo" y "✅ Confirmar recepción".
    """
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.user import User
            from app.models.team import Team
            from app.routes.telegram_routes import get_telegram_app

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.answer("❌ Reporte no encontrado.", show_alert=True)
                return

            # Obtener la cuadrilla actual (la que solicita apoyo)
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            if not asignacion or not asignacion.team_id:
                await query.answer("❌ No se encontró la cuadrilla asignada.", show_alert=True)
                return

            cuadrilla_actual = Team.query.get(asignacion.team_id)
            if not cuadrilla_actual:
                await query.answer("❌ Cuadrilla no encontrada.", show_alert=True)
                return

            # Obtener el nombre del solicitante
            usuario_solicitante = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            nombre_solicitante = usuario_solicitante.nombre if usuario_solicitante else query.from_user.first_name or "Cuadrilla"

            # Buscar responsables (supervisores o directores del área)
            area = cuadrilla_actual.area

            # Buscar supervisores del área
            supervisores = User.query.filter_by(
                area=area,
                rol_especifico='supervisor',
                is_active=True
            ).all()

            # Si no hay supervisores, buscar directores
            if not supervisores:
                supervisores = User.query.filter_by(
                    area=area,
                    rol_especifico='director',
                    is_active=True
                ).all()

            if not supervisores:
                # Fallback: buscar jefe de área técnica
                supervisores = User.query.filter_by(
                    area=area,
                    rol_especifico='jefe_area_tecnica',
                    is_active=True
                ).all()

            if not supervisores:
                await query.answer("❌ No hay supervisores disponibles para este área", show_alert=True)
                await query.message.reply_text(
                    "⚠️ *No se pudo enviar la solicitud de apoyo*\n\n"
                    "No hay supervisores o directores registrados para esta área.\n\n"
                    "📌 *Acción:* Contacta al administrador para registrar un supervisor.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"

            mensaje_supervisor = (
                f"👷 *SOLICITUD DE APOYO - OTRA CUADRILLA*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {direccion}\n"
                f"👷 *Cuadrilla solicitante:* {cuadrilla_actual.nombre}\n"
                f"👤 *Solicitado por:* {nombre_solicitante}\n"
                f"⏰ *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*🚨 Se solicita apoyo de otra cuadrilla para atender este reporte.*\n"
                f"*🔧 Motivo:* La cuadrilla actual requiere refuerzos o personal adicional.\n\n"
                f"*📋 ACCIONES:*"
            )

            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                mensaje_supervisor += f"\n\n🗺️ [Ver en Google Maps]({maps_url})"

            # ⭐ DOS BOTONES: Asignar apoyo + Confirmar recepción
            keyboard = [
                [
                    InlineKeyboardButton("👷 Asignar cuadrilla de apoyo", callback_data=f"apoyo_asignar_{reporte_id}")
                ],
                [
                    InlineKeyboardButton("✅ Confirmar recepción", callback_data=f"apoyo_confirmar_{reporte_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            bot_app = get_telegram_app()

            # Enviar a todos los supervisores/directores
            enviados = 0
            for responsable in supervisores:
                if responsable.telegram_id:
                    try:
                        await bot_app.bot.send_message(
                            chat_id=int(responsable.telegram_id),
                            text=mensaje_supervisor,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup
                        )
                        enviados += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {responsable.nombre}: {e}")

            await query.message.reply_text(
                f"✅ *Solicitud de apoyo enviada*\n\n"
                f"Se ha notificado a {enviados} supervisor(es) del área.\n"
                f"📍 Ubicación: {direccion}\n\n"
                f"*Se te notificará cuando un supervisor asigne o confirme el apoyo.*",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.answer("✅ Solicitud de apoyo enviada", show_alert=False)
            logger.info(f"👷 Solicitud de apoyo enviada para reporte {reporte_id} a {enviados} responsables")

    except Exception as e:
        logger.error(f"❌ Error en manejar_solicitar_apoyo_cuadrilla: {e}")
        await query.answer("❌ Error al enviar solicitud", show_alert=True)


# ============================================================
# MOSTRAR CUADRILLAS PARA APOYO
# ============================================================

async def manejar_mostrar_cuadrillas_apoyo(query, context, reporte_id):
    """Muestra las cuadrillas disponibles para asignar como apoyo"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.team import Team
            from app.models.user import User

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return

            # Obtener la cuadrilla actual (para no mostrarla)
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            cuadrilla_actual_id = asignacion.team_id if asignacion else None

            # Obtener cuadrillas del mismo área excepto la actual y "Sin asignar"
            mapeo_tipo_a_area = {
                "Agua potable": "agua",
                "Drenaje": "agua",
                "Aseo público": "aseo",
                "Alumbrado público": "alumbrado",
                "Parques y jardines": "parques",
                "Ecología": "ecologia",
                "Seguridad pública": "seguridad",
                "Obras públicas": "obras",
                "Bomberos": "bomberos"
            }
            area_buscar = mapeo_tipo_a_area.get(reporte.tipo, "general")

            cuadrillas = Team.query.filter(
                Team.area == area_buscar,
                Team.nombre != "Sin asignar",
                Team.id != cuadrilla_actual_id
            ).order_by(Team.nombre).all()

            # Si no hay cuadrillas del área, mostrar todas excepto "Sin asignar" y la actual
            if not cuadrillas:
                cuadrillas = Team.query.filter(
                    Team.nombre != "Sin asignar",
                    Team.id != cuadrilla_actual_id
                ).order_by(Team.nombre).all()

            if not cuadrillas:
                await query.edit_message_text(
                    f"❌ *No hay cuadrillas disponibles para apoyo*\n\n"
                    f"No se encontraron otras cuadrillas en el área.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Crear teclado con cuadrillas
            keyboard = []
            for cuadrilla in cuadrillas:
                usuarios_count = User.query.filter_by(team_id=cuadrilla.id).count()
                texto_boton = f"👷 {cuadrilla.nombre}"
                if usuarios_count > 0:
                    texto_boton += f" ({usuarios_count})"
                keyboard.append([
                    InlineKeyboardButton(
                        texto_boton,
                        callback_data=f"apoyo_asignarc_{reporte_id}_{cuadrilla.id}"
                    )
                ])

            keyboard.append([
                InlineKeyboardButton("↩️ Cancelar", callback_data=f"volver_reporte_{reporte_id}")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

            mensaje = (
                f"👷 *ASIGNAR CUADRILLA DE APOYO*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n\n"
                f"*Selecciona la cuadrilla de apoyo:*"
            )

            await query.edit_message_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )

            logger.info(f"✅ Mostrando {len(cuadrillas)} cuadrillas para apoyo en reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_mostrar_cuadrillas_apoyo: {e}")
        await query.edit_message_text("❌ Error al cargar cuadrillas.")


# ============================================================
# ASIGNAR CUADRILLA DE APOYO (CON GPS)
# ============================================================

async def manejar_asignar_apoyo(query, context, reporte_id, cuadrilla_id):
    """Asigna una cuadrilla de apoyo al reporte con GPS"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.user import User
            from app.models.team import Team
            from app.models.status import Status
            from app.extensions import db
            from app.services.notification_service import notificar_jefe_area_apoyo

            reporte = Report.query.get(reporte_id)
            cuadrilla_apoyo = Team.query.get(cuadrilla_id)

            if not reporte or not cuadrilla_apoyo:
                await query.edit_message_text("❌ Datos no válidos.")
                return

            # Obtener la cuadrilla actual
            asignacion_actual = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            cuadrilla_actual = Team.query.get(asignacion_actual.team_id) if asignacion_actual else None
            nombre_cuadrilla_actual = cuadrilla_actual.nombre if cuadrilla_actual else "Cuadrilla desconocida"

            # Obtener el supervisor que asigna
            supervisor = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            nombre_supervisor = supervisor.nombre if supervisor else "Supervisor"

            # Obtener estado "Asignado"
            status_asignado = Status.query.filter_by(descripcion="Asignado").first()
            if not status_asignado:
                status_asignado = Status(descripcion="Asignado")
                db.session.add(status_asignado)
                db.session.commit()

            # Crear asignación para la cuadrilla de apoyo
            nueva_asignacion = Assignment(
                report_id=reporte_id,
                team_id=cuadrilla_id,
                status_id=status_asignado.id,
                timestamp=datetime.utcnow(),
                observaciones=f"Cuadrilla de apoyo asignada por {nombre_supervisor} para ayudar a {nombre_cuadrilla_actual}"
            )
            db.session.add(nueva_asignacion)
            db.session.commit()

            # ============================================================
            # NOTIFICACIONES CON GPS
            # ============================================================

            bot = context.bot
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"

            # ⭐ CONSTRUIR TEXTO GPS PARA TODOS LOS MENSAJES
            gps_texto = ""
            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                gps_texto = f"\n\n📍 *Ubicación exacta:* [Ver en Google Maps]({maps_url})"

            # 1. NOTIFICAR A LA CUADRILLA ORIGINAL
            usuarios_original = User.query.filter_by(team_id=asignacion_actual.team_id, is_active=True).all()
            for usuario in usuarios_original:
                if usuario.telegram_id:
                    try:
                        mensaje = (
                            f"👷 *APOYO ASIGNADO - Reporte #{reporte.id}*\n\n"
                            f"Se ha asignado la cuadrilla *{cuadrilla_apoyo.nombre}* como apoyo.\n\n"
                            f"📍 *Ubicación:* {direccion}"
                            f"{gps_texto}"
                            f"\n\n🤝 *Trabajarán juntos para resolver el reporte.*"
                        )
                        await bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=False
                        )
                    except Exception as e:
                        logger.error(f"❌ Error notificando a cuadrilla original: {e}")

            # 2. NOTIFICAR A LA CUADRILLA DE APOYO
            usuarios_apoyo = User.query.filter_by(team_id=cuadrilla_id, is_active=True).all()
            for usuario in usuarios_apoyo:
                if usuario.telegram_id:
                    try:
                        mensaje = (
                            f"👷 *HAS SIDO ASIGNADO COMO APOYO*\n\n"
                            f"📋 *Reporte:* #{reporte.id}\n"
                            f"📍 *Ubicación:* {direccion}\n"
                            f"🔧 *Problema:* {reporte.tipo} - {reporte.subtipo}\n"
                            f"🤝 *Cuadrilla principal:* {nombre_cuadrilla_actual}"
                            f"{gps_texto}"
                            f"\n\n*🚨 Apoya a la cuadrilla principal en este reporte.*"
                        )
                        await bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=False
                        )
                    except Exception as e:
                        logger.error(f"❌ Error notificando a cuadrilla de apoyo: {e}")

            # 3. NOTIFICAR AL JEFE DE ÁREA TÉCNICA (INFORMATIVO)
            await notificar_jefe_area_apoyo(
                reporte_id=reporte.id,
                cuadrilla_principal=nombre_cuadrilla_actual,
                cuadrilla_apoyo=cuadrilla_apoyo.nombre,
                supervisor=nombre_supervisor
            )

            # 4. CONFIRMAR AL SUPERVISOR
            mensaje_confirmacion = (
                f"✅ *APOYO ASIGNADO CORRECTAMENTE*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"👷 *Cuadrilla principal:* {nombre_cuadrilla_actual}\n"
                f"👷 *Cuadrilla de apoyo:* {cuadrilla_apoyo.nombre}\n"
                f"📍 *Ubicación:* {direccion}"
                f"{gps_texto}"
                f"\n\n*Notificaciones enviadas:*\n"
                f"• ✅ Cuadrilla original\n"
                f"• ✅ Cuadrilla de apoyo\n"
                f"• ✅ Jefe de área técnica\n\n"
                f"*Asignado por:* {nombre_supervisor}\n"
                f"*Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )

            await query.edit_message_text(
                text=mensaje_confirmacion,
                parse_mode=ParseMode.MARKDOWN
            )

            logger.info(f"✅ Supervisor {nombre_supervisor} asignó apoyo al reporte #{reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_asignar_apoyo: {e}")
        await query.edit_message_text("❌ Error al asignar apoyo.")


# ============================================================
# VOLVER AL REPORTE ORIGINAL
# ============================================================

async def manejar_volver_reporte(query, context, reporte_id):
    """Vuelve al mensaje original del reporte (cuadrilla) con todos los botones activos"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            from app.models.user import User
            from app.models.team import Team
            from app.telegram.keyboards import construir_botones_reporte

            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return

            # Obtener la última asignación para saber el estado
            asignacion = Assignment.query.filter_by(
                report_id=reporte.id
            ).order_by(Assignment.timestamp.desc()).first()

            # Obtener el usuario que está presionando el botón
            usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            
            # Determinar si está confirmado o hay problema de ubicación
            confirmado = False
            problema_reportado = False
            if asignacion and asignacion.status:
                if asignacion.status.descripcion == "En proceso":
                    confirmado = True
                elif asignacion.status.descripcion == "Problema ubicación":
                    problema_reportado = True

            # ⭐ CONSTRUIR MENSAJE CON TODOS LOS DATOS
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
            )

            # ⭐ AGREGAR EVIDENCIA SI EXISTE
            if reporte.evidencia:
                from app.services.notification_service import construir_enlace_evidencia
                enlace, _ = construir_enlace_evidencia(reporte.evidencia, "evidencia_usuario")
                mensaje += f"📎 *Evidencia:* {enlace}\n\n"

            # ⭐ AGREGAR MAPA SI HAY COORDENADAS
            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                mensaje += f"📍 *Ver en mapa:* [Google Maps]({maps_url})\n\n"

            mensaje += f"*📋 Acciones rápidas:*"

            # ⭐ CONSTRUIR BOTONES CON EL USUARIO QUE PRESIONÓ
            reply_markup = construir_botones_reporte(
                reporte.id,
                confirmado=confirmado,
                problema_reportado=problema_reportado,
                context=context,
                user_id=query.from_user.id
            )

            # ⭐ ENVIAR NUEVO MENSAJE (NO editar el anterior)
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

            # ⭐ ELIMINAR EL MENSAJE ANTERIOR (el de la evidencia)
            try:
                await query.message.delete()
            except:
                pass

            await query.answer("↩️ Volviendo al reporte", show_alert=False)
            logger.info(f"↩️ Cuadrilla volvió al mensaje original del reporte {reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_volver_reporte: {e}")
        await query.answer("❌ Error al volver", show_alert=True)
