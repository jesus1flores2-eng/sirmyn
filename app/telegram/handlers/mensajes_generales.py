from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.telegram.common.utils import user_data, get_saludo
from app.telegram.dicts import TIPOS_DEPENDENCIAS
import logging

logger = logging.getLogger(__name__)

async def mensaje_general_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde a mensajes generales como 'gracias' o 'hola' con dependencia específica"""
    if not update.message or not update.message.text:
        return
    
    texto = update.message.text.lower().strip()
    user_id = update.effective_user.id
    datos_usuario = user_data.get(user_id, {})
    
    # Determinar la dependencia actual o última utilizada
    dependencia = None
    if "tipo" in datos_usuario:
        dependencia = datos_usuario["tipo"]
    elif "tipo_key" in datos_usuario:
        dependencia = TIPOS_DEPENDENCIAS.get(datos_usuario["tipo_key"])
    
    # Palabras clave
    palabras_gracias = ["gracias", "thank you", "thanks", "merci", "danke", 
                       "muchas gracias", "mil gracias", "te agradezco", "agradecido"]
    
    palabras_saludo = ["hola", "hello", "hi", "hey", "buenos días", 
                      "buenas tardes", "buenas noches", "saludos"]
    
    palabras_despedida = ["adiós", "bye", "chao", "hasta luego", "nos vemos"]
    
    # ========== GRACIAS ==========
    if any(palabra in texto for palabra in palabras_gracias):
        if dependencia:
            mensajes_dependencia = {
                "Agua potable": "🤖 En Agua Potable y alcantarillado estamos para servirle. ¡Gracias a usted! 💧",
                "Drenaje": "🤖 En el departamento de Drenaje estamos para servirle. ¡Gracias a usted! 🚰",
                "Aseo público": "🤖 En el servicio de Aseo Público estamos para servirle. ¡Gracias a usted! 🗑️",
                "Alumbrado público": "🤖 En el departamento de Alumbrado Público estamos para servirle. ¡Gracias a usted! 💡",
                "Parques y jardines": "🤖 En Parques y Jardines estamos para servirle. ¡Gracias a usted! 🌳",
                "Ecología": "🤖 En el departamento de Ecología estamos para servirle. ¡Gracias a usted! 🌍",
                "Seguridad pública": "🤖 En Seguridad Pública estamos para servirle. ¡Gracias a usted! 👮",
                "Obras públicas": "🤖 En Obras Públicas estamos para servirle. ¡Gracias a usted! 🏗️"
            }
            mensaje = mensajes_dependencia.get(dependencia, 
                f"🤖 En {dependencia} estamos para servirle. ¡Gracias a usted!")
        else:
            mensaje = "🤖 ¡Gracias a usted! En el sistema municipal estamos para servirle."
        
        await update.message.reply_text(mensaje, reply_markup=ReplyKeyboardRemove())
        return
    
    # ========== SALUDO ==========
    if any(palabra in texto for palabra in palabras_saludo):
        saludo = get_saludo()
        if dependencia:
            saludo_especifico = {
                "Agua potable": f"👋 {saludo}! Soy tu asistente de Agua Potable y alcantarillado. ¿En qué puedo ayudarte? 💧",
                "Drenaje": f"👋 {saludo}! Soy tu asistente de Drenaje. ¿En qué puedo ayudarte? 🚰",
                "Aseo público": f"👋 {saludo}! Soy tu asistente de Aseo Público. ¿En qué puedo ayudarte? 🗑️",
                "Alumbrado público": f"👋 {saludo}! Soy tu asistente de Alumbrado. ¿En qué puedo ayudarte? 💡",
                "Parques y jardines": f"👋 {saludo}! Soy tu asistente de Parques y Jardines. ¿En qué puedo ayudarte? 🌳",
                "Ecología": f"👋 {saludo}! Soy tu asistente de Ecología. ¿En qué puedo ayudarte? 🌍",
                "Seguridad pública": f"👋 {saludo}! Soy tu asistente de Seguridad Pública. ¿En qué puedo ayudarte? 👮",
                "Obras públicas": f"👋 {saludo}! Soy tu asistente de Obras Públicas. ¿En qué puedo ayudarte? 🏗️"
            }
            mensaje = saludo_especifico.get(dependencia, 
                f"👋 {saludo}! Soy tu asistente de {dependencia}. ¿En qué puedo ayudarte?")
        else:
            mensaje = f"👋 {saludo}! Para iniciar un reporte, usa el comando /start"
        
        await update.message.reply_text(mensaje, reply_markup=ReplyKeyboardRemove())
        return
    
    # ========== DESPEDIDA ==========
    if any(palabra in texto for palabra in palabras_despedida):
        await update.message.reply_text(
            "👋 ¡Hasta luego! Recuerda que puedes usar /start para nuevos reportes.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # ========== RESPUESTA POR DEFECTO ==========
    if len(texto) > 0:
        await update.message.reply_text(
            "🤖 No entendí tu mensaje. Puedes usar:\n"
            "• /start - Para iniciar un reporte\n"
            "• /estado - Para consultar un reporte\n"
            "• /ayuda - Para ver todos los comandos",
            reply_markup=ReplyKeyboardRemove()
        )

async def router_texto_completo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Router central que decide qué función maneja el texto
    basado en el estado del usuario (modo reparación, encuesta, etc.)
    """
    user_id = update.effective_user.id
    
    # Las fotos/videos NO se procesan aquí, las manejan los ConversationHandler
    if update.message and (update.message.photo or update.message.video):
        return
    
    if not update.message or not update.message.text:
        return
    
    texto = update.message.text
    logger.info(f"📱 Router texto: user_id={user_id}, texto='{texto[:50]}...'")
        
    # ⭐ 1.4 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE ASEO)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_aseo'):
        logger.info(f"❌ Router: Jefe de Aseo {user_id} enviando motivo de rechazo")
        from app.telegram.aseo.callbacks import manejar_motivo_rechazo_jefe_aseo
        await manejar_motivo_rechazo_jefe_aseo(update, context)
        return
        
    # ⭐ 1.5 MODO ESPERANDO MOTIVO DE RECHAZO (SUPERVISOR)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo'):
        logger.info(f"❌ Router: Supervisor {user_id} enviando motivo de rechazo")
        from app.telegram.callbacks.supervisor import manejar_motivo_rechazo_supervisor
        await manejar_motivo_rechazo_supervisor(update, context)
        return

    # ⭐ 1.7 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE ALUMBRADO)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_alumbrado'):
        logger.info(f"❌ Router: Jefe de Alumbrado {user_id} enviando motivo de rechazo")
        from app.telegram.alumbrado.callbacks import manejar_motivo_rechazo_jefe_alumbrado
        await manejar_motivo_rechazo_jefe_alumbrado(update, context)
        return

    # ⭐ 1.8 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE PARQUES)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_parques'):
        logger.info(f"❌ Router: Jefe de Parques {user_id} enviando motivo de rechazo")
        from app.telegram.parques.callbacks import manejar_motivo_rechazo_jefe_parques
        await manejar_motivo_rechazo_jefe_parques(update, context)
        return

    # ⭐ 1.9 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE ECOLOGÍA)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_ecologia'):
        logger.info(f"❌ Router: Jefe de Ecología {user_id} enviando motivo de rechazo")
        from app.telegram.ecologia.callbacks import manejar_motivo_rechazo_jefe_ecologia
        await manejar_motivo_rechazo_jefe_ecologia(update, context)
        return

    # ⭐ 2.0 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE SEGURIDAD)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_seguridad'):
        logger.info(f"❌ Router: Jefe de Seguridad {user_id} enviando motivo de rechazo")
        from app.telegram.seguridad.callbacks import manejar_motivo_rechazo_jefe_seguridad
        await manejar_motivo_rechazo_jefe_seguridad(update, context)
        return

    # ⭐ 2.1 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE OBRAS)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_obras'):
        logger.info(f"❌ Router: Jefe de Obras {user_id} enviando motivo de rechazo")
        from app.telegram.obras.callbacks import manejar_motivo_rechazo_jefe_obras
        await manejar_motivo_rechazo_jefe_obras(update, context)
        return

    # ⭐ 2.2 MODO ESPERANDO MOTIVO DE RECHAZO (JEFE DE BOMBEROS)
    if user_id in user_data and user_data[user_id].get('modo_esperando_motivo_rechazo_bomberos'):
        logger.info(f"❌ Router: Jefe de Bomberos {user_id} enviando motivo de rechazo")
        from app.telegram.bomberos.callbacks import manejar_motivo_rechazo_jefe_bomberos
        await manejar_motivo_rechazo_jefe_bomberos(update, context)
        return
    
    # 2. MODO COMENTARIO RECHAZO (DIRECTOR)
    if user_id in user_data and user_data[user_id].get('modo_comentario_rechazo'):
        logger.info(f"👨‍💼 Router: Enviando a manejar_comentario_rechazo_director")
        from app.telegram.callbacks.director import manejar_comentario_rechazo_director
        await manejar_comentario_rechazo_director(update, context)
        return
    
    # 3. MODO UBICACIÓN EXACTA (TEXTO)
    if user_id in user_data and user_data[user_id].get('modo_ubicacion_exacta'):
        logger.info(f"📍 Router: Enviando a manejar_descripcion_ubicacion")
        from app.telegram.handlers.ubicacion import manejar_descripcion_ubicacion
        await manejar_descripcion_ubicacion(update, context)
        return
    
    # 4. MODO ENCUESTA (COMENTARIO)
    if user_id in user_data and user_data[user_id].get('modo_encuesta'):
        paso_actual = user_data[user_id].get('paso_actual')
        if paso_actual == 'comentario':
            logger.info(f"📊 Router: Enviando a encuesta_comentario_handler")
            from app.telegram.callbacks.encuesta import encuesta_comentario_handler
            await encuesta_comentario_handler(update, context)
            return
        else:
            await update.message.reply_text(
                "📊 Por favor, completa la encuesta seleccionando las opciones de arriba.",
                parse_mode="Markdown"
            )
            return
            
    # ⭐ 4.5 MODO RECHAZO USUARIO - ESCRIBIENDO MOTIVO PERSONALIZADO
    if user_id in user_data and user_data[user_id].get('modo_rechazo_usuario'):
        paso_actual = user_data[user_id].get('paso_actual')
        if paso_actual == 'escribir_motivo':
            logger.info(f"✍️ Router: Usuario {user_id} escribiendo motivo de rechazo personalizado")
            from app.telegram.callbacks.rechazo import rechazo_otro_motivo_handler
            await rechazo_otro_motivo_handler(update, context)
            return
        else:
            await update.message.reply_text(
                "❌ Para rechazar, selecciona un motivo de la lista o escribe tu propio motivo.\n"
                "Si deseas cancelar, usa /cancelar."
            )
            return
    
    # 5. SI NADA DE LO ANTERIOR, USAR EL MANEJADOR GENERAL
    logger.info(f"🤖 Router: Enviando a mensaje_general_handler")
    await mensaje_general_handler(update, context)
