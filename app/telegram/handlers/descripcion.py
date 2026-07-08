from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.telegram.states import *
from app.telegram.utils import user_data, actualizar_timestamp_usuario
import logging

logger = logging.getLogger(__name__)

async def entre_calles_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    user_data[user_id]["entre_calles"] = update.message.text
    
    await update.message.reply_text(
        "Descríbeme un poco el problema:",
        reply_markup=ReplyKeyboardRemove()
    )
    return DESCRIPCION

async def descripcion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    user_data[user_id]["descripcion"] = update.message.text
    
    keyboard = [["📸 Subir foto/video", "➡️ Omitir evidencia"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📸 ¿Deseas subir una foto o video del problema?\n"
        "Puedes enviar la imagen/video directamente o presionar 'Omitir evidencia' para continuar.",
        reply_markup=reply_markup
    )
    return EVIDENCIA
