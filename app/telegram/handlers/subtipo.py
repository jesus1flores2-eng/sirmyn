from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, actualizar_timestamp_usuario, extraer_numero_opcion
from app.telegram.common.keyboards import crear_teclado_subtipos
from app.telegram.dicts import *
import logging

logger = logging.getLogger(__name__)


async def manejar_subtipo_generico(update: Update, context: ContextTypes.DEFAULT_TYPE, subtipos_dict: dict, tipo_nombre: str):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    texto = update.message.text
    numero = extraer_numero_opcion(texto)

    if numero and numero in subtipos_dict:
        user_data[user_id]["subtipo"] = subtipos_dict[numero]
        keyboard = [["📍 Compartir ubicación GPS", "🏠 Escribir dirección manualmente"], ["❌ Cancelar"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"✅ {tipo_nombre.capitalize()}: {subtipos_dict[numero]}\n\n📍 *¿Cómo quieres proporcionar la ubicación?*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ELEGIR_UBICACION

    texto_limpio = texto.lower()
    for key, value in subtipos_dict.items():
        if texto_limpio in value.lower() or key in texto_limpio:
            user_data[user_id]["subtipo"] = value
            keyboard = [["📍 Compartir ubicación GPS", "🏠 Escribir dirección manualmente"], ["❌ Cancelar"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                f"✅ {tipo_nombre.capitalize()}: {value}\n\n📍 *¿Cómo quieres proporcionar la ubicación?*",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return ELEGIR_UBICACION

    opciones_texto = "\n".join([f"{k}. {v}" for k, v in subtipos_dict.items()])
    await update.message.reply_text(
        f"❌ Subtipo no reconocido.\n\nOpciones:\n{opciones_texto}",
        parse_mode="Markdown"
    )
    return ELEGIR_UBICACION
