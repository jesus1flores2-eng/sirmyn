from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado
from app.services.db_manager import DatabaseManager
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

# Estados de emergencia
EMERGENCIA_DEPARTAMENTO, EMERGENCIA_TELEFONO, EMERGENCIA_ADVERTENCIA, EMERGENCIA_SUBTIPO, EMERGENCIA_UBICACION, EMERGENCIA_COMENTARIO, EMERGENCIA_EVIDENCIA, EMERGENCIA_CONFIRMAR = range(60, 68)


async def emergencia_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de emergencia desde el menú principal"""
    user_id = update.effective_user.id
    
    es_patrullero = False
    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(user_id), is_active=True).first()
        if usuario and usuario.rol_especifico in ['patrullero', 'policia', 'comandante', 'cuadrilla']:
            if usuario.area == 'seguridad' or usuario.team_id:
                from app.models.team import Team
                team = Team.query.get(usuario.team_id)
                if team and team.area == 'seguridad':
                    es_patrullero = True
    
    user_data[user_id] = {'modo_emergencia': True, 'es_patrullero': es_patrullero}
    user_data[user_id]['nombre_telegram'] = update.effective_user.first_name or update.effective_user.username or 'Ciudadano'
    
    keyboard = [
        ["👮 Seguridad Pública", "🚒 Bomberos"],
        ["🛡️ Protección Civil", "💜 Punto Violeta"],
    ]
    
    if es_patrullero:
        keyboard.append(["🔴 BOTÓN DE PÁNICO"])
    
    keyboard.append(["↩️ Volver al menú"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "🚨 *EMERGENCIA - ATENCIÓN INMEDIATA*\n\n"
        "⚠️ *ADVERTENCIA:* El uso indebido de este servicio constituye un delito.\n"
        "Solo usar en casos REALES de emergencia.\n\n"
        "Selecciona el tipo de emergencia:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return EMERGENCIA_DEPARTAMENTO


async def emergencia_departamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Selecciona departamento y pide teléfono directamente"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "↩️ Volver al menú":
        from app.telegram.handlers.start import menu_principal_handler
        limpiar_estado(user_id)
        return await menu_principal_handler(update, context)
    
    if texto == "🔴 BOTÓN DE PÁNICO":
        return await boton_panico(update, context)
    
    departamentos = {
        "👮 Seguridad Pública": "seguridad",
        "🚒 Bomberos": "bomberos",
        "🛡️ Protección Civil": "proteccion_civil",
        "💜 Punto Violeta": "punto_violeta"
    }
    
    depto = departamentos.get(texto)
    if not depto:
        await update.message.reply_text("Selecciona una opción del teclado.")
        return EMERGENCIA_DEPARTAMENTO
    
    user_data[user_id]['emergencia_depto'] = depto
    user_data[user_id]['emergencia_depto_nombre'] = texto
    
    await update.message.reply_text(
        f"⚠️ *{texto} - EMERGENCIA*\n\n"
        f"⚖️ Recuerda: El uso indebido es un DELITO.\n\n"
        "📱 *NÚMERO DE TELÉFONO*\n"
        "Escribe tu número a 10 dígitos (ej: 4491234567)\n"
        "o presiona ❌ Cancelar:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancelar"]], resize_keyboard=True)
    )
    
    return EMERGENCIA_TELEFONO


async def emergencia_advertencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma advertencia y pide teléfono"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if texto != "✅ Sí, es real":
        await update.message.reply_text("Debes confirmar '✅ Sí, es real' para continuar.")
        return EMERGENCIA_ADVERTENCIA
    
    await update.message.reply_text(
        "📱 *NÚMERO DE TELÉFONO*\n\n"
        "Por seguridad, necesitamos tu número de contacto:\n"
        "Escribe tu número a 10 dígitos (ej: 4491234567)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return EMERGENCIA_TELEFONO


async def emergencia_telefono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda teléfono y pide ubicación GPS"""
    user_id = update.effective_user.id
    telefono = update.message.text.strip()
    
    import re
    if not re.match(r'^\d{10}$', telefono):
        await update.message.reply_text("❌ El número debe ser de 10 dígitos. Intenta de nuevo:")
        return EMERGENCIA_TELEFONO
    
    user_data[user_id]['telefono'] = telefono
    
    keyboard = [[KeyboardButton("📍 ENVIAR MI UBICACIÓN GPS", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📍 *UBICACIÓN EXACTA*\n\n"
        "Para atender tu emergencia *necesitamos tu ubicación GPS*.\n"
        "Presiona el botón para compartir tu ubicación actual.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return EMERGENCIA_UBICACION


async def emergencia_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe ubicación GPS y muestra subtipos"""
    user_id = update.effective_user.id
    location = update.message.location
    
    if not location:
        await update.message.reply_text("❌ Debes enviar tu ubicación GPS. Presiona el botón.")
        return EMERGENCIA_UBICACION
    
    user_data[user_id]['latitud'] = location.latitude
    user_data[user_id]['longitud'] = location.longitude
    
    try:
        from app.services.geocoding import obtener_direccion_osm
        direccion = obtener_direccion_osm(location.latitude, location.longitude)
        if direccion:
            user_data[user_id]['localidad_detectada'] = direccion.get('localidad', 'No detectada')
            user_data[user_id]['calle_detectada'] = direccion.get('road', 'No detectada')
    except Exception as e:
        logger.warning(f"No se pudo obtener dirección: {e}")
        user_data[user_id]['localidad_detectada'] = 'No detectada'
        user_data[user_id]['calle_detectada'] = 'No detectada'
    
    depto = user_data[user_id].get('emergencia_depto', 'seguridad')
    
    subtipos = {
        'seguridad': [
            ["🔫 Balacera / Disparos", "👊 Agresión física"],
            ["🚗 Robo de vehículo", "🏠 Robo a casa"],
            ["🏪 Robo a negocio", "🗡️ Portación de arma"],
            ["🚨 Violencia familiar", "📵 Acoso callejero"],
            ["⚠️ Otro incidente"]
        ],
        'bomberos': [
            ["🔥 Incendio casa", "🔥 Incendio vehículo"],
            ["🌲 Incendio forestal", "💥 Explosión"],
            ["🧯 Fuga de gas", "🏢 Incendio edificio"],
            ["⚠️ Otro incidente"]
        ],
        'proteccion_civil': [
            ["🌊 Inundación", "🏚️ Derrumbe"],
            ["🌪️ Tornado/Viento", "🧪 Fuga química"],
            ["🚑 Accidente masivo", "⚠️ Otro incidente"]
        ],
        'punto_violeta': [
            ["👩‍🦰 Violencia de género", "🏠 Violencia doméstica"],
            ["🚨 Acoso sexual", "🔒 Secuestro"],
            ["⚠️ Otra emergencia"]
        ]
    }
    
    opciones = subtipos.get(depto, subtipos['seguridad'])
    opciones.append(["↩️ Cancelar"])
    
    reply_markup = ReplyKeyboardMarkup(opciones, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Ubicación recibida\n\nSelecciona el tipo de incidente:",
        reply_markup=reply_markup
    )
    
    return EMERGENCIA_SUBTIPO


async def emergencia_subtipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda subtipo y pide evidencia"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "↩️ Cancelar":
        await update.message.reply_text("❌ Emergencia cancelada.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    user_data[user_id]['subtipo'] = texto
    
    keyboard = [["📸 Subir evidencia", "➡️ Omitir"], ["↩️ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ *Incidente:* {texto}\n\n"
        "¿Deseas agregar evidencia (foto/video)?\n"
        "Puedes enviarla directamente o presionar 'Omitir'.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return EMERGENCIA_EVIDENCIA


async def emergencia_evidencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja evidencia y muestra resumen antes de confirmar"""
    user_id = update.effective_user.id
    
    # Si es foto/video, guardarla y mostrar resumen
    if update.message.photo or update.message.video:
        file = await (update.message.photo[-1].get_file() if update.message.photo else update.message.video.get_file())
        ext = 'jpg' if update.message.photo else 'mp4'
        import uuid, os
        filename = f"emergencia_{user_id}_{uuid.uuid4().hex[:8]}.{ext}"
        os.makedirs("uploads/emergencias", exist_ok=True)
        await file.download_to_drive(f"uploads/emergencias/{filename}")
        user_data[user_id]['evidencia'] = f"uploads/emergencias/{filename}"
        await update.message.reply_text("✅ Evidencia recibida.")
        # Mostrar resumen
        return await _mostrar_resumen(update, user_id)
    
    texto = update.message.text.strip() if update.message.text else ""
    
    if texto == "↩️ Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    # Si presiona "Subir evidencia", pedir la foto
    if texto == "📸 Subir evidencia":
        await update.message.reply_text(
            "Envía la foto o video ahora 📸",
            reply_markup=ReplyKeyboardRemove()
        )
        return EMERGENCIA_EVIDENCIA
    
    # Si presiona "Omitir", saltar a resumen
    if texto == "➡️ Omitir":
        user_data[user_id]['evidencia'] = None
        return await _mostrar_resumen(update, user_id)
    
    await update.message.reply_text("Envía una foto/video o presiona 'Omitir'.")
    return EMERGENCIA_EVIDENCIA


async def _mostrar_resumen(update: Update, user_id: int):
    """Función auxiliar para mostrar resumen"""
    datos = user_data[user_id]
    resumen = (
        f"🚨 *RESUMEN DE EMERGENCIA*\n\n"
        f"🏛️ *Depto:* {datos.get('emergencia_depto_nombre', 'N/A')}\n"
        f"📱 *Teléfono:* {datos.get('telefono', 'N/A')}\n"
        f"📍 *GPS:* {datos.get('latitud')}, {datos.get('longitud')}\n"
        f"⚠️ *Incidente:* {datos.get('subtipo', 'N/A')}\n"
        f"📸 *Evidencia:* {'Sí' if datos.get('evidencia') else 'No'}\n\n"
        f"¿Confirmar envío de emergencia?"
    )
    keyboard = [["🚨 CONFIRMAR EMERGENCIA", "❌ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(resumen, parse_mode="Markdown", reply_markup=reply_markup)
    return EMERGENCIA_CONFIRMAR

async def emergencia_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía la emergencia a cabina y notifica"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if texto != "🚨 CONFIRMAR EMERGENCIA":
        await update.message.reply_text("Presiona '🚨 CONFIRMAR EMERGENCIA' o '❌ Cancelar'.")
        return EMERGENCIA_CONFIRMAR
    
    datos = user_data[user_id]
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment, Localidad
            from app.models.team import Team
            from app.models.status import Status
            from app.models.user import User
            from app.extensions import db
            from datetime import datetime
            from app.routes.telegram_routes import get_telegram_app
            
            depto = datos.get('emergencia_depto', 'seguridad')
            depto_nombre = datos.get('emergencia_depto_nombre', 'Seguridad Pública')
            
            localidad_id = 1
            calle_id = 1
            localidad_nombre = datos.get('localidad_detectada', 'No detectada')
            
            if localidad_nombre and localidad_nombre != 'No detectada':
                loc = Localidad.query.filter(Localidad.nombre.ilike(f"%{localidad_nombre}%")).first()
                if loc:
                    localidad_id = loc.id
                    localidad_nombre = loc.nombre
            
            nuevo_reporte = Report(
                telefono=datos.get('telefono', str(user_id)),
                reportante=datos.get('nombre_telegram', 'Ciudadano'),
                tipo=f"EMERGENCIA - {depto_nombre}",
                subtipo=datos.get('subtipo', 'Emergencia'),
                numero="S/N",
                descripcion_problema=f"EMERGENCIA: {datos.get('subtipo', '')}",
                evidencia=datos.get('evidencia'),
                timestamp=datetime.utcnow(),
                calle_id=calle_id,
                localidad_id=localidad_id,
                plataforma="telegram_emergencia",
                latitud=datos.get('latitud'),
                longitud=datos.get('longitud')
            )
            db.session.add(nuevo_reporte)
            db.session.commit()
            
            team = Team.query.filter_by(area=depto, nombre='Sin asignar').first()
            if not team:
                team = Team.query.filter_by(nombre='Sin asignar').first()
            
            status_asignado = Status.query.filter_by(descripcion='Asignado').first()
            if not status_asignado:
                status_asignado = Status(descripcion='Asignado')
                db.session.add(status_asignado)
                db.session.commit()
            
            asignacion = Assignment(
                report_id=nuevo_reporte.id,
                team_id=team.id if team else 1,
                status_id=status_asignado.id,
                timestamp=datetime.utcnow()
            )
            db.session.add(asignacion)
            db.session.commit()
            
            cabina = User.query.filter_by(area=depto, rol_especifico='jefe_area', is_active=True).first()
            if not cabina:
                cabina = User.query.filter_by(area=depto, rol_especifico='director', is_active=True).first()
            
            if cabina and cabina.telegram_id:
                bot_app = get_telegram_app()
                maps_url = f"https://www.google.com/maps?q={datos.get('latitud')},{datos.get('longitud')}"
                
                mensaje_cabina = (
                    f"🚨 *EMERGENCIA - {depto_nombre.upper()}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📋 *Folio:* #{nuevo_reporte.id}\n"
                    f"⚠️ *Incidente:* {datos.get('subtipo', 'Emergencia')}\n"
                    f"📱 *Teléfono:* {datos.get('telefono', 'N/A')}\n"
                    f"📍 *Ver ubicación:* [Google Maps]({maps_url})\n\n"
                    f"⚡ *ACCIÓN INMEDIATA REQUERIDA*"
                )
                
                await bot_app.bot.send_message(
                    chat_id=int(cabina.telegram_id),
                    text=mensaje_cabina,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await update.message.reply_text(
                f"✅ *EMERGENCIA ENVIADA - Folio #{nuevo_reporte.id}*\n\n"
                f"Las autoridades han sido notificadas.\n"
                f"Mantén la calma y espera asistencia.\n\n"
                f"📞 Tu teléfono registrado: {datos.get('telefono')}",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            
    except Exception as e:
        logger.error(f"❌ Error enviando emergencia: {e}")
        await update.message.reply_text("❌ Error al enviar la emergencia. Intenta de nuevo.")
    
    limpiar_estado(user_id)
    return ConversationHandler.END


# ============================================================
# BOTÓN DE PÁNICO (PATRULLEROS)
# ============================================================
async def boton_panico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activa el botón de pánico para patrulleros"""
    user_id = update.effective_user.id
    
    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(user_id), is_active=True).first()
        if not usuario:
            await update.message.reply_text("❌ No autorizado.")
            limpiar_estado(user_id)
            return ConversationHandler.END
    
    keyboard = [[KeyboardButton("📍 ENVIAR UBICACIÓN - PÁNICO", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    user_data[user_id]['panico_activo'] = True
    user_data[user_id]['patrullero_nombre'] = usuario.nombre
    
    await update.message.reply_text(
        "🔴 *BOTÓN DE PÁNICO ACTIVADO*\n\n"
        "Envía tu ubicación GPS *INMEDIATAMENTE*.\n"
        "Se notificará a todos los patrulleros cercanos y a cabina.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return EMERGENCIA_UBICACION
