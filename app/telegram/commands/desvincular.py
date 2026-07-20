# app/telegram/commands/desvincular.py
from telegram import Update
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
import logging

logger = logging.getLogger(__name__)

async def desvincular_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desvincula el Telegram ID del usuario actual o de otro (admin)"""
    user_id = update.effective_user.id
    args = context.args
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            from app.extensions import db
            
            # Si es admin y proporciona un username
            if args:
                usuario_actual = User.query.filter_by(telegram_id=str(user_id)).first()
                if not usuario_actual or usuario_actual.role != 'admin':
                    await update.message.reply_text("❌ Solo un administrador puede desvincular a otros usuarios.")
                    return
                
                username = args[0]
                usuario = User.query.filter_by(username=username).first()
                if not usuario:
                    await update.message.reply_text(f"❌ Usuario '{username}' no encontrado.")
                    return
            else:
                # Desvincularse a sí mismo
                usuario = User.query.filter_by(telegram_id=str(user_id)).first()
                if not usuario:
                    await update.message.reply_text("❌ No tienes una cuenta vinculada.")
                    return
            
            if not usuario.telegram_id:
                await update.message.reply_text(f"ℹ️ {usuario.nombre} ya está desvinculado.")
                return
            
            nombre = usuario.nombre
            usuario.telegram_id = None
            db.session.commit()
            
            await update.message.reply_text(
                f"✅ *VINCULACIÓN ELIMINADA*\n\n"
                f"👤 *Usuario:* {nombre}\n"
                f"📱 *Telegram:* Desvinculado\n\n"
                f"📌 El usuario ya no recibirá notificaciones del bot.",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ {nombre} desvinculado")
            
    except Exception as e:
        logger.error(f"❌ Error en /desvincular: {e}")
        await update.message.reply_text("❌ Error al desvincular.")
