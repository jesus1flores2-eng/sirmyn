"""
Maneja la encuesta de satisfacción (calificación, velocidad, comentario)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data
from app.services.db_manager import DatabaseManager
from app.models.feedback import EncuestaSatisfaccion
from app.extensions import db
import logging

logger = logging.getLogger(__name__)

async def encuesta_calificacion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la calificación de la encuesta (1-5)"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    user_id = query.from_user.id
    
    if not callback_data.startswith('enc_calif_'):
        return
    
    partes = callback_data.split('_')
    calificacion = int(partes[2])
    reporte_id = int(partes[3])
    
    if user_id not in user_data or not user_data[user_id].get('modo_encuesta'):
        await query.edit_message_text("❌ Sesión expirada.")
        return
    
    user_data[user_id]['calificacion'] = calificacion
    user_data[user_id]['paso_actual'] = 'velocidad'
    
    emojis = ['😠', '😟', '😐', '😊', '😍']
    emoji = emojis[calificacion - 1]
    
    keyboard = [
        [
            InlineKeyboardButton("1️⃣ 🐌", callback_data=f"enc_vel_1_{reporte_id}"),
            InlineKeyboardButton("2️⃣ ⏱️", callback_data=f"enc_vel_2_{reporte_id}"),
            InlineKeyboardButton("3️⃣ ⚡", callback_data=f"enc_vel_3_{reporte_id}"),
            InlineKeyboardButton("4️⃣ 🛩️", callback_data=f"enc_vel_4_{reporte_id}"),
            InlineKeyboardButton("5️⃣ 🚀", callback_data=f"enc_vel_5_{reporte_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"✅ Calificación: {emoji} ({calificacion}/5)\n\n⏱️ ¿Qué tan rápida fue la atención? (1-5):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def encuesta_velocidad_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la velocidad de atención (1-5)"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    user_id = query.from_user.id
    
    if not callback_data.startswith('enc_vel_'):
        return
    
    partes = callback_data.split('_')
    velocidad = int(partes[2])
    reporte_id = int(partes[3])
    
    if user_id not in user_data or not user_data[user_id].get('modo_encuesta'):
        await query.edit_message_text("❌ Sesión expirada.")
        return
    
    user_data[user_id]['velocidad'] = velocidad
    user_data[user_id]['paso_actual'] = 'comentario'
    
    await query.edit_message_text(
        text="✅ Velocidad registrada.\n\n💬 ¿Tienes algún comentario o sugerencia? (opcional, escribe 'omitir' para saltar):",
        parse_mode=ParseMode.MARKDOWN
    )
    # Ahora esperamos un mensaje de texto


async def encuesta_comentario_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comentario final de la encuesta"""
    user_id = update.effective_user.id
    
    if user_id not in user_data or not user_data[user_id].get('modo_encuesta'):
        await update.message.reply_text("❌ Sesión expirada.")
        return
    
    comentario = update.message.text.strip()
    if comentario.lower() == 'omitir':
        comentario = None
    
    app = DatabaseManager.get_app()
    with app.app_context():
        encuesta = EncuestaSatisfaccion(
            reporte_id=user_data[user_id]['reporte_id'],
            usuario_id=user_id,
            calificacion=user_data[user_id]['calificacion'],
            velocidad=user_data[user_id]['velocidad'],
            comentario=comentario
        )
        db.session.add(encuesta)
        db.session.commit()
        
        await update.message.reply_text(
            "📊 *¡Encuesta completada!*\n\nGracias por tu feedback. Tu opinión nos ayuda a mejorar.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"📊 Encuesta registrada para usuario {user_id}, reporte {user_data[user_id]['reporte_id']}")
    
    # Limpiar datos
    if user_id in user_data:
        user_data[user_id].pop('modo_encuesta', None)
        user_data[user_id].pop('calificacion', None)
        user_data[user_id].pop('velocidad', None)
        user_data[user_id].pop('paso_actual', None)
