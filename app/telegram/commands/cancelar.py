from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.telegram.common.utils import limpiar_estado

def cancelar_command(update, context):
    user_id = update.effective_user.id
    limpiar_estado(user_id)
    update.message.reply_text(
        "Operación cancelada. Usa /start para comenzar de nuevo.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END
