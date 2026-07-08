import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

from app.services.emergencias.emergencias_database import guardar_emergencia_en_db
from app.services.emergencias.notificaciones_emergencias import notificar_emergencia_a_directores

logger = logging.getLogger(__name__)

# Estados de la conversación
SELECCIONAR_TIPO, ESPERAR_UBICACION, ESPERAR_DESCRIPCION = range(3)

async def start_emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de reporte de emergencia."""
    user = update.effective_user
    
    logger.info(f"🚨 Usuario {user.id} ({user.username}) inició reporte de emergencia")
    
    # Crear teclado con opciones de emergencia
    keyboard = [
        [KeyboardButton("👮 POLICÍA"), KeyboardButton("🚒 BOMBEROS")],
        [KeyboardButton("🚑 AMBULANCIA"), KeyboardButton("👩 PUNTO VIOLETA")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "🚨 *¿QUÉ TIPO DE EMERGENCIA ES?*\n\n"
        "Selecciona una opción:\n"
        "• 👮 POLICÍA: Asalto, violencia, robo\n"
        "• 🚒 BOMBEROS: Incendio, explosión\n"
        "• 🚑 AMBULANCIA: Accidente, heridos\n"
        "• 👩 PUNTO VIOLETA: Violencia de género\n\n"
        "_Responde con el texto o toca el botón_",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return SELECCIONAR_TIPO

async def recibir_tipo_emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el tipo de emergencia y solicita ubicación."""
    tipo_texto = update.message.text
    
    # Mapear texto a tipo interno
    if "👮" in tipo_texto or "POLICÍA" in tipo_texto.upper():
        tipo = "policia"
        tipo_display = "👮 POLICÍA"
    elif "🚒" in tipo_texto or "BOMBEROS" in tipo_texto.upper():
        tipo = "bomberos"
        tipo_display = "🚒 BOMBEROS"
    elif "🚑" in tipo_texto or "AMBULANCIA" in tipo_texto.upper():
        tipo = "ambulancia"
        tipo_display = "🚑 AMBULANCIA"
    elif "👩" in tipo_texto or "PUNTO VIOLETA" in tipo_texto.upper():
        tipo = "punto_violeta"
        tipo_display = "👩 PUNTO VIOLETA"
    else:
        # Por defecto
        tipo = "policia"
        tipo_display = "👮 POLICÍA"
    
    context.user_data['emergencia_tipo'] = tipo
    context.user_data['emergencia_tipo_display'] = tipo_display
    
    logger.info(f"📋 Usuario seleccionó tipo: {tipo}")
    
    # Solicitar ubicación con botón especial
    ubicacion_keyboard = [[KeyboardButton("📍 Compartir ubicación", request_location=True)]]
    ubicacion_markup = ReplyKeyboardMarkup(ubicacion_keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"📍 *COMPARTE TU UBICACIÓN EN TIEMPO REAL*\n\n"
        f"Toca el botón abajo para compartir tu ubicación actual.\n"
        f"_Esto ayuda a que la ayuda llegue más rápido._",
        reply_markup=ubicacion_markup,
        parse_mode='Markdown'
    )
    
    return ESPERAR_UBICACION

async def recibir_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la ubicación y solicita descripción breve."""
    location = update.message.location
    
    context.user_data['emergencia_latitud'] = location.latitude
    context.user_data['emergencia_longitud'] = location.longitude
    
    logger.info(f"📍 Ubicación recibida: {location.latitude}, {location.longitude}")
    
    await update.message.reply_text(
        "✅ *Ubicación recibida*\n\n"
        "⚠️ *ESCRIBE UNA DESCRIPCIÓN BREVE*\n"
        "Ejemplos:\n"
        "• 'Asalto a mano armada en esquina'\n"
        "• 'Incendio en casa de dos pisos'\n"
        "• 'Accidente automovilístico con heridos'\n"
        "• 'Hombre golpeando a mujer en calle...'\n\n"
        "_Sé breve pero claro. Máximo 2 líneas._",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    return ESPERAR_DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la descripción y guarda la emergencia."""
    descripcion = update.message.text
    context.user_data['emergencia_descripcion'] = descripcion
    
    user = update.effective_user
    
    logger.info(f"📝 Descripción recibida: {descripcion[:50]}...")
    
    # Construir datos para la base de datos
    datos_emergencia = {
        'tipo': context.user_data.get('emergencia_tipo', 'policia'),
        'subtipo': '',  # Podrías agregar más detalles si quieres
        'latitud': context.user_data.get('emergencia_latitud'),
        'longitud': context.user_data.get('emergencia_longitud'),
        'direccion_aproximada': 'Ubicación por GPS',  # Podrías geocodificar si quieres
        'reportante': f"{user.first_name} {user.last_name or ''}".strip(),
        'telegram_user_id': user.id,
        'telegram_username': user.username,
        'descripcion': descripcion,
        'nivel_urgencia': 1,
        'status': 'reportada',
        'plataforma': 'telegram',
        'localidad_id': 1,  # Ajusta según tu sistema
        'municipio_id': 1,
        'municipio_nombre': 'Nombre de tu Municipio'
    }
    
    # Obtener sesión de base de datos del contexto
    db_session = context.bot_data.get('db_session')
    
    if db_session is None:
        logger.error("❌ No hay sesión de base de datos en context.bot_data")
        await update.message.reply_text(
            "❌ Error del sistema. Por favor, contacta al 911 directamente.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Guardar en base de datos
    logger.info("💾 Guardando emergencia en base de datos...")
    resultado = await guardar_emergencia_en_db(datos_emergencia, db_session)
    
    if resultado['success']:
        # Notificar a directores
        logger.info("📤 Notificando a directores...")
        notificaciones = await notificar_emergencia_a_directores(
            bot=context.bot,
            db_session=db_session,
            report_id=resultado['report_id'],
            datos_emergencia=datos_emergencia
        )
        
        # Responder al usuario
        await update.message.reply_text(
            f"✅ *EMERGENCIA REPORTADA EXITOSAMENTE*\n\n"
            f"📋 *Folio:* `{resultado['folio_publico']}`\n"
            f"📍 *Tipo:* {context.user_data.get('emergencia_tipo_display', 'Emergencia')}\n"
            f"👮 *Notificado a:* {notificaciones} autoridad(es)\n\n"
            f"*La ayuda está en camino. Mantén tu teléfono cerca.*\n\n"
            f"_Si es seguro, espera a que llegue la unidad._",
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Emergencia procesada. Report ID: {resultado['report_id']}, Folio: {resultado['folio_publico']}, Notificaciones: {notificaciones}")
    else:
        logger.error(f"❌ Error guardando emergencia: {resultado.get('error')}")
        await update.message.reply_text(
            "❌ Error al registrar la emergencia. Intenta nuevamente o contacta al 911.",
            parse_mode='Markdown'
        )
    
    # Limpiar datos de la conversación
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancelar_emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela el reporte de emergencia."""
    user = update.effective_user
    logger.info(f"❌ Usuario {user.id} canceló reporte de emergencia")
    
    await update.message.reply_text(
        "❌ *Reporte de emergencia cancelado.*\n\n"
        "Si necesitas ayuda, llama al 911.",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start para emergencias"""
    # Verificar si viene con parámetros (ej: /start emergencia)
    args = context.args
    
    if args and args[0] == "emergencia":
        # Viene del bot normal - iniciar flujo de emergencia
        return await start_emergencia(update, context)
    else:
        # /start normal - mostrar mensaje de bienvenida
        await update.message.reply_text(
            "🚨 *SISTEMA DE EMERGENCIAS SIRMYN*\n\n"
            "Este bot es exclusivo para emergencias reales:\n"
            "• 👮 Policía/Seguridad Pública\n"
            "• 🚒 Bomberos\n"
            "• 🚑 Ambulancia/Protección Civil\n"
            "• 👩 Punto Violeta (Violencia de género)\n\n"
            "⚠️ *USO INMEDIATO:*\n"
            "Comando: /emergencia\n\n"
            "🔗 *VENÍAS DEL BOT NORMAL?*\n"
            "Vuelve a él usando: @SIRMYNBot",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

# Configurar el Conversation Handler
def setup_emergencia_handlers(application):
    """Configura los handlers para emergencias."""
   
    application.add_handler(CommandHandler("start", start_handler))
 
    emergencia_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('emergencia', start_emergencia)],
        states={
            SELECCIONAR_TIPO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tipo_emergencia)
            ],
            ESPERAR_UBICACION: [
                MessageHandler(filters.LOCATION, recibir_ubicacion)
            ],
            ESPERAR_DESCRIPCION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion)
            ],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_emergencia)],
    )
    
    application.add_handler(emergencia_conv_handler)