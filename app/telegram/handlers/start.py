from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
from app.telegram.emergencias.handlers import emergencia_start
import logging, time, asyncio

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔴🔴🔴 START EJECUTADO 🔴🔴🔴")
    user = update.effective_user
    user_id = user.id
    municipio_id_guardado = user_data.get(user_id, {}).get('municipio_id', 1)
    nombre_telegram = user.first_name or user.username or "Usuario"
    limpiar_estado(user_id)

    user_data[user_id] = {
        "nombre_telegram": nombre_telegram,
        "user_id": user_id,
        "telegram_username": user.username,
        "municipio_id": municipio_id_guardado,
        "_timestamp": time.time()
    }

    from app.models.municipio_config import MunicipioConfig

    municipio_id = user_data[user_id].get('municipio_id', 1)
    municipio = MunicipioConfig.query.get(municipio_id)
    nombre_municipio = municipio.nombre if municipio else "Ixtlahuacán"

    mensaje = (
        "🏛️ *Sistema Integral de Reportes Municipales y Notificaciones*\n"
        "*SIRMYN*\n\n"
        f"🏘️ *Municipio:* {nombre_municipio}\n\n"
        f"👋 *¡Bienvenido, {nombre_telegram}!*\n\n"
        "Este sistema te permite generar reportes ciudadanos y recibir "
        "información oficial del Ayuntamiento.\n\n"
        "📌 *Aviso importante:*\n"
        "• Al generar un reporte recibirás notificaciones institucionales.\n"
        "• Tus datos se usan únicamente para atender tu reporte.\n"
        "• La ubicación y evidencia ayudan a canalizarlo correctamente.\n\n"
        "🔐 Aviso de privacidad:\n"
        "👉 https://municipio.gob.mx/aviso-de-privacidad/\n\n"
        "*¿Aceptas continuar?*"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceptar", callback_data="aceptar_privacidad"),
         InlineKeyboardButton("❌ No aceptar", callback_data="rechazar_privacidad")]
    ])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=mensaje,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return ESPERAR_ACEPTACION


async def manejar_aceptacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔵 MANEJAR_ACEPTACION EJECUTADO")
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "rechazar_privacidad":
        await query.edit_message_text(
            "❌ *Lamentamos no poder ayudarle*\n\n"
            "Para usar el sistema SIRMYN es necesario aceptar "
            "el aviso de privacidad y términos de uso.\n\n"
            "Si cambia de opinión, use /start nuevamente.",
            parse_mode="Markdown"
        )
        limpiar_estado(user_id)
        return ConversationHandler.END

    nombre_capturado = user_data[user_id].get("nombre_telegram", "Usuario")
    user_data[user_id]["nombre"] = nombre_capturado

    await query.edit_message_text(
        f"✅ *Aceptación registrada*\n\n"
        f"*Bienvenido, {nombre_capturado}* al sistema de reportes municipal.",
        parse_mode="Markdown"
    )
    await asyncio.sleep(1)

    keyboard = [
        ["📋 REPORTE NORMAL", "🚨 EMERGENCIA"],
        ["📊 CONSULTAR REPORTE"],
        ["❌ CANCELAR"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    mensaje_menu = (
        f"🤖 *Estimado - {nombre_capturado}*\n\n"
        f"*Seleccione una opción:*\n\n"
        f"• 📋 REPORTE NORMAL: Servicios municipales (agua, drenaje, etc.)\n"
        f"• 🚨 EMERGENCIA: Atención inmediata (policía, bomberos, etc.)\n"
        f"• 📊 CONSULTAR REPORTE: Ver estatus de reporte existente\n"
        f"• ❌ CANCELAR: Salir del sistema"
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=mensaje_menu,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return MENU_PRINCIPAL


async def menu_principal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🟢 MENU_PRINCIPAL_HANDLER EJECUTADO")
    user_id = update.effective_user.id
    opcion = update.message.text.strip()
    print(f"   📱 Opción recibida: '{opcion}'")
    print(f"   📱 ¿Es REPORTE NORMAL? {opcion == '📋 REPORTE NORMAL'}")

    if opcion == "📋 Nuevo reporte":
        # Redirigir a REPORTE NORMAL
        nombre = user_data[user_id].get("nombre_telegram", "Usuario")
        user_data[user_id]["nombre"] = nombre

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

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "📋 Selecciona el tipo de reporte:",
            reply_markup=reply_markup
        )
        return MENU_PRINCIPAL

    elif opcion == "📊 Consultar estado":
        # Redirigir a /estado
        from app.telegram.commands.estado import estado_command
        await estado_command(update, context)
        return MENU_PRINCIPAL

    elif opcion == "❌ CANCELAR":
        await update.message.reply_text(
            "Operación cancelada. Use /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END

    elif opcion == "📋 REPORTE NORMAL":
        print("🔴 REPORTE NORMAL PRESIONADO")
        print(f"   user_id: {user_id}")
        print(f"   user_data: {user_data.get(user_id, {})}")
        # Inicializar user_data correctamente como lo hace emergencia
        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id]['municipio_id'] = user_data[user_id].get('municipio_id', 1)
        user_data[user_id]['nombre_telegram'] = user_data[user_id].get('nombre_telegram', update.effective_user.first_name or 'Usuario')
        user_data[user_id]['nombre'] = user_data[user_id].get('nombre_telegram', 'Usuario')
        
        nombre = user_data[user_id].get("nombre_telegram", "Usuario")

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
            f"✅ *{nombre}*, selecciona la dependencia municipal para tu reporte:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return TIPO

    elif opcion == "🚨 EMERGENCIA":
        return await emergencia_start(update, context)

    elif opcion == "📊 CONSULTAR REPORTE":
        await update.message.reply_text(
            "📋 Ingresa el *folio de tu reporte* tal como aparece en tu confirmación.\n"
            "Ejemplo: *ALUM-0006*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONSULTA_ID

    elif opcion == "↩️ VOLVER AL MENÚ":
        nombre = user_data[user_id].get("nombre_telegram", "Usuario")
        keyboard = [
            ["📋 REPORTE NORMAL", "🚨 EMERGENCIA"],
            ["📊 CONSULTAR REPORTE"],
            ["❌ CANCELAR"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            f"🤖 *BOT SIRMYN - {nombre}*\n\n"
            f"¿Qué tipo de servicio necesita?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return MENU_PRINCIPAL

    else:
        await update.message.reply_text(
            "❌ Opción no reconocida. Usa /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
