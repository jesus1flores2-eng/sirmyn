from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.telegram.states import NOMBRE
from app.telegram.utils import user_data

async def nombre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "Por favor, escribe tu *nombre completo*:\n"
        "(Apellido paterno, Apellido materno y Nombre)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    user_data[user_id] = user_data.get(user_id, {})
    return NOMBRE
