from telegram import Update
from telegram.ext import ContextTypes
from app.telegram.dicts import SUBTIPOS_PARQUES_JARDINES
import logging

logger = logging.getLogger(__name__)

async def subtipo_parques_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.telegram.handlers.subtipo import manejar_subtipo_generico
    return await manejar_subtipo_generico(update, context, SUBTIPOS_PARQUES_JARDINES, "parques y jardines")
