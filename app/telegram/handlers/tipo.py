from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.telegram.states import *
from app.telegram.utils import user_data, actualizar_timestamp_usuario, extraer_numero_opcion, limpiar_estado
from app.telegram.keyboards import crear_teclado_subtipos
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
        
        if numero in ["1", "2"]:
            keyboard = [["✅ Sí, tengo cuenta", "❌ No tengo cuenta"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                f"🔍 Para reportes de *{TIPOS_DEPENDENCIAS[numero]}*, necesitamos saber:\n\n"
                f"¿Tienes número de cuenta de agua?",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return CUENTA
        else:
            if numero == "9":
                keyboard = crear_teclado_subtipos(SUBTIPOS_BOMBEROS)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("🚒 Selecciona el tipo de emergencia o servicio:", reply_markup=reply_markup)
                return SUBTIPO_BOMBEROS
            elif numero == "3":
                keyboard = crear_teclado_subtipos(SUBTIPOS_ASEO_PUBLICO)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Selecciona el tipo de problema de aseo público:", reply_markup=reply_markup)
                return SUBTIPO_ASEO_PUBLICO
            elif numero == "4":
                keyboard = crear_teclado_subtipos(SUBTIPOS_ALUMBRADO_PUBLICO)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Selecciona el tipo de problema de alumbrado:", reply_markup=reply_markup)
                return SUBTIPO_ALUMBRADO_PUBLICO
            elif numero == "5":
                keyboard = crear_teclado_subtipos(SUBTIPOS_PARQUES_JARDINES)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Selecciona el tipo de problema de parques/jardines:", reply_markup=reply_markup)
                return SUBTIPO_PARQUES_JARDINES
            elif numero == "6":
                keyboard = crear_teclado_subtipos(SUBTIPOS_ECOLOGIA)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Selecciona el tipo de problema ambiental:", reply_markup=reply_markup)
                return SUBTIPO_ECOLOGIA
            elif numero == "7":
                keyboard = crear_teclado_subtipos(SUBTIPOS_SEGURIDAD_PUBLICA)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Selecciona el tipo de problema de seguridad:", reply_markup=reply_markup)
                return SUBTIPO_SEGURIDAD_PUBLICA
            elif numero == "8":
                keyboard = crear_teclado_subtipos(SUBTIPOS_OBRAS_PUBLICAS)
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Selecciona el tipo de problema de obra pública:", reply_markup=reply_markup)
                return SUBTIPO_OBRA_PUBLICA
    elif numero == "9" or "checar" in opcion or "reporte" in opcion:
        await update.message.reply_text("Ingresa el número de reporte:", reply_markup=ReplyKeyboardRemove())
        return CONSULTA_ID
    else:
        keyboard = [
            ["1️⃣ Agua potable", "2️⃣ Drenaje"],
            ["3️⃣ Aseo público", "4️⃣ Alumbrado público"],
            ["5️⃣ Parques y jardins", "6️⃣ Ecología"],
            ["7️⃣ Seguridad pública", "8️⃣ Obra pública"],
            ["9️⃣ Bomberos", "🔟 Checar un reporte"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Selecciona la *dependencia municipal* para tu reporte:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return TIPO

async def cuenta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    respuesta = update.message.text.strip()
    respuesta_lower = respuesta.lower()
    
    if respuesta_lower in ["no", "n", "no tengo", "no sé", "ninguna", "❌ no tengo cuenta"]:
        user_data[user_id]["cuenta"] = None
    elif respuesta_lower in ["sí", "si", "s", "yes", "y", "tengo", "claro", "por supuesto", "✅ sí, tengo cuenta"]:
        await update.message.reply_text(
            "Por favor, escribe tu *número de cuenta*:\n(Si no la recuerdas, escribe 'no')",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return CUENTA
    else:
        numero_limpio = respuesta.replace(" ", "").replace("-", "").replace(".", "")
        if numero_limpio.isdigit():
            if 3 <= len(numero_limpio) <= 20:
                user_data[user_id]["cuenta"] = numero_limpio
            else:
                await update.message.reply_text(
                    f"❌ El número debe tener entre 3 y 20 dígitos. Tienes {len(numero_limpio)} dígitos.\n\n"
                    "Por favor, escribe tu *número de cuenta* o 'no' si no tienes:",
                    parse_mode="Markdown"
                )
                return CUENTA
        else:
            await update.message.reply_text(
                "❌ Eso no parece un número de cuenta válido.\n\n"
                "Por favor, escribe:\n• Tu *número de cuenta* (solo números)\n• O *'no'* si no tienes cuenta",
                parse_mode="Markdown"
            )
            return CUENTA
    
    tipo_key = user_data[user_id].get("tipo_key", "1")
    if tipo_key == "1":
        keyboard = crear_teclado_subtipos(SUBTIPOS_AGUA)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Selecciona el tipo de problema de agua potable:", reply_markup=reply_markup)
        return SUBTIPO_AGUA
    elif tipo_key == "2":
        keyboard = crear_teclado_subtipos(SUBTIPOS_DRENAJE)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Selecciona el tipo de problema de drenaje:", reply_markup=reply_markup)
        return SUBTIPO_DRENAJE
