from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup
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
    
    palabras_reporte = ["reporte", "reportar", "reclamar", "queja", "problema", "iniciar"]
    palabras_consulta = ["consultar", "ver", "revisar", "checar", "estado", "estatus"]
    
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
    
    # ========== SALUDO O INTENCIÓN DE REPORTE ==========
    if any(palabra in texto for palabra in palabras_saludo) or any(palabra in texto for palabra in palabras_reporte):
        saludo = get_saludo()
        nombre = update.effective_user.first_name or "Usuario"
        
        # Verificar si tiene reportes activos
        try:
            app = DatabaseManager.get_app()
            with app.app_context():
                from app.models.report import Report
                reportes_activos = Report.query.filter_by(telefono=str(user_id)).count()
        except:
            reportes_activos = 0
        
        keyboard = [["📋 INICIAR REPORTE", "📊 CONSULTAR REPORTE"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        mensaje = f"👋 *¡{saludo}, {nombre}!*\n\n"
        if reportes_activos > 0:
            mensaje += f"Tienes *{reportes_activos}* reporte(s) registrado(s).\n\n"
        mensaje += "Presiona el botón para iniciar un nuevo reporte."
        
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=reply_markup)
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
    
    # ⭐ DETECCIÓN DE BOTONES DEL MENÚ PRINCIPAL (EXCEPTO CONSULTAR REPORTE)
    if texto in ['📋 REPORTE NORMAL', '🚨 EMERGENCIA', '❌ CANCELAR', '↩️ VOLVER AL MENÚ']:
        from app.telegram.handlers.start import menu_principal_handler
        from app.telegram.common.states import MENU_PRINCIPAL
        return await menu_principal_handler(update, context)
    
    # ⭐ BOTÓN CONSULTAR REPORTE
    if texto == "📊 CONSULTAR REPORTE":
        user_data[user_id] = {'modo_consulta': True}
        await update.message.reply_text(
            "📋 Ingresa el *folio de tu reporte* tal como aparece en tu confirmación.\n"
            "Ejemplo: *ALUM-0006*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # ⭐ MODO CONSULTA: usuario escribió el folio
    if user_id in user_data and user_data[user_id].get('modo_consulta'):
        if 'folio_consulta' not in user_data[user_id]:
            # Guardar el folio y pedir nombre
            user_data[user_id]['folio_consulta'] = texto
            await update.message.reply_text(
                "🔐 Para verificar tu identidad, escribe el nombre de quien levantó el reporte.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        else:
            # Verificar nombre y mostrar reporte
            from app.services.db_manager import DatabaseManager
            app = DatabaseManager.get_app()
            with app.app_context():
                from app.models.report import Report, Assignment, Localidad, Calle
                
                folio = user_data[user_id].get('folio_consulta').upper()
                nombre = texto.lower()
                
                # Buscar por folio o id
                rep = Report.query.filter_by(folio=folio).first()
                if not rep and folio.isdigit():
                    rep = Report.query.filter_by(id=int(folio)).first()
                
                if rep and (rep.reportante or '').lower() == nombre:
                    asignacion = Assignment.query.filter_by(report_id=rep.id).order_by(Assignment.timestamp.desc()).first()
                    estado = asignacion.status.descripcion if asignacion and asignacion.status else 'Sin estado'
                    cuadrilla = asignacion.team.nombre if asignacion and asignacion.team else 'Sin asignar'
                    calle = Calle.query.get(rep.calle_id)
                    loc = Localidad.query.get(rep.localidad_id)
                    
                    # Obtener usuario que atiende
                    from app.models.user import User
                    usuario = User.query.filter_by(team_id=asignacion.team_id).first()
                    nombre_usuario = usuario.nombre if usuario else 'Sin usuario'
                    observaciones = asignacion.observaciones or 'Sin observaciones'
                    
                    mensaje = (
                        f"📋 *Estado del Reporte {rep.folio or rep.id}*\n\n"
                        f"📍 *Dirección:* {calle.nombre if calle else 'N/D'} #{rep.numero}, {loc.nombre if loc else 'N/D'}\n"
                        f"👤 *Reportante:* {rep.reportante}\n"
                        f"🛠 *Cuadrilla:* {cuadrilla}\n"
                        f"👷 *Atendiendo:* {nombre_usuario}\n"
                        f"📌 *Estatus:* {estado}\n"
                        f"📝 *Observaciones:* {observaciones}"
                    )
                    await update.message.reply_text(mensaje, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
                else:
                    keyboard = [["📋 INICIAR REPORTE", "📊 CONSULTAR REPORTE"]]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    await update.message.reply_text(
                        "❌ No se encontró el reporte o el nombre no coincide.\n\n"
                        "Puedes intentar de nuevo:",
                        reply_markup=reply_markup
                    )
            
            # Limpiar modo consulta
            user_data[user_id].pop('modo_consulta', None)
            user_data[user_id].pop('folio_consulta', None)
            return
    
    # ⭐ DETECCIÓN DE DEPARTAMENTOS (1️⃣, 2️⃣, etc.)
    if texto.startswith(('1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣')):
        from app.telegram.handlers.tipo import tipo_handler
        return await tipo_handler(update, context)
        
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
