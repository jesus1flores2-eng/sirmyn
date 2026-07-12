from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data, limpiar_estado, actualizar_timestamp_usuario, buscar_coincidencias_flexibles, _normalize_text
from app.services.db_manager import DatabaseManager
import logging, re

logger = logging.getLogger(__name__)

def obtener_localidades_con_fallback():
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Localidad
            localidades = Localidad.query.all()
            if localidades:
                return [(loc.id, loc.nombre) for loc in localidades]
            else:
                logger.warning("⚠️ No hay localidades en la base de datos")
                return []
    except Exception as e:
        logger.error(f"❌ Error obteniendo localidades: {e}")
        return []

def obtener_calles_con_fallback(localidad_id):
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Calle
            calles = Calle.query.filter_by(localidad_id=localidad_id).all()
            if calles:
                return [(calle.id, calle.nombre) for calle in calles]
            else:
                logger.warning(f"⚠️ No hay calles para localidad {localidad_id}")
                return []
    except Exception as e:
        logger.error(f"❌ Error obteniendo calles: {e}")
        return []

async def elegir_ubicacion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto_original = update.message.text.strip()
    
    if texto_original.lower() in ["❌ cancelar", "cancelar", "cancel"] or "❌" in texto_original:
        await update.message.reply_text(
            "💙 *Nos da tristeza que no hayas completado tu reporte.*\n\n"
            "📌 *Recuerda que puedes:*\n"
            "• Usar /start cuando estés listo para comenzar de nuevo\n"
            "• Escribir tu dirección manualmente si el GPS no funciona\n"
            "• Contactar al administrador si necesitas ayuda\n\n"
            "🌐 *Estamos aquí para servirte. ¡Vuelve pronto!*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if texto_original in ["📍 Compartir ubicación GPS", "📍", "GPS"] or "gps" in texto_original.lower():
        keyboard = [[KeyboardButton("📍 Compartir mi ubicación", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "📍 *Comparte tu ubicación GPS:*\n\nToca el botón azul '📍 Compartir mi ubicación' de abajo.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ELEGIR_UBICACION
    
    if texto_original in ["🏠 Escribir dirección manualmente", "🏠", "Manual"] or "manual" in texto_original.lower():
        await update.message.reply_text(
            "📍 *Escribe la localidad/colonia* (o las primeras letras):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return LOCALIDAD
    
    keyboard = [
        ["📍 Compartir ubicación GPS"],
        ["🏠 Escribir dirección manualmente"],
        ["❌ Cancelar"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "📍 *¿Cómo quieres proporcionar la ubicación?*\n\nSelecciona una opción:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ELEGIR_UBICACION

async def ubicacion_gps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la ubicación GPS enviada durante la creación de un reporte - CORREGIDO"""
    print("🚨🚨🚨 UBICACION_GPS_HANDLER EJECUTADO 🚨🚨🚨")
    try:
        user_id = update.effective_user.id
        location = update.message.location
        print(f"📍 Lat: {location.latitude}, Lon: {location.longitude}")
        
        # ⭐ SIEMPRE guardar coordenadas GPS
        user_data[user_id]["latitud"] = location.latitude
        user_data[user_id]["longitud"] = location.longitude
        user_data[user_id]["ubicacion_gps"] = True
        
        # Intentar obtener dirección por reverse geocoding (solo para referencia)
        from app.services.geocoding import obtener_direccion_osm, buscar_localidad_flexible, buscar_calle_flexible
        
        localidad_detectada = None
        calle_detectada = None
        
        direccion = obtener_direccion_osm(location.latitude, location.longitude)
        if direccion and direccion.get('road') and direccion.get('localidad'):
            localidad_detectada = direccion['localidad']
            calle_detectada = direccion['road']
        else:
            # Si no se detecta dirección, usar valores por defecto
            print("⚠️ No se pudo detectar dirección, usando valores predeterminados")
        
        # ⭐ Buscar localidad en BD (si se detectó)
        if localidad_detectada:
            resultado_localidad = buscar_localidad_flexible(localidad_detectada)
            if resultado_localidad:
                loc_id, loc_nombre = resultado_localidad
                user_data[user_id]["localidad_id"] = loc_id
                user_data[user_id]["localidad_nombre"] = loc_nombre
                
                # Buscar calle (si se detectó y la localidad existe)
                if calle_detectada:
                    resultado_calle = buscar_calle_flexible(calle_detectada, loc_id)
                    if resultado_calle:
                        calle_id, calle_nombre = resultado_calle
                        user_data[user_id]["calle_id"] = calle_id
                        user_data[user_id]["calle_nombre"] = calle_nombre
        
        # ⭐ SI no se encontró localidad o calle, usar valores predeterminados
        if not user_data[user_id].get("localidad_nombre"):
            user_data[user_id]["localidad_nombre"] = "Ubicación GPS"
            # Buscar una localidad por defecto o usar None
            localidad_defecto = Localidad.query.first() if Localidad.query.count() > 0 else None
            if localidad_defecto:
                user_data[user_id]["localidad_id"] = localidad_defecto.id
            else:
                user_data[user_id]["localidad_id"] = None
        
        if not user_data[user_id].get("calle_nombre"):
            user_data[user_id]["calle_nombre"] = "Calle GPS"
            user_data[user_id]["calle_id"] = None
        
        # ⭐ Mostrar confirmación y pedir número (sin pedir localidad o calle)
        localidad_mostrar = user_data[user_id].get("localidad_nombre", "Ubicación GPS")
        calle_mostrar = user_data[user_id].get("calle_nombre", "Calle GPS")
        
        await update.message.reply_text(
            f"✅ *Ubicación GPS recibida*\n\n"
            f"📍 *Coordenadas:*\n"
            f"Latitud: {location.latitude}\n"
            f"Longitud: {location.longitude}\n"
            f"📍 *Localidad:* {localidad_mostrar}\n"
            f"🛣️ *Calle:* {calle_mostrar}\n\n"
            "📝 **Escribe el número exterior o referencia:**\n"
            "(Ej: 123, Casa azul, S/N)",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return NUMERO
            
    except Exception as e:
        print(f"❌ ERROR en ubicacion_gps_handler: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "❌ Ocurrió un error al procesar tu ubicación.\n"
            "Por favor, escribe la dirección manualmente:",
            reply_markup=ReplyKeyboardRemove()
        )
        return LOCALIDAD

async def localidad_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text.strip()
    
    # ⭐ LIMPIAR SUGERENCIAS ANTERIORES (para que la segunda búsqueda funcione)
    user_data[user_id].pop("sugerencias_localidad", None)
    
    if entrada.lower() == "cancelar":
        await update.message.reply_text(
            "💙 *Nos da tristeza que no hayas completado tu reporte.*\n\n"
            "📌 *Recuerda que puedes:*\n"
            "• Usar /start cuando estés listo para comenzar de nuevo\n"
            "• Escribir tu dirección manualmente si el GPS no funciona\n"
            "• Contactar al administrador si necesitas ayuda\n\n"
            "🌐 *Estamos aquí para servirte. ¡Vuelve pronto!*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    candidatos = obtener_localidades_con_fallback()
    if not candidatos:
        await update.message.reply_text(
            "⚠️ No hay localidades registradas en el sistema.\nPor favor, contacta al administrador.",
            reply_markup=ReplyKeyboardRemove()
        )
        return LOCALIDAD
    
    sugerencias = buscar_coincidencias_flexibles(entrada, candidatos)
    user_data[user_id]["sugerencias_localidad"] = sugerencias
    
    if sugerencias:
        keyboard = []
        for i, sug in enumerate(sugerencias[:5], 1):
            keyboard.append([f"{i}. {sug['nombre']}"])
        keyboard.append(["✏️ Escribir de nuevo"])
        keyboard.append(["📋 Ver lista completa"])
        keyboard.append(["❌ Cancelar"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        mensaje = "🔍 Encontré varias localidades similares:\n\n"
        for i, sug in enumerate(sugerencias[:5], 1):
            mensaje += f"{i}. {sug['nombre']}\n"
        mensaje += "\nSelecciona una opción:"
        
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
        return LOCALIDAD_SUGERENCIAS
    else:
        # ⭐ MOSTRAR EJEMPLOS REALES cuando no encuentre coincidencias
        ejemplos = [nombre for _, nombre in candidatos[:8]]
        mensaje = (
            f"❌ No encontré coincidencias para '*{entrada}*'.\n\n"
            f"💡 *Ejemplos de localidades disponibles:*\n"
        )
        for i, nombre in enumerate(ejemplos, 1):
            mensaje += f"{i}. {nombre}\n"
        mensaje += (
            f"\n📌 *Puedes:*\n"
            f"• Escribir el nombre completo de la localidad\n"
            f"• Usar solo la primera palabra (ej: 'Ixtlahuacán')\n"
            f"• Escribir '📋 Ver lista completa' para ver todas\n"
            f"• Escribir 'cancelar' para salir\n\n"
            f"*Escribe la localidad/colonia:*"
        )
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return LOCALIDAD

async def localidad_sugerencias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar" or "cancelar" in texto.lower():
        await update.message.reply_text(
            "💙 *Nos da tristeza que no hayas completado tu reporte.*\n\n"
            "📌 *Recuerda que puedes:*\n"
            "• Usar /start cuando estés listo para comenzar de nuevo\n\n"
            "🌐 *Estamos aquí para servirte. ¡Vuelve pronto!*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    # ⭐ NUEVA OPCIÓN: Ver lista completa
    if "lista completa" in texto.lower() or "📋" in texto:
        candidatos = obtener_localidades_con_fallback()
        if candidatos:
            mensaje = "📋 *LISTA COMPLETA DE LOCALIDADES:*\n\n"
            for i, (_, nombre) in enumerate(candidatos, 1):
                mensaje += f"{i}. {nombre}\n"
            mensaje += "\n*Escribe el nombre exacto de la localidad:*"
            
            await update.message.reply_text(
                mensaje,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return LOCALIDAD
        else:
            await update.message.reply_text(
                "⚠️ No hay localidades registradas.",
                reply_markup=ReplyKeyboardRemove()
            )
            return LOCALIDAD
    
    if "escribir" in texto.lower() or "✏️" in texto:
        await update.message.reply_text(
            "📍 Escribe la *localidad/colonia* (o las primeras letras):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return LOCALIDAD
    
    numeros = re.findall(r'\d+', texto)
    if numeros:
        num = int(numeros[0])
        sugerencias = user_data[user_id].get("sugerencias_localidad", [])
        if 1 <= num <= len(sugerencias):
            localidad = sugerencias[num - 1]
            user_data[user_id]["localidad_id"] = localidad["id"]
            user_data[user_id]["localidad_nombre"] = localidad["nombre"]
            
            await update.message.reply_text(
                f"✅ Localidad: {localidad['nombre']}\n\nAhora escribe la *calle* (o las primeras letras).",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return CALLE
    
    await update.message.reply_text(
        "No pude identificar la localidad. Intenta de nuevo o escribe 'cancelar'.",
        reply_markup=ReplyKeyboardRemove()
    )
    return LOCALIDAD_SUGERENCIAS

async def calle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text.strip()
    
    # ⭐ LIMPIAR SUGERENCIAS ANTERIORES (para que la segunda búsqueda funcione)
    user_data[user_id].pop("sugerencias_calle", None)
    
    if entrada.lower() == "cancelar":
        await update.message.reply_text(
            "💙 *Nos da tristeza que no hayas completado tu reporte.*\n\n"
            "📌 *Recuerda que puedes:*\n"
            "• Usar /start cuando estés listo para comenzar de nuevo\n\n"
            "🌐 *Estamos aquí para servirte. ¡Vuelve pronto!*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    loc_id = user_data[user_id].get("localidad_id")
    if not loc_id:
        await update.message.reply_text(
            "Primero selecciona una localidad. Escribe la *localidad/colonia*:",
            parse_mode="Markdown"
        )
        return LOCALIDAD
    
    candidatos = obtener_calles_con_fallback(loc_id)
    if not candidatos:
        await update.message.reply_text(
            f"⚠️ No hay calles registradas para esta localidad.\nPor favor, escribe el nombre de la calle manualmente:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CALLE
    
    sugerencias = buscar_coincidencias_flexibles(entrada, candidatos)
    user_data[user_id]["sugerencias_calle"] = sugerencias
    
    if sugerencias:
        keyboard = []
        for i, sug in enumerate(sugerencias[:5], 1):
            keyboard.append([f"{i}. {sug['nombre']}"])
        keyboard.append(["✏️ Escribir de nuevo"])
        keyboard.append(["📋 Ver lista completa"])
        keyboard.append(["❌ Cancelar"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        mensaje = "🔍 Encontré varias calles similares:\n\n"
        for i, sug in enumerate(sugerencias[:5], 1):
            mensaje += f"{i}. {sug['nombre']}\n"
        mensaje += "\nSelecciona una opción:"
        
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
        return CALLE_SUGERENCIAS
    else:
        # ⭐ MOSTRAR EJEMPLOS REALES de calles de esta localidad
        ejemplos = [nombre for _, nombre in candidatos[:8]]
        mensaje = (
            f"❌ No encontré coincidencias para '*{entrada}*'.\n\n"
            f"💡 *Ejemplos de calles en {user_data[user_id].get('localidad_nombre', 'esta localidad')}:*\n"
        )
        for i, nombre in enumerate(ejemplos, 1):
            mensaje += f"{i}. {nombre}\n"
        mensaje += (
            f"\n📌 *Puedes:*\n"
            f"• Escribir el nombre completo de la calle\n"
            f"• Escribir '📋 Ver lista completa' para ver todas\n"
            f"• Escribir 'cancelar' para salir\n\n"
            f"*Escribe la calle:*"
        )
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return CALLE

async def calle_sugerencias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar" or "cancelar" in texto.lower():
        await update.message.reply_text(
            "💙 *Nos da tristeza que no hayas completado tu reporte.*\n\n"
            "📌 *Recuerda que puedes:*\n"
            "• Usar /start cuando estés listo para comenzar de nuevo\n\n"
            "🌐 *Estamos aquí para servirte. ¡Vuelve pronto!*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    # ⭐ NUEVA OPCIÓN: Ver lista completa de calles
    if "lista completa" in texto.lower() or "📋" in texto:
        loc_id = user_data[user_id].get("localidad_id")
        if loc_id:
            candidatos = obtener_calles_con_fallback(loc_id)
            if candidatos:
                mensaje = f"📋 *LISTA COMPLETA DE CALLES en {user_data[user_id].get('localidad_nombre', 'esta localidad')}:*\n\n"
                for i, (_, nombre) in enumerate(candidatos, 1):
                    mensaje += f"{i}. {nombre}\n"
                mensaje += "\n*Escribe el nombre exacto de la calle:*"
                
                await update.message.reply_text(
                    mensaje,
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                return CALLE
            else:
                await update.message.reply_text(
                    "⚠️ No hay calles registradas para esta localidad.",
                    reply_markup=ReplyKeyboardRemove()
                )
                return CALLE
        else:
            await update.message.reply_text(
                "Primero selecciona una localidad.",
                reply_markup=ReplyKeyboardRemove()
            )
            return LOCALIDAD
    
    if "escribir" in texto.lower() or "✏️" in texto:
        await update.message.reply_text(
            "Escribe la *calle* (o las primeras letras):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return CALLE
    
    numeros = re.findall(r'\d+', texto)
    if numeros:
        num = int(numeros[0])
        sugerencias = user_data[user_id].get("sugerencias_calle", [])
        if 1 <= num <= len(sugerencias):
            calle = sugerencias[num - 1]
            user_data[user_id]["calle_id"] = calle["id"]
            user_data[user_id]["calle_nombre"] = calle["nombre"]
            
            await update.message.reply_text(
                f"✅ Calle: {calle['nombre']}\n\nEscribe el *número exterior* (o 'S/N'):",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return NUMERO
    
    await update.message.reply_text(
        "No pude identificar la calle. Intenta de nuevo o escribe 'cancelar'.",
        reply_markup=ReplyKeyboardRemove()
    )
    return CALLE_SUGERENCIAS

# ============================================================================
# FUNCIÓN: SOLICITAR UBICACIÓN EXACTA (para problemas de ubicación)
# ============================================================================

async def solicitar_ubicacion_exacta_al_reportante(reporte_id: int, cuadrilla_nombre: str, context=None):
    """
    Solicita al reportante que envíe su ubicación GPS exacta.
    Se usa cuando la cuadrilla reporta problema de ubicación.
    
    Args:
        reporte_id: ID del reporte
        cuadrilla_nombre: Nombre de la cuadrilla que reporta el problema
        context: Contexto de Telegram (opcional). Si no se proporciona, usa get_telegram_app()
    
    Returns:
        bool: True si se envió correctamente, False en caso contrario
    """
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"📍 [UBICACION] Solicitando ubicación exacta para reporte #{reporte_id}")
        
        app = DatabaseManager.get_app()
        
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            from app.extensions import db
            from datetime import datetime
            
            # 1. Obtener reporte
            reporte = Report.query.get(reporte_id)
            if not reporte:
                logger.error(f"❌ Reporte {reporte_id} no encontrado")
                return False
            
            # 2. Obtener telegram_id del reportante
            telegram_id_reportante = reporte.telefono
            if not telegram_id_reportante:
                logger.error(f"❌ Reporte {reporte_id} no tiene teléfono")
                return False
            
            try:
                user_id = int(str(telegram_id_reportante).strip())
            except ValueError:
                logger.error(f"❌ Telegram ID inválido: {telegram_id_reportante}")
                return False
            
            # 3. Cambiar estado a "Problema ubicación" (ID 9 o buscar por nombre)
            status_problema = Status.query.get(9)
            if not status_problema:
                status_problema = Status.query.filter_by(descripcion="Problema ubicación").first()
                if not status_problema:
                    status_problema = Status(descripcion="Problema ubicación", color="warning")
                    db.session.add(status_problema)
                    db.session.commit()
                    logger.info(f"✅ Estado 'Problema ubicación' creado con ID {status_problema.id}")
            
            # Actualizar asignación
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            if asignacion:
                asignacion.status_id = status_problema.id
                asignacion.observaciones = f"Problema de ubicación - Cuadrilla {cuadrilla_nombre}"
                db.session.commit()
                logger.info(f"✅ Estado actualizado a 'Problema ubicación' para reporte #{reporte_id}")
            else:
                logger.warning(f"⚠️ No hay asignación para reporte #{reporte_id}")
            
            # 4. Guardar estado en user_data para manejar la respuesta
            user_data[user_id] = {
                'modo_ubicacion_exacta': True,
                'reporte_id': reporte_id,
                'cuadrilla_nombre': cuadrilla_nombre,
                'timestamp': datetime.now().isoformat()
            }
            logger.info(f"💾 Estado guardado en user_data para usuario {user_id}")
            
            # 5. Obtener el bot (si no hay context, usar get_telegram_app)
            if context is None:
                from app.routes.telegram_routes import get_telegram_app
                bot_app = get_telegram_app()
                if not bot_app or not bot_app.bot:
                    logger.error("❌ Bot de Telegram no disponible")
                    return False
                bot = bot_app.bot
            else:
                bot = context.bot
            
            # 6. Enviar mensaje al reportante
            mensaje = (
                f"⚠️ *UBICACIÓN NO ENCONTRADA*\n\n"
                f"La cuadrilla *{cuadrilla_nombre}* no pudo encontrar tu ubicación.\n\n"
                f"📍 *Cómo enviar tu ubicación exacta:*\n"
                f"1. Ve al lugar del reporte\n"
                f"2. Toca el ícono 📎 (clip) en el chat\n"
                f"3. Selecciona '📍 Ubicación'\n"
                f"4. Envía tu ubicación actual\n\n"
                f"⏰ *Tienes 24 horas para responder.*\n\n"
                f"*Si no respondes, el reporte se cancelará automáticamente.*"
            )
            
            await bot.send_message(
                chat_id=user_id,
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            
            logger.info(f"✅ Solicitud de ubicación enviada al reportante {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error en solicitar_ubicacion_exacta_al_reportante: {e}", exc_info=True)
        return False

# ============================================================================
# NUEVO HANDLER: RESPUESTA A PROBLEMA DE UBICACIÓN (GPS)
# ============================================================================

async def manejar_ubicacion_problema_gps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja la ubicación GPS enviada por el reportante en respuesta a un problema de ubicación.
    VERSIÓN CORREGIDA: usa exclusivamente context.bot para enviar mensajes.
    """
    user_id = update.effective_user.id
    location = update.message.location

    logger.info(f"📍 [PROBLEMA GPS] Usuario {user_id} envió ubicación en modo_exacta")

    # Verificar que esté en modo_ubicacion_exacta
    user_data_entry = user_data.get(user_id, {})
    if not user_data_entry.get('modo_ubicacion_exacta', False):
        logger.warning(f"⚠️ Usuario {user_id} no está en modo_ubicacion_exacta, ignorando")
        return

    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            from app.models.user import User
            from app.extensions import db
            from datetime import datetime
            from app.routes.telegram_routes import get_telegram_app

            reporte_id = user_data_entry.get('reporte_id')
            cuadrilla_nombre = user_data_entry.get('cuadrilla_nombre', 'Cuadrilla desconocida')

            if not reporte_id:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ No se encontró el reporte asociado."
                )
                limpiar_estado(user_id)
                return

            # 1. Obtener reporte
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Reporte no encontrado."
                )
                limpiar_estado(user_id)
                return

            # 2. Actualizar coordenadas
            reporte.latitud = location.latitude
            reporte.longitud = location.longitude

            # 3. Cambiar estado a "En proceso" (ID: 3)
            status_en_proceso = Status.query.get(3)
            if not status_en_proceso:
                status_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
                if not status_en_proceso:
                    status_en_proceso = Status(descripcion="En proceso", color="warning")
                    db.session.add(status_en_proceso)
                    db.session.commit()

            # 4. Actualizar asignación
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            if asignacion:
                asignacion.status_id = status_en_proceso.id
                asignacion.observaciones = f"Ubicación exacta recibida del reportante el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                db.session.commit()
                logger.info(f"✅ Estado actualizado a 'En proceso' para reporte #{reporte_id}")

            # 5. Limpiar user_data del usuario
            user_data[user_id].pop('modo_ubicacion_exacta', None)
            user_data[user_id].pop('reporte_id', None)
            user_data[user_id].pop('cuadrilla_nombre', None)

            # 6. Confirmar al reportante (usar context.bot SIEMPRE)
            mensaje_confirmacion = (
                f"✅ *Ubicación recibida*\n\n"
                f"La cuadrilla *{cuadrilla_nombre}* ha sido notificada con tu ubicación exacta.\n\n"
                f"📍 Coordenadas:\n"
                f"Latitud: {location.latitude}\n"
                f"Longitud: {location.longitude}\n\n"
                f"Gracias por tu colaboración."
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=mensaje_confirmacion,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )

            # 7. Notificar a la cuadrilla asignada
            if asignacion and asignacion.team_id:
                usuarios_cuadrilla = User.query.filter_by(
                    team_id=asignacion.team_id,
                    is_active=True
                ).all()

                calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
                localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'

                mensaje_cuadrilla = (
                    f"📍 *UBICACIÓN EXACTA RECIBIDA - Reporte #{reporte.id}*\n\n"
                    f"El reportante ha compartido su ubicación exacta.\n\n"
                    f"📋 *Detalles:*\n"
                    f"• Reportante: {reporte.reportante}\n"
                    f"• Teléfono: {reporte.telefono}\n"
                    f"• Dirección original: {calle_nombre} #{reporte.numero}, {localidad_nombre}\n\n"
                    f"📍 *Coordenadas:*\n"
                    f"Latitud: {location.latitude}\n"
                    f"Longitud: {location.longitude}\n\n"
                    f"🔗 *Ver en Google Maps:*\n"
                    f"https://www.google.com/maps?q={location.latitude},{location.longitude}\n\n"
                    f"✅ Ahora pueden dirigirse a la ubicación exacta."
                )

                for usuario in usuarios_cuadrilla:
                    if usuario.telegram_id:
                        try:
                            await context.bot.send_message(
                                chat_id=int(usuario.telegram_id),
                                text=mensaje_cuadrilla,
                                parse_mode=ParseMode.MARKDOWN
                            )
                            logger.info(f"✅ Notificación enviada a {usuario.nombre} (cuadrilla)")
                        except Exception as e:
                            logger.error(f"❌ Error notificando a {usuario.nombre}: {e}")

            # 8. Notificar al responsable (Jefe Técnico para agua, Director para otros)
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
                    mensaje_responsable = (
                        f"📍 *UBICACIÓN RECIBIDA - Reporte #{reporte.id}*\n\n"
                        f"El reportante ha compartido su ubicación exacta.\n\n"
                        f"• Cuadrilla: {cuadrilla_nombre}\n"
                        f"• Coordenadas: {location.latitude}, {location.longitude}\n\n"
                        f"✅ El reporte está ahora en estado 'En proceso'."
                    )
                    await context.bot.send_message(
                        chat_id=int(responsable.telegram_id),
                        text=mensaje_responsable,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    logger.info(f"✅ Notificación enviada a {responsable.nombre}")
            except Exception as e:
                logger.error(f"❌ Error notificando responsable: {e}")

            logger.info(f"✅ Flujo de ubicación completado para reporte #{reporte_id}")

    except Exception as e:
        logger.error(f"❌ Error en manejar_ubicacion_problema_gps: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ocurrió un error al procesar tu ubicación. Intenta de nuevo.",
                reply_markup=ReplyKeyboardRemove()
            )
        except:
            pass
        limpiar_estado(user_id)
