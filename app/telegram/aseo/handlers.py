# app/telegram/aseo/handlers.py
# Handlers específicos del departamento de Aseo Público

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, actualizar_timestamp_usuario
from app.telegram.common.keyboards import crear_teclado_subtipos
from app.telegram.dicts import SUBTIPOS_ASEO_PUBLICO
import logging

logger = logging.getLogger(__name__)


async def subtipo_aseo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de subtipo para Aseo Público"""
    from app.telegram.handlers.subtipo import manejar_subtipo_generico
    return await manejar_subtipo_generico(update, context, SUBTIPOS_ASEO_PUBLICO, "aseo público")
