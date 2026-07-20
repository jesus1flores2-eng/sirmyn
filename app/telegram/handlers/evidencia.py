from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
import logging
import os
import uuid

logger = logging.getLogger(__name__)


async def mostrar_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el resumen del reporte antes de confirmar"""
    user_id = update.effective_user.id
    datos = user_data[user_id]

    resumen = (
        f"📋 *Resumen del Reporte*\n\n"
        f"👤 *Nombre:* {datos.get('nombre', 'N/A')}\n"
        f"💧 *Tipo:* {datos.get('tipo', 'N/A')} - {datos.get('subtipo', '')}\n"
        f"📍 *Dirección:* {datos.get('calle_nombre', '')} #{datos.get('numero', '')}, "
        f"{datos.get('localidad_nombre', '')}\n"
        f"🚧 *Entre calles:* {datos.get('entre_calles', '')}\n"
        f"📝 *Descripción:* {datos.get('descripcion', '')}\n"
        f"💳 *Cuenta:* {datos.get('cuenta') or 'No proporcionada'}\n"
        f"📎 *Evidencia:* {'Sí' if datos.get('evidencia') else 'No'}"
    )

    keyboard = [["✅ Confirmar", "❌ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        resumen,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def evidencia_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la subida de evidencia (texto o multimedia)"""
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)

    if update.message and update.message.text:
        return await manejar_texto_evidencia(update, context, user_id)
    elif update.message and (update.message.photo or update.message.video):
        return await manejar_multimedia_evidencia(update, context, user_id)
    else:
        await update.message.reply_text("Por favor, envía una foto, video, o escribe 'omitir'.")
        return EVIDENCIA


async def manejar_texto_evidencia(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Maneja cuando el usuario escribe texto en el paso de evidencia"""
    texto = update.message.text.lower()

    if "omitir" in texto or "➡️" in texto:
        user_data[user_id]["evidencia"] = None
        await update.message.reply_text("✅ Continuando sin evidencia.")
        await mostrar_resumen(update, context)
        return CONFIRMACION
    elif "subir" in texto or "📸" in texto:
        await update.message.reply_text(
            "Por favor, envía la foto o video directamente.\n"
            "Máximo 20MB. Si no deseas adjuntar nada, escribe 'omitir'.",
            reply_markup=ReplyKeyboardRemove()
        )
        return EVIDENCIA
    else:
        await update.message.reply_text(
            "Por favor, selecciona una opción: Envía una foto/video o escribe 'omitir'."
        )
        return EVIDENCIA


async def manejar_multimedia_evidencia(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Maneja cuando el usuario envía una foto o video"""
    try:
        await update.message.reply_text(
            "📤 Guardando evidencia, por favor espere...",
            reply_markup=ReplyKeyboardRemove()
        )

        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            extension = "jpg"
            tipo = "foto"
        else:
            file = await update.message.video.get_file()
            extension = "mp4"
            tipo = "video"

        if file.file_size > 20 * 1024 * 1024:
            await update.message.reply_text(f"⚠️ El {tipo} es muy grande (máx 20MB).")
            return EVIDENCIA

        filename = f"tmp_{user_id}_{uuid.uuid4().hex}.{extension}"
        filepath = os.path.join("uploads", filename)
        os.makedirs("uploads", exist_ok=True)
        await file.download_to_drive(filepath)

        user_data[user_id]["evidencia"] = filename
        user_data[user_id]["evidencia_filename"] = filename

        await update.message.reply_text(f"✅ {tipo.capitalize()} recibida correctamente.")
        await mostrar_resumen(update, context)
        return CONFIRMACION

    except Exception as e:
        logger.error(f"Error al procesar evidencia: {e}")
        await update.message.reply_text(
            "❌ Error al procesar el archivo. Intenta con otro o escribe 'omitir'."
        )
        return EVIDENCIA
