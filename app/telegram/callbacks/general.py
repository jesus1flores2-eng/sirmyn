# app/telegram/callbacks/general.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
from app.services.db_manager import DatabaseManager
from app.telegram.keyboards import construir_botones_reporte, obtener_carpeta_departamento
import logging, os, re, uuid
from datetime import datetime

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
    
    # Ignorar callbacks que no son de este handler (dir_, pres_, dash_, etc.)
    if callback_data.startswith(('dir_', 'pres_', 'dash_', 'super_', 'reasignar_', 'usuario_', 'enc_', 'rech_')):
        logger.info(f"⏩ Callback {callback_data} ignorado, va a su handler específico")
        return
    
    # ============================================================
    # MANEJAR CALLBACKS DE CUADRILLAS
    # ============================================================
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment, Localidad, Calle
            from app.models.user import User
            from app.models.team import Team
            from app.models.status import Status
            from app.extensions import db
            from app.services.geocoding import buscar_localidad_flexible, buscar_calle_flexible
            import os, asyncio
            
            # Extraer datos del callback
            if '_' in callback_data:
                partes = callback_data.split('_', 1)
                accion = partes[0]
                reporte_id_str = partes[1] if len(partes) > 1 else ''
                
                # Validar que reporte_id sea numérico
                if not reporte_id_str.isdigit():
                    # Botones especiales como "confirmado_ya" o "problema_ya"
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
                
                # Verificar que el usuario esté vinculado
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
                        # Cambiar a estado "En proceso"
                        status_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
                        if not status_en_proceso:
                            status_en_proceso = Status(descripcion="En proceso")
                            db.session.add(status_en_proceso)
                            db.session.commit()
                        
                        asignacion.status_id = status_en_proceso.id
                        asignacion.observaciones = f"Confirmado por {usuario.nombre} via Telegram"
                        db.session.commit()
                    
                    # Actualizar mensaje
                    reply_markup = construir_botones_reporte(reporte.id, confirmado=True, context=context)
                    
                    # Obtener dirección para el mapa
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
                    
                    # Notificar al administrador
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
                    # Cambiar estado a "Problema ubicación" (ID: 9)
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
                    
                    # Actualizar mensaje
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
                    
                    # Solicitar ubicación exacta al reportante (esto es complejo, por ahora solo notificamos)
                    # Aquí podrías llamar a una función que notifique al reportante pidiendo ubicación exacta
                    
                    await query.answer("⚠️ Problema de ubicación reportado", show_alert=False)
                    logger.info(f"⚠️ Problema de ubicación en reporte {reporte_id}")
                
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
                    
                    # Enviar como mensaje nuevo
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
                        server_url = app.config.get('SERVER_URL', 'http://localhost:5000')
                        evidencia_url = f"{server_url}/admin/uploads/{reporte.evidencia}"
                        await context.bot.send_message(
                            chat_id=query.from_user.id,
                            text=f"📎 <b>Evidencia del reporte #{reporte.id}</b>\n\n🔗 Enlace:\n{evidencia_url}",
                            parse_mode=ParseMode.HTML
                        )
                        await query.answer("🔗 Evidencia enviada", show_alert=False)
                    else:
                        await query.answer("❌ No hay evidencia disponible", show_alert=True)
                
                # ============================================================
                # ACCIÓN: REPARACIÓN (iniciar flujo de subida de evidencia)
                # ============================================================
                elif accion == 'reparacion':
                    # Verificar que el usuario sea la cuadrilla asignada
                    asignacion = Assignment.query.filter_by(
                        report_id=reporte_id
                    ).order_by(Assignment.timestamp.desc()).first()
                    
                    if not usuario or not asignacion:
                        await query.answer("❌ No se pudo verificar la asignación", show_alert=True)
                        return
                    
                    if usuario.team_id != asignacion.team_id:
                        await query.answer("❌ No estás asignado a este reporte", show_alert=True)
                        return
                    
                    # Iniciar modo reparación
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
                    
    except Exception as e:
        logger.error(f"❌ Error en button_callback_handler: {e}", exc_info=True)
        try:
            await query.edit_message_text(
                text="❌ Ocurrió un error al procesar la acción. Intenta nuevamente.",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
