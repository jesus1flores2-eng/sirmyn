from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, actualizar_timestamp_usuario, extraer_numero_opcion, limpiar_estado
from app.telegram.common.keyboards import crear_teclado_subtipos
from app.telegram.dicts import *
import logging

logger = logging.getLogger(__name__)


async def tipo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    opcion = update.message.text.lower()

    numero = extraer_numero_opcion(opcion)

    if numero and numero in TIPOS_DEPENDENCIAS:
        user_data[user_id]["tipo"] = TIPOS_DEPENDENCIAS[numero]
        user_data[user_id]["tipo_key"] = numero

        # Agua potable (1) y Drenaje (2) → preguntar cuenta
        if numero in ["1", "2"]:
            from app.telegram.agua.handlers import cuenta_handler
            keyboard = [["✅ Sí, tengo cuenta", "❌ No tengo cuenta"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                f"🔍 Para reportes de *{TIPOS_DEPENDENCIAS[numero]}*, necesitamos saber:\n\n"
                f"¿Tienes número de cuenta de agua?",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return CUENTA

        # Aseo público (3)
        elif numero == "3":
            keyboard = crear_teclado_subtipos(SUBTIPOS_ASEO_PUBLICO)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema de aseo público:", reply_markup=reply_markup)
            return SUBTIPO_ASEO_PUBLICO

        # Alumbrado público (4)
        elif numero == "4":
            keyboard = crear_teclado_subtipos(SUBTIPOS_ALUMBRADO_PUBLICO)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema de alumbrado público:", reply_markup=reply_markup)
            return SUBTIPO_ALUMBRADO_PUBLICO

        # Parques y jardines (5)
        elif numero == "5":
            keyboard = crear_teclado_subtipos(SUBTIPOS_PARQUES_JARDINES)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema de parques y jardines:", reply_markup=reply_markup)
            return SUBTIPO_PARQUES_JARDINES

        # Ecología (6)
        elif numero == "6":
            keyboard = crear_teclado_subtipos(SUBTIPOS_ECOLOGIA)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema ambiental:", reply_markup=reply_markup)
            return SUBTIPO_ECOLOGIA

        # Seguridad pública (7)
        elif numero == "7":
            keyboard = crear_teclado_subtipos(SUBTIPOS_SEGURIDAD_PUBLICA)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema de seguridad:", reply_markup=reply_markup)
            return SUBTIPO_SEGURIDAD_PUBLICA

        # Obras públicas (8)
        elif numero == "8":
            keyboard = crear_teclado_subtipos(SUBTIPOS_OBRAS_PUBLICAS)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema de obra pública:", reply_markup=reply_markup)
            return SUBTIPO_OBRA_PUBLICA

        # Bomberos (9)
        elif numero == "9":
            keyboard = crear_teclado_subtipos(SUBTIPOS_BOMBEROS)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("🚒 Selecciona el tipo de emergencia o servicio:", reply_markup=reply_markup)
            return SUBTIPO_BOMBEROS

        # No implementado
        else:
            await update.message.reply_text(
                f"🚧 El servicio *{TIPOS_DEPENDENCIAS[numero]}* está en mantenimiento.\n"
                f"Usa /start para elegir otra opción.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return MENU_PRINCIPAL

    elif "checar" in opcion or "reporte" in opcion:
        await update.message.reply_text("Ingresa el número de reporte:", reply_markup=ReplyKeyboardRemove())
        return CONSULTA_ID

    else:
        keyboard = [
            ["1️⃣ Agua potable", "2️⃣ Drenaje"],
            ["3️⃣ Aseo público", "4️⃣ Alumbrado público"],
            ["5️⃣ Parques y jardines", "6️⃣ Ecología"],
            ["7️⃣ Seguridad pública", "8️⃣ Obras públicas"],
            ["9️⃣ Bomberos", "🔟 Checar un reporte"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Selecciona la *dependencia municipal* para tu reporte:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return TIPO
