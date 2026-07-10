# app/telegram/callbacks/aceptacion.py
from telegram import Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

async def aceptar_privacidad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "aceptar_privacidad":
        await query.edit_message_text("✅ Privacidad aceptada. Puedes continuar.")
    else:
        await query.edit_message_text("❌ Privacidad rechazada. No puedes usar el bot.")
