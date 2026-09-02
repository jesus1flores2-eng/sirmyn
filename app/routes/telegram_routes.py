from flask import Blueprint, request, jsonify
from telegram import Update
import logging
from app.telegram.bot import build_telegram_app
from app.services.db_manager import DatabaseManager
import asyncio
import os

telegram_bp = Blueprint('telegram', __name__)
logger = logging.getLogger(__name__)

_telegram_apps = {}
_initialized_apps = {}
_bot_loops = {}


def obtener_bots_desde_db():
    """Obtiene los bots desde municipios_config"""
    from app.models.municipio_config import MunicipioConfig
    import unicodedata

    bots = {}
    municipios = MunicipioConfig.query.filter(MunicipioConfig.bot_token.isnot(None)).all()

    for m in municipios:
        # Normalizar: quitar acentos para las claves
        clave = unicodedata.normalize('NFD', m.nombre.lower()).encode('ascii', 'ignore').decode('utf-8')
        clave = clave.replace(' ', '_')
        bots[clave] = {
            'token': m.bot_token,
            'municipio_id': m.id
        }

    return bots


def get_telegram_app(municipio_clave='ixtlahuacan'):
    global _telegram_apps, _initialized_apps, _bot_loops

    BOTS = obtener_bots_desde_db()

    if municipio_clave not in BOTS:
        if BOTS:
            municipio_clave = list(BOTS.keys())[0]
        else:
            raise ValueError("No hay bots configurados en la base de datos")

    token = BOTS[municipio_clave]['token']

    if not token:
        raise ValueError(f"Token no configurado para {municipio_clave}")

    if municipio_clave not in _telegram_apps:
        _telegram_apps[municipio_clave] = build_telegram_app(token)
        logger.info(f"✅ App de Telegram construida para {municipio_clave}")

    if municipio_clave not in _initialized_apps:
        if municipio_clave not in _bot_loops:
            _bot_loops[municipio_clave] = asyncio.new_event_loop()
            asyncio.set_event_loop(_bot_loops[municipio_clave])

        try:
            _bot_loops[municipio_clave].run_until_complete(
                _telegram_apps[municipio_clave].initialize()
            )
            _initialized_apps[municipio_clave] = True
            logger.info(f"✅ App de Telegram inicializada para {municipio_clave}")
        except Exception as e:
            logger.error(f"❌ Error inicializando Telegram para {municipio_clave}: {e}")
            raise

    return _telegram_apps[municipio_clave]


@telegram_bp.route('/webhook/<municipio_clave>', methods=['POST'])
def webhook_municipio(municipio_clave):
    try:
        update_data = request.get_json(force=True)
        if not update_data:
            return jsonify({"status": "error", "message": "No data"}), 400

        logger.info(f"📨 Webhook recibido para {municipio_clave}: {update_data.get('update_id')}")

        BOTS = obtener_bots_desde_db()

        if municipio_clave not in BOTS:
            return jsonify({"status": "error", "message": "Municipio no encontrado"}), 404

        bot_app = get_telegram_app(municipio_clave)
        update = Update.de_json(update_data, bot_app.bot)

        from app.telegram.common.utils import user_data
        user_id = update.effective_user.id if update.effective_user else None
        if user_id:
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['municipio_id'] = BOTS[municipio_clave]['municipio_id']

        loop = _bot_loops.get(municipio_clave)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            _bot_loops[municipio_clave] = loop
            asyncio.set_event_loop(loop)

        async def process_update():
            await bot_app.process_update(update)

        loop.run_until_complete(process_update())
        logger.info(f"📨 Update procesado para {municipio_clave}")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@telegram_bp.route('/webhook', methods=['POST'])
def webhook_default():
    return webhook_municipio('ixtlahuacan')


@telegram_bp.route('/health', methods=['GET'])
def health():
    try:
        BOTS = obtener_bots_desde_db()
        if BOTS:
            primera_clave = list(BOTS.keys())[0]
            bot_app = get_telegram_app(primera_clave)
            initialized = bot_app is not None
        else:
            initialized = False
    except Exception:
        initialized = False

    return jsonify({
        "status": "ok",
        "service": "telegram",
        "initialized": initialized
    }), 200
