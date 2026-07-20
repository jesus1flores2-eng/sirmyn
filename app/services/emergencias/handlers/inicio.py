"""
Handlers para emergencias (SIRMYN)
"""
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from app.services.db_manager import DatabaseManager
from app.models.emergency import Emergency
from app.models.user import User
from app.extensions import db
from app.services.emergencias.notificaciones_emergencias import notificar_emergencia_a_directores

logger = logging.getLogger(__name__)

# Estados de la conversación
SELECCIONAR_TIPO, ESPERAR_UBICACION, ESPERAR_DESCRIPCION, ESPERAR_NUMERO, CONFIRMAR_NUMERO = range(5)

async def start_emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de emergencia con advertencia + solicitud de número (SOLO TEXTO)"""
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"🚨 Usuario {user_id} inició reporte de emergencia")
    logger.info(f"🔍 [START_EMERGENCIA] Context user_data: {context.user_data}")
    
    # Mensaje de advertencia + solicitud de número (sin botón de contacto)
    mensaje = (
        "🚨 *REPORTE DE EMERGENCIA - SIRMYN*\n\n"
        "⚠️ *ESTE SISTEMA ES PARA EMERGENCIAS REALES*\n\n"
        f"*{user.first_name or 'Usuario'}*, esto no es un juego.\n"
        "Un reporte falso puede *costar vidas* y está penado por la ley.\n\n"
        "📱 *Para continuar, necesitamos tu número de teléfono real.*\n"
        "Escribe tu número con el formato: *3312345678*\n\n"
        "_Al aceptar, tus datos y ubicación serán compartidos con las autoridades._"
    )
    
    await update.message.reply_text(
        text=mensaje,
        parse_mode='Markdown'
    )
    
    logger.info(f"🔍 [START_EMERGENCIA] Estado retornado: ESPERAR_NUMERO ({ESPERAR_NUMERO})")
    return ESPERAR_NUMERO

async def recibir_numero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el número de teléfono (SOLO TEXTO)"""
    logger.info("🔍 [RECIBIR_NUMERO] Función ejecutada")
    user = update.effective_user
    
    # Obtener el número del mensaje de texto
    numero = update.message.text.strip()
    logger.info(f"🔍 [RECIBIR_NUMERO] Texto recibido: {numero}")
    
    # Limpiar caracteres no numéricos
    numero = ''.join(filter(str.isdigit, numero))
    logger.info(f"🔍 [RECIBIR_NUMERO] Número limpio: {numero}")
    
    # Validar que tenga al menos 10 dígitos
    if len(numero) < 10:
        await update.message.reply_text(
            "❌ El número debe tener al menos 10 dígitos.\n"
            "Escribe tu número nuevamente (ej: 3312345678):",
            parse_mode='Markdown'
        )
        return ESPERAR_NUMERO
    
    logger.info(f"📱 Número válido: {numero}")
    
    # Guardar en context
    context.user_data['numero_emergencia'] = numero
    
    # Mostrar confirmación
    await update.message.reply_text(
        f"✅ *Número recibido:* `{numero}`\n\n"
        f"¿Es correcto?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, es correcto", callback_data=f"num_aceptar_{numero}")],
            [InlineKeyboardButton("❌ No, quiero cambiarlo", callback_data="num_cambiar")]
        ])
    )
    return CONFIRMAR_NUMERO

async def numero_confirmar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la confirmación del número"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data.startswith("num_aceptar_"):
        # Número confirmado
        numero = callback_data.replace("num_aceptar_", "")
        context.user_data['numero_emergencia'] = numero
        
        # Guardar número en la BD (para futuras emergencias)
        try:
            user_id = update.effective_user.id
            app = DatabaseManager.get_app()
            with app.app_context():
                usuario_db = User.query.filter_by(telegram_id=str(user_id)).first()
                if usuario_db:
                    usuario_db.telefono = numero
                    db.session.commit()
                    logger.info(f"✅ Número guardado en BD para usuario {user_id}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo guardar número en BD: {e}")
        
        # Mostrar opciones de tipo de emergencia
        keyboard = [
            [KeyboardButton("👮 POLICÍA"), KeyboardButton("🚒 BOMBEROS")],
            [KeyboardButton("🚑 AMBULANCIA"), KeyboardButton("👩 PUNTO VIOLETA")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await query.edit_message_text(
            "✅ *Número confirmado*\n\n"
            "📍 *¿QUÉ TIPO DE EMERGENCIA ES?*\n\n"
            "• 👮 POLICÍA: Asalto, violencia, robo\n"
            "• 🚒 BOMBEROS: Incendio, explosión\n"
            "• 🚑 AMBULANCIA: Accidente, heridos\n"
            "• 👩 PUNTO VIOLETA: Violencia de género",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return SELECCIONAR_TIPO
    
    elif callback_data == "num_cambiar":
        # El usuario quiere cambiar el número
        keyboard = [[KeyboardButton("📱 Compartir mi número", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await query.edit_message_text(
            "✏️ *Escribe tu número de teléfono*\n\n"
            "Toca el botón para compartirlo automáticamente,\n"
            "o escríbelo manualmente (ej: 3312345678):",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ESPERAR_NUMERO

async def recibir_tipo_emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el tipo de emergencia"""
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
        tipo = "policia"
        tipo_display = "👮 POLICÍA"
    
    context.user_data['emergencia_tipo'] = tipo
    context.user_data['emergencia_tipo_display'] = tipo_display
    
    logger.info(f"📋 Usuario seleccionó tipo: {tipo}")
    
    # Solicitar ubicación
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
    """Recibe la ubicación"""
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
        "• 'Accidente automovilístico con heridos'\n\n"
        "_Sé breve pero claro. Máximo 2 líneas._",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    return ESPERAR_DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la descripción y guarda la emergencia"""
    descripcion = update.message.text
    context.user_data['emergencia_descripcion'] = descripcion
    
    user = update.effective_user
    numero = context.user_data.get('numero_emergencia', 'No proporcionado')
    
    logger.info(f"📝 Descripción recibida: {descripcion[:50]}...")
    
    datos_emergencia = {
        'tipo': context.user_data.get('emergencia_tipo', 'policia'),
        'subtipo': '',
        'latitud': context.user_data.get('emergencia_latitud'),
        'longitud': context.user_data.get('emergencia_longitud'),
        'direccion_aproximada': 'Ubicación por GPS',
        'reportante': f"{user.first_name} {user.last_name or ''}".strip(),
        'telegram_user_id': user.id,
        'telegram_username': user.username,
        'numero_contacto': numero,
        'descripcion': descripcion,
        'nivel_urgencia': 1,
        'status': 'reportada',
        'plataforma': 'telegram',
        'municipio_id': 1,
        'municipio_nombre': 'Ixtlahuacán de los Membrillos'
    }
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            emergencia = Emergency(
                municipio_id=datos_emergencia['municipio_id'],
                municipio_nombre=datos_emergencia['municipio_nombre'],
                tipo=datos_emergencia['tipo'],
                subtipo=datos_emergencia['subtipo'],
                latitud=datos_emergencia['latitud'],
                longitud=datos_emergencia['longitud'],
                direccion_aproximada=datos_emergencia['direccion_aproximada'],
                reportante=datos_emergencia['reportante'],
                telegram_user_id=datos_emergencia['telegram_user_id'],
                telegram_username=datos_emergencia['telegram_username'],
                numero_contacto=datos_emergencia['numero_contacto'],
                descripcion=datos_emergencia['descripcion'],
                nivel_urgencia=datos_emergencia['nivel_urgencia'],
                status=datos_emergencia['status']
            )
            
            db.session.add(emergencia)
            db.session.commit()
            
            emergencia.folio_publico = f"E-{emergencia.timestamp_reporte.year}-{emergencia.id:05d}"
            db.session.commit()
            
            logger.info(f"✅ Emergencia guardada en BD: #{emergencia.id} - {emergencia.folio_publico}")
            
            notificaciones = await notificar_emergencia_a_directores(
                bot=context.bot,
                db_session=db.session,
                report_id=emergencia.id,
                datos_emergencia=datos_emergencia
            )
            
            await update.message.reply_text(
                f"✅ *EMERGENCIA REPORTADA EXITOSAMENTE*\n\n"
                f"📋 *Folio:* `{emergencia.folio_publico}`\n"
                f"📍 *Tipo:* {context.user_data.get('emergencia_tipo_display', 'Emergencia')}\n"
                f"📱 *Número de contacto:* {numero}\n"
                f"👮 *Notificado a:* {notificaciones} autoridad(es)\n\n"
                f"*La ayuda está en camino. Mantén tu teléfono cerca.*",
                parse_mode='Markdown'
            )
            
            logger.info(f"✅ Emergencia procesada. Report ID: {emergencia.id}")
            
    except Exception as e:
        logger.error(f"❌ Error guardando emergencia: {e}")
        await update.message.reply_text(
            "❌ Error al registrar la emergencia. Intenta nuevamente o contacta al 911.",
            parse_mode='Markdown'
        )
    
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
