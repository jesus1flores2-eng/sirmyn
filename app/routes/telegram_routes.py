from flask import Blueprint, request, jsonify
from telegram import Update
import logging
from app.telegram.bot import build_telegram_app
from app.services.db_manager import DatabaseManager
import asyncio

telegram_bp = Blueprint('telegram', __name__)
logger = logging.getLogger(__name__)

_telegram_app = None
_telegram_app_initialized = False
_bot_loop = None  # Loop único para todo el bot

def get_telegram_app():
    global _telegram_app, _telegram_app_initialized, _bot_loop
    if _telegram_app is None:
        app = DatabaseManager.get_app()
        token = app.config.get('TELEGRAM_TOKEN')
        if not token:
            raise ValueError("TELEGRAM_TOKEN no configurado")
        _telegram_app = build_telegram_app(token)
    
    if not _telegram_app_initialized:
        # Si no hay loop o está cerrado, creamos uno nuevo
        if _bot_loop is None or _bot_loop.is_closed():
            _bot_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_bot_loop)
        _bot_loop.run_until_complete(_telegram_app.initialize())
        _telegram_app_initialized = True
        logger.info("✅ Aplicación de Telegram inicializada correctamente")
    
    return _telegram_app

@telegram_bp.route('/webhook', methods=['POST'])
def webhook():
    try:
        update_data = request.get_json(force=True)
        if not update_data:
            return jsonify({"status": "error", "message": "No data"}), 400

        logger.info(f"📨 Webhook recibido: {update_data.get('update_id')}")

        bot_app = get_telegram_app()
        update = Update.de_json(update_data, bot_app.bot)

        # Usar el loop persistente para procesar
        global _bot_loop
        if _bot_loop is None or _bot_loop.is_closed():
            _bot_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_bot_loop)
        _bot_loop.run_until_complete(bot_app.process_update(update))

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@telegram_bp.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "telegram"}), 200
