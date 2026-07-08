from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
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
            "Operación cancelada. Usa /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if texto_original in ["📍 Compartir ubicación GPS", "📍", "GPS"] or "gps" in texto_original.lower():
        keyboard = [[KeyboardButton("📍 Compartir mi ubicación", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "📍 *Comparte tu ubicación GPS:*\n\n"
            "Toca el botón azul '📍 Compartir mi ubicación' de abajo.",
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
    print("🚨🚨🚨 UBICACION_GPS_HANDLER EJECUTADO 🚨🚨🚨")
    try:
        user_id = update.effective_user.id
        location = update.message.location
        print(f"📍 Lat: {location.latitude}, Lon: {location.longitude}")
        
        user_data[user_id]["latitud"] = location.latitude
        user_data[user_id]["longitud"] = location.longitude
        
        from app.services.geocoding import obtener_direccion_osm, buscar_localidad_flexible, buscar_calle_flexible
        
        direccion = obtener_direccion_osm(location.latitude, location.longitude)
        
        if direccion and direccion.get('road') and direccion.get('localidad'):
            localidad_detectada = direccion['localidad']
            calle_detectada = direccion['road']
        else:
            localidad_detectada = "Ixtlahuacán De Los Membrillos"
            calle_detectada = "Calle Principal"
        
        resultado_localidad = buscar_localidad_flexible(localidad_detectada)
        if resultado_localidad:
            loc_id, loc_nombre = resultado_localidad
            user_data[user_id]["localidad_id"] = loc_id
            user_data[user_id]["localidad_nombre"] = loc_nombre
            
            resultado_calle = buscar_calle_flexible(calle_detectada, loc_id)
            if resultado_calle:
                calle_id, calle_nombre = resultado_calle
                user_data[user_id]["calle_id"] = calle_id
                user_data[user_id]["calle_nombre"] = calle_nombre
                await update.message.reply_text(
                    f"✅ *Ubicación confirmada*\n\n"
                    f"📍 *Localidad:* {loc_nombre}\n"
                    f"🛣️ *Calle:* {calle_nombre}\n\n"
                    "📝 **Escribe el número exterior o referencia:**\n"
                    "(Ej: 123, Casa azul, S/N)",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                return NUMERO
            else:
                await update.message.reply_text(
                    f"⚠️ No encontré la calle '{calle_detectada}'.\n\n"
                    "Por favor, escribe la *calle* manualmente:",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                return CALLE
        else:
            await update.message.reply_text(
                f"⚠️ No encontré la localidad '{localidad_detectada}'.\n\n"
                "Por favor, escribe la *localidad/colonia* manualmente:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return LOCALIDAD
            
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
    
    if entrada.lower() == "cancelar":
        await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    candidatos = obtener_localidades_con_fallback()
    if not candidatos:
        await update.message.reply_text(
            "⚠️ No hay localidades registradas en el sistema.\n"
            "Por favor, contacta al administrador.",
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
        keyboard.append(["❌ Cancelar"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        mensaje = "🔍 Encontré varias localidades similares:\n\n"
        for i, sug in enumerate(sugerencias[:5], 1):
            mensaje += f"{i}. {sug['nombre']}\n"
        mensaje += "\nSelecciona una opción:"
        
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
        return LOCALIDAD_SUGERENCIAS
    else:
        await update.message.reply_text("❌ No encontré coincidencias. Intenta de nuevo:")
        return LOCALIDAD

async def localidad_sugerencias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar" or "cancelar" in texto.lower():
        await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if "escribir" in texto.lower():
        await update.message.reply_text("📍 Escribe la *localidad/colonia*:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
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
                f"✅ Localidad: {localidad['nombre']}\n\n"
                "Ahora escribe la *calle* (o las primeras letras).",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return CALLE
    
    await update.message.reply_text("No pude identificar la localidad. Intenta de nuevo:")
    return LOCALIDAD_SUGERENCIAS

async def calle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text.strip()
    
    if entrada.lower() == "cancelar":
        await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    loc_id = user_data[user_id].get("localidad_id")
    if not loc_id:
        await update.message.reply_text("Primero selecciona una localidad.")
        return LOCALIDAD
    
    candidatos = obtener_calles_con_fallback(loc_id)
    if not candidatos:
        await update.message.reply_text(
            f"⚠️ No hay calles registradas para esta localidad.\n"
            "Por favor, escribe el nombre de la calle manualmente:",
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
        keyboard.append(["❌ Cancelar"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        mensaje = "🔍 Encontré varias calles similares:\n\n"
        for i, sug in enumerate(sugerencias[:5], 1):
            mensaje += f"{i}. {sug['nombre']}\n"
        mensaje += "\nSelecciona una opción:"
        
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
        return CALLE_SUGERENCIAS
    else:
        await update.message.reply_text("❌ No encontré coincidencias. Intenta de nuevo:")
        return CALLE

async def calle_sugerencias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar" or "cancelar" in texto.lower():
        await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if "escribir" in texto.lower():
        await update.message.reply_text("Escribe la *calle*:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
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
                f"✅ Calle: {calle['nombre']}\n\n"
                "Escribe el *número exterior* (o 'S/N'):",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return NUMERO
    
    await update.message.reply_text("No pude identificar la calle. Intenta de nuevo:")
    return CALLE_SUGERENCIAS
