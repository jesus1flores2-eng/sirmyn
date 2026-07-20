from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, actualizar_timestamp_usuario, extraer_numero_opcion, limpiar_estado
from app.telegram.common.keyboards import crear_teclado_subtipos
from app.telegram.dicts import *
import logging

logger = logging.getLogger(__name__)


async def cuenta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    respuesta = update.message.text.strip()
    respuesta_lower = respuesta.lower()

    if respuesta_lower in ["no", "n", "no tengo", "no sé", "ninguna", "❌ no tengo cuenta"]:
        user_data[user_id]["cuenta"] = None
        
    elif respuesta_lower in ["sí", "si", "s", "yes", "y", "tengo", "claro", "por supuesto", "✅ sí, tengo cuenta"]:
        await update.message.reply_text(
            "Por favor, escribe tu *número de cuenta*:\n(Si no la recuerdas, escribe 'no')",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return CUENTA
    else:
        numero_limpio = respuesta.replace(" ", "").replace("-", "").replace(".", "")
        if numero_limpio.isdigit() and 3 <= len(numero_limpio) <= 20:
            user_data[user_id]["cuenta"] = numero_limpio
        else:
            await update.message.reply_text(
                "❌ Eso no parece un número de cuenta válido.\n\n"
                "Por favor, escribe:\n• Tu *número de cuenta* (solo números)\n• O *'no'* si no tienes cuenta",
                parse_mode="Markdown"
            )
            return CUENTA

    tipo_key = user_data[user_id].get("tipo_key", "1")
    if tipo_key == "1":
        keyboard = crear_teclado_subtipos(SUBTIPOS_AGUA)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Selecciona el tipo de problema de agua potable:", reply_markup=reply_markup)
        return SUBTIPO_AGUA
    elif tipo_key == "2":
        keyboard = crear_teclado_subtipos(SUBTIPOS_DRENAJE)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Selecciona el tipo de problema de drenaje:", reply_markup=reply_markup)
        return SUBTIPO_DRENAJE


async def subtipo_agua_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.telegram.handlers.subtipo import manejar_subtipo_generico
    return await manejar_subtipo_generico(update, context, SUBTIPOS_AGUA, "agua potable")


async def subtipo_drenaje_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.telegram.handlers.subtipo import manejar_subtipo_generico
    return await manejar_subtipo_generico(update, context, SUBTIPOS_DRENAJE, "drenaje")
