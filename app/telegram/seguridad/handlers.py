from telegram import Update
from telegram.ext import ContextTypes
from app.telegram.dicts import SUBTIPOS_SEGURIDAD_PUBLICA
import logging

logger = logging.getLogger(__name__)

async def subtipo_seguridad_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.telegram.handlers.subtipo import manejar_subtipo_generico
    return await manejar_subtipo_generico(update, context, SUBTIPOS_SEGURIDAD_PUBLICA, "seguridad pública")
