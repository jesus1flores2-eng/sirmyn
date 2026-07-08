from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.telegram.states import *
from app.telegram.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
import logging, time, asyncio

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔴🔴🔴 START EJECUTADO 🔴🔴🔴")
    user = update.effective_user
    user_id = user.id
    limpiar_estado(user_id)
    nombre_telegram = user.first_name or user.username or "Usuario"
    
    user_data[user_id] = {
        "nombre_telegram": nombre_telegram,
        "user_id": user_id,
        "telegram_username": user.username,
        "_timestamp": time.time()
    }
    
    mensaje = (
        "🏛️ *Sistema Integral de Reportes Municipales y Notificaciones*\n"
        "*SIRMYN*\n\n"
        f"👋 *¡Bienvenido, {nombre_telegram}!*\n\n"
        "Este sistema te permite generar reportes ciudadanos y recibir "
        "información oficial del Ayuntamiento.\n\n"
        "📌 *Aviso importante:*\n"
        "• Al generar un reporte recibirás notificaciones institucionales.\n"
        "• Tus datos se usan únicamente para atender tu reporte.\n"
        "• La ubicación y evidencia ayudan a canalizarlo correctamente.\n\n"
        "🔐 Aviso de privacidad:\n"
        "👉 https://municipio.gob.mx/aviso-de-privacidad/\n\n"
        "*¿Aceptas continuar?*"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceptar", callback_data="aceptar_privacidad"),
         InlineKeyboardButton("❌ No aceptar", callback_data="rechazar_privacidad")]
    ])
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=mensaje,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return ESPERAR_ACEPTACION


async def manejar_aceptacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔵 MANEJAR_ACEPTACION EJECUTADO")
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data == "rechazar_privacidad":
        await query.edit_message_text(
            "❌ *Lamentamos no poder ayudarle*\n\n"
            "Para usar el sistema SIRMYN es necesario aceptar "
            "el aviso de privacidad y términos de uso.\n\n"
            "Si cambia de opinión, use /start nuevamente.",
            parse_mode="Markdown"
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    nombre_capturado = user_data[user_id].get("nombre_telegram", "Usuario")
    user_data[user_id]["nombre"] = nombre_capturado
    
    await query.edit_message_text(
        f"✅ *Aceptación registrada*\n\n"
        f"*Bienvenido, {nombre_capturado}* al sistema de reportes municipal.",
        parse_mode="Markdown"
    )
    await asyncio.sleep(1)
    
    keyboard = [
        ["📋 REPORTE NORMAL", "🚨 EMERGENCIA"],
        ["📊 CONSULTAR REPORTE"],
        ["❌ CANCELAR"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    mensaje_menu = (
        f"🤖 *Estimado - {nombre_capturado}*\n\n"
        f"*Seleccione una opción:*\n\n"
        f"• 📋 REPORTE NORMAL: Servicios municipales (agua, drenaje, etc.)\n"
        f"• 🚨 EMERGENCIA: Atención inmediata (policía, bomberos, etc.)\n"
        f"• 📊 CONSULTAR REPORTE: Ver estatus de reporte existente\n"
        f"• ❌ CANCELAR: Salir del sistema"
    )
    
    await context.bot.send_message(
        chat_id=user_id,
        text=mensaje_menu,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return MENU_PRINCIPAL

async def menu_principal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🟢 MENU_PRINCIPAL_HANDLER EJECUTADO")
    user_id = update.effective_user.id
    opcion = update.message.text.strip()
    
    if opcion == "❌ CANCELAR":
        await update.message.reply_text(
            "Operación cancelada. Use /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    elif opcion == "📋 REPORTE NORMAL":
        nombre = user_data[user_id].get("nombre_telegram", "Usuario")
        user_data[user_id]["nombre"] = nombre
        
        keyboard = [
            ["1️⃣ Agua potable", "2️⃣ Drenaje"],
            ["3️⃣ Aseo público", "4️⃣ Alumbrado público"],
            ["5️⃣ Parques y jardines", "6️⃣ Ecología"],
            ["7️⃣ Obra pública", "8️⃣ Checar un reporte"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            f"✅ *{nombre}*, selecciona la dependencia municipal para tu reporte:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return TIPO
    
    elif opcion == "🚨 EMERGENCIA":
        bot_username = "SIRMYNEmergenciasBot"
        enlace_directo = f"https://t.me/{bot_username}?start=redirigido"
        await update.message.reply_text(
            f"🚨 *EMERGENCIA REPORTADA*\n\n"
            f"Para atención inmediata:\n\n"
            f"🔗 [👉 PRESIONA AQUÍ para iniciar tu reporte de emergencia]({enlace_directo})",
            parse_mode="Markdown",
            disable_web_page_preview=False,
            reply_markup=ReplyKeyboardRemove()
        )
        keyboard = [["↩️ VOLVER AL MENÚ"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("¿Deseas volver al menú principal?", reply_markup=reply_markup)
        return MENU_PRINCIPAL
    
    elif opcion == "📊 CONSULTAR REPORTE":
        await update.message.reply_text(
            "Ingresa el número de folio de tu reporte:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONSULTA_ID
    
    elif opcion == "↩️ VOLVER AL MENÚ":
        nombre = user_data[user_id].get("nombre_telegram", "Usuario")
        keyboard = [
            ["📋 REPORTE NORMAL", "🚨 EMERGENCIA"],
            ["📊 CONSULTAR REPORTE"],
            ["❌ CANCELAR"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            f"🤖 *BOT SIRMYN - {nombre}*\n\n"
            f"¿Qué tipo de servicio necesita?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return MENU_PRINCIPAL
    
    else:
        await update.message.reply_text(
            "❌ Opción no reconocida. Usa /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
