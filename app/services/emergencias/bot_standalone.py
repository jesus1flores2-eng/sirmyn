"""
Bot de Emergencias Standalone - Sin dependencias circulares
"""
import logging
from telegram.ext import Application, CommandHandler
from .handlers.inicio import conv_handler_emergencias

logger = logging.getLogger(__name__)

def create_emergencias_bot(token):
    """
    Crea y configura el bot de emergencias standalone
    """
    # Crear aplicación
    app = Application.builder().token(token).build()
    
    # Configurar handlers
    setup_handlers(app)
    
    return app

def setup_handlers(app):
    """Configura todos los handlers del bot de emergencias"""
    # Conversation handler principal
    app.add_handler(conv_handler_emergencias)
    
    # Comandos directos
    async def ayuda_command(update, context):
        await update.message.reply_text(
            "🚨 *BOT DE EMERGENCIAS SIRMYN*\n\n"
            "Este es el sistema de emergencias independiente.\n\n"
            "📋 *Comandos:*\n"
            "/start - Reportar emergencia\n"
            "/ayuda - Mostrar esta ayuda\n"
            "/cancelar - Cancelar operación\n\n"
            "📞 *Emergencias reales:* Llame al 911",
            parse_mode="Markdown"
        )
    
    app.add_handler(CommandHandler("ayuda", ayuda_command))
    app.add_handler(CommandHandler("help", ayuda_command))
    
    logger.info("✅ Handlers de emergencias configurados")
    return app