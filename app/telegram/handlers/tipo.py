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
        from app.models.municipio_config import MunicipioConfig

        municipio_id = user_data[user_id].get('municipio_id', 1)
        municipio = MunicipioConfig.query.get(municipio_id)

        tipo_elegido = TIPOS_DEPENDENCIAS[numero]

        if municipio:
            departamentos_activos = municipio.get_departamentos_lista()
            mapeo_nombre_area = {
                'Agua potable': 'agua',
                'Drenaje': 'drenaje',
                'Aseo público': 'aseo',
                'Alumbrado público': 'alumbrado',
                'Parques y jardines': 'parques',
                'Ecología': 'ecologia',
                'Obras públicas': 'obras'
            }
            area = mapeo_nombre_area.get(tipo_elegido)

            if area not in departamentos_activos:
                await update.message.reply_text(
                    f"❌ El departamento *{tipo_elegido}* no está disponible en este municipio.",
                    parse_mode="Markdown"
                )
                return TIPO

        user_data[user_id]["tipo"] = tipo_elegido
        user_data[user_id]["tipo_key"] = numero

        # Agua potable (1) y Drenaje (2) → preguntar cuenta
        if numero in ["1", "2"]:
            from app.telegram.agua.handlers import cuenta_handler
            keyboard = [["✅ Sí, tengo cuenta", "❌ No tengo cuenta"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                f"🔍 Para reportes de *{tipo_elegido}*, necesitamos saber:\n\n"
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

        # Obras públicas (7)
        elif numero == "7":
            keyboard = crear_teclado_subtipos(SUBTIPOS_OBRAS_PUBLICAS)
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Selecciona el tipo de problema de obra pública:", reply_markup=reply_markup)
            return SUBTIPO_OBRA_PUBLICA

        else:
            await update.message.reply_text(
                f"🚧 El servicio *{tipo_elegido}* está en mantenimiento.\n"
                f"Usa /start para elegir otra opción.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return MENU_PRINCIPAL

    elif "checar" in opcion or "reporte" in opcion:
        await update.message.reply_text("Ingresa el número de reporte:", reply_markup=ReplyKeyboardRemove())
        return CONSULTA_ID

    else:
        from app.models.municipio_config import MunicipioConfig

        municipio_id = user_data[user_id].get('municipio_id', 1)
        municipio = MunicipioConfig.query.get(municipio_id)
        departamentos_activos = municipio.get_departamentos_lista() if municipio else []

        mapeo = {
            'agua': "1️⃣ Agua potable",
            'drenaje': "2️⃣ Drenaje",
            'aseo': "3️⃣ Aseo público",
            'alumbrado': "4️⃣ Alumbrado público",
            'parques': "5️⃣ Parques y jardines",
            'ecologia': "6️⃣ Ecología",
            'obras': "7️⃣ Obras públicas",
        }

        keyboard = []
        fila_actual = []

        for clave in departamentos_activos:
            if clave in mapeo:
                fila_actual.append(mapeo[clave])
                if len(fila_actual) == 2:
                    keyboard.append(fila_actual)
                    fila_actual = []

        if fila_actual:
            keyboard.append(fila_actual)

        keyboard.append(["8️⃣ Checar un reporte"])

        if not departamentos_activos:
            keyboard = [
                ["1️⃣ Agua potable", "2️⃣ Drenaje"],
                ["3️⃣ Aseo público", "4️⃣ Alumbrado público"],
                ["5️⃣ Parques y jardines", "6️⃣ Ecología"],
                ["7️⃣ Obras públicas", "8️⃣ Checar un reporte"]
            ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Selecciona la *dependencia municipal* para tu reporte:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return TIPO
