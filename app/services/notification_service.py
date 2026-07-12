import logging
from datetime import datetime
from app.services.db_manager import DatabaseManager
from app.telegram.keyboards import construir_botones_reporte
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import os
from app.extensions import db
from flask import current_app, url_for

logger = logging.getLogger(__name__)


# ============================================================
# 1. OBTENER RESPONSABLES SEGÚN TIPO DE REPORTE
# ============================================================
def obtener_directores_por_tipo_reporte(tipo_reporte: str):
    """
    Obtiene responsables según el tipo de reporte.
    - Agua/Drenaje: Jefe Técnico (principal) + Director (informativo)
    - Otros: Director correspondiente
    """
    try:
        from app.models.user import User
        
        responsables = []
        
        # ========== AGUA POTABLE O DRENAJE ==========
        if tipo_reporte in ["Agua potable", "Drenaje"]:
            logger.info(f"💧 [NOTIFICACIÓN] Procesando {tipo_reporte} - lógica especial")
            
            # 1. JEFE TÉCNICO (mensaje COMPLETO con botones)
            jefe_tecnico = User.query.filter_by(
                area='agua',
                rol_especifico='jefe_area_tecnica',
                is_active=True
            ).first()
            
            if jefe_tecnico:
                responsables.append({
                    'usuario': jefe_tecnico,
                    'tipo_mensaje': 'completo_con_botones',
                    'puede_asignar': True,
                    'es_jefe_tecnico': True,
                    'descripcion': 'Jefe Técnico de Agua/Drenaje'
                })
                logger.info(f"✅ Jefe Técnico encontrado: {jefe_tecnico.nombre}")
            else:
                logger.warning("⚠️ No se encontró jefe técnico para agua")
            
            # 2. DIRECTOR AGUA (mensaje INFORMATIVO)
            director_agua = User.query.filter_by(
                area='agua',
                rol_especifico='director',
                is_active=True
            ).first()
            
            if director_agua:
                if jefe_tecnico and jefe_tecnico.id == director_agua.id:
                    logger.info("ℹ️ Misma persona: Director y Jefe Técnico")
                else:
                    responsables.append({
                        'usuario': director_agua,
                        'tipo_mensaje': 'informativo_simple_sin_botones',
                        'puede_asignar': False,
                        'es_jefe_tecnico': False,
                        'descripcion': 'Director de Agua (informativo)'
                    })
                    logger.info(f"✅ Director Agua encontrado: {director_agua.nombre}")
            else:
                logger.warning("⚠️ No se encontró director de agua")
            
            return responsables
        
        # ========== OTROS DEPARTAMENTOS ==========
        mapeo_tipo_a_area = {
            "Aseo público": "aseo",
            "Alumbrado público": "alumbrado",
            "Parques y jardines": "parques",
            "Ecología": "ecologia",
            "Seguridad pública": "seguridad",
            "Obras públicas": "obras",
            "Bomberos": "bomberos"
        }
        
        area_reporte = mapeo_tipo_a_area.get(tipo_reporte)
        if not area_reporte:
            logger.warning(f"⚠️ Área no mapeada para tipo: {tipo_reporte}")
            return []
        
        director = User.query.filter_by(
            area=area_reporte,
            rol_especifico='director',
            is_active=True
        ).first()
        
        if director:
            responsables.append({
                'usuario': director,
                'tipo_mensaje': 'completo_con_botones',
                'puede_asignar': True,
                'es_jefe_tecnico': False,
                'descripcion': f'Director de {area_reporte.title()}'
            })
            logger.info(f"✅ Director {area_reporte} encontrado: {director.nombre}")
        else:
            logger.warning(f"⚠️ No se encontró director para {area_reporte}")
        
        return responsables
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo responsables: {e}", exc_info=True)
        return []


# ============================================================
# 2. FUNCIÓN AUXILIAR PARA CONSTRUIR ENLACES DE EVIDENCIA
# ============================================================
def construir_enlace_evidencia(evidencia: str, nombre_base: str = "evidencia"):
    """
    Construye un enlace formateado para una evidencia (Cloudinary o local).
    Retorna (texto_con_enlace, es_archivo)
    """
    if not evidencia:
        return None, False
    
    evidencia = evidencia.strip()
    
    # Determinar si es URL de Cloudinary o ruta local
    if evidencia.startswith('http'):
        url = evidencia
        # Extraer nombre del archivo de la URL
        nombre_archivo = evidencia.split('/')[-1].split('?')[0]
        # Limpiar nombre si es muy largo
        if len(nombre_archivo) > 30:
            nombre_archivo = nombre_archivo[:27] + "..."
        return f"[{nombre_archivo}]({url})", True
    
    # Ruta local
    if evidencia.startswith('evidencias/'):
        url = url_for('static', filename=evidencia, _external=True)
    else:
        url = url_for('admin.uploaded_file', filename=evidencia, _external=True)
    
    # Extraer nombre del archivo
    nombre_archivo = os.path.basename(evidencia)
    if len(nombre_archivo) > 30:
        nombre_archivo = nombre_archivo[:27] + "..."
    
    return f"[{nombre_archivo}]({url})", True


# ============================================================
# 3. NOTIFICAR NUEVO REPORTE
# ============================================================
async def notificar_director_nuevo_reporte(reporte_id: int, telegram_id: int, tipo_reporte: str):
    """
    Notifica a responsables según el tipo de reporte.
    - Agua/Drenaje: Jefe Técnico (completo) + Director (informativo)
    - Otros: Director correspondiente (completo)
    """
    try:
        from app.models.report import Report, Localidad, Calle
        from app.models.user import User
        from app.routes.telegram_routes import get_telegram_app
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            logger.error(f"❌ Reporte {reporte_id} no encontrado")
            return False
        
        localidad = Localidad.query.get(reporte.localidad_id)
        calle = Calle.query.get(reporte.calle_id)
        
        responsables = obtener_directores_por_tipo_reporte(tipo_reporte)
        
        if not responsables:
            logger.warning(f"⚠️ No hay responsables para {tipo_reporte}")
            return False
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return False
        
        notificaciones_enviadas = 0
        
        for responsable in responsables:
            usuario = responsable['usuario']
            if not usuario or not usuario.telegram_id:
                logger.warning(f"⚠️ Usuario {usuario.nombre if usuario else 'N/A'} sin Telegram ID")
                continue
            
            try:
                telegram_id_destino = int(usuario.telegram_id)
            except:
                logger.warning(f"⚠️ Telegram ID inválido para {usuario.nombre}")
                continue
            
            if responsable['tipo_mensaje'] == 'completo_con_botones':
                mensaje = await construir_mensaje_completo(reporte, localidad, calle)
                reply_markup = construir_botones_reporte(reporte.id, es_director=True)
            
            elif responsable['tipo_mensaje'] == 'informativo_simple_sin_botones':
                mensaje = (
                    f"💧 *INFORMACIÓN - NUEVO REPORTE {tipo_reporte.upper()}*\n\n"
                    f"📋 *Folio:* #{reporte.id}\n"
                    f"📍 *Ubicación:* {calle.nombre if calle else 'N/D'} #{reporte.numero}\n"
                    f"👤 *Reportante:* {reporte.reportante}\n"
                    f"📱 *Teléfono:* {reporte.telefono}\n"
                    f"🔧 *Problema:* {reporte.subtipo}\n\n"
                    f"📅 *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"*📋 Jefe Técnico ha sido notificado para asignación.*"
                )
                reply_markup = None
            
            else:
                mensaje = (
                    f"📋 *NUEVO REPORTE*\n\n"
                    f"Folio: #{reporte.id}\n"
                    f"Ubicación: {calle.nombre if calle else 'N/D'} #{reporte.numero}\n"
                    f"Problema: {reporte.tipo} - {reporte.subtipo}\n"
                    f"Reportante: {reporte.reportante}"
                )
                keyboard = [[InlineKeyboardButton("📋 Ver Detalles", callback_data=f"dir_detalle_{reporte.id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await bot_app.bot.send_message(
                    chat_id=telegram_id_destino,
                    text=mensaje,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                notificaciones_enviadas += 1
                logger.info(f"✅ Notificación enviada a {usuario.nombre} (ID: {usuario.telegram_id})")
            except Exception as e:
                logger.error(f"❌ Error enviando a {usuario.nombre}: {e}")
        
        logger.info(f"📊 Notificaciones enviadas: {notificaciones_enviadas}")
        return notificaciones_enviadas > 0
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_director_nuevo_reporte: {e}", exc_info=True)
        return False


# ============================================================
# 4. CONSTRUIR MENSAJE COMPLETO (con evidencia)
# ============================================================
async def construir_mensaje_completo(reporte, localidad, calle):
    """Construye mensaje completo con botones de asignación y evidencia"""
    mensaje = (
        f"🚨 *NUEVO REPORTE - {reporte.tipo.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 *Folio:* #{reporte.id}\n"
        f"📍 *Ubicación:* {calle.nombre if calle else 'N/D'} #{reporte.numero}, "
        f"{localidad.nombre if localidad else 'N/D'}\n"
        f"📞 *Reportante:* {reporte.reportante}\n"
        f"🔧 *Tipo:* {reporte.tipo}\n"
        f"📝 *Subtipo:* {reporte.subtipo}\n"
        f"📄 *Descripción:*\n"
        f"{reporte.descripcion_problema[:150]}{'...' if len(reporte.descripcion_problema) > 150 else ''}\n\n"
    )
    
    # ============================================================
    # EVIDENCIA DEL USUARIO (con enlace)
    # ============================================================
    if reporte.evidencia:
        enlace, _ = construir_enlace_evidencia(reporte.evidencia, "evidencia_usuario")
        mensaje += f"📎 *Evidencia:* {enlace}\n\n"
    
    mensaje += (
        f"⏰ *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
        f"*👷 ACCIONES RÁPIDAS:*"
    )
    
    return mensaje


# ============================================================
# 5. NOTIFICAR ASIGNACIÓN A CUADRILLA
# ============================================================
async def notificar_asignacion_a_cuadrilla(reporte_id: int, user_id_asignado: int):
    """
    Notifica a una cuadrilla que se le ha asignado un reporte.
    """
    try:
        from app.models.report import Report, Assignment, Localidad, Calle
        from app.models.user import User
        from app.models.team import Team
        from app.models.status import Status
        from app.routes.telegram_routes import get_telegram_app
        import os
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            logger.error(f"❌ Reporte {reporte_id} no encontrado")
            return False
        
        usuario = User.query.get(user_id_asignado)
        if not usuario or not usuario.telegram_id:
            logger.error(f"❌ Usuario {user_id_asignado} no tiene Telegram")
            return False
        
        localidad = Localidad.query.get(reporte.localidad_id)
        calle = Calle.query.get(reporte.calle_id)
        
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        status = Status.query.get(asignacion.status_id) if asignacion else None
        
        mensaje = (
            f"🚨 *NUEVO REPORTE ASIGNADO*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 *Folio:* #{reporte.id}\n"
            f"📍 *Ubicación:* {calle.nombre if calle else 'N/D'} #{reporte.numero}, "
            f"{localidad.nombre if localidad else 'N/D'}\n"
            f"📞 *Reportante:* {reporte.reportante}\n"
            f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
            f"📄 *Descripción:* {reporte.descripcion_problema[:150]}...\n"
            f"🏷️ *Estatus:* {status.descripcion if status else 'Asignado'}\n"
            f"👷 *Asignado a:* {usuario.nombre}\n"
            f"⏰ *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M') if reporte.timestamp else 'N/D'}\n\n"
            f"*📋 Acciones rápidas:*"
        )
        
        reply_markup = construir_botones_reporte(reporte_id, user_id=usuario.telegram_id)
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return False
        
        await bot_app.bot.send_message(
            chat_id=int(usuario.telegram_id),
            text=mensaje,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )
        
        logger.info(f"✅ Notificación enviada a {usuario.nombre} (ID: {usuario.telegram_id})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_asignacion_a_cuadrilla: {e}", exc_info=True)
        return False


# ============================================================
# 6. NOTIFICAR SUPERVISOR REVISIÓN (CON EVIDENCIAS ENLACES)
# ============================================================
async def notificar_supervisor_revision(reporte_id: int, team_id: int):
    """
    Notifica al supervisor que una cuadrilla ha terminado la reparación.
    Incluye enlaces a las evidencias y materiales.
    """
    try:
        from app.models.report import Report, Assignment
        from app.models.user import User
        from app.models.team import Team
        from app.routes.telegram_routes import get_telegram_app
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            logger.error(f"❌ Reporte {reporte_id} no encontrado")
            return False
        
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion:
            logger.error(f"❌ No hay asignación para reporte {reporte_id}")
            return False
        
        cuadrilla = Team.query.get(team_id)
        if not cuadrilla:
            logger.error(f"❌ Cuadrilla {team_id} no encontrada")
            return False
        
        supervisor = User.query.filter_by(
            area='agua',
            rol_especifico='supervisor',
            is_active=True
        ).first()
        
        if not supervisor or not supervisor.telegram_id:
            logger.warning(f"⚠️ Supervisor para agua no configurado o sin Telegram")
            return False
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return False
        
        # ============================================================
        # CONSTRUIR EVIDENCIAS DE REPARACIÓN (CON ENLACES)
        # ============================================================
        evidencias_texto = "• No hay evidencia"
        if asignacion.evidencia_cuadrilla:
            evidencias_lista = asignacion.evidencia_cuadrilla.split(',')
            evidencias_texto = ""
            for i, evidencia in enumerate(evidencias_lista, 1):
                evidencia = evidencia.strip()
                if evidencia:
                    enlace, _ = construir_enlace_evidencia(evidencia, f"evidencia_{i}")
                    # Detectar tipo de archivo para el icono
                    ext = evidencia.split('.')[-1].lower() if '.' in evidencia else ''
                    icono = "📷" if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'] else "🎬" if ext in ['mp4', 'mov', 'avi', 'mkv'] else "📎"
                    evidencias_texto += f"• {icono} {enlace}\n"
        
        # ============================================================
        # CONSTRUIR MATERIALES UTILIZADOS (CON ENLACE)
        # ============================================================
        materiales_texto = "• No especificado"
        if asignacion.materiales_utilizados:
            materiales = asignacion.materiales_utilizados.strip()
            if '.' in materiales or '/' in materiales:
                # Es un archivo
                enlace, _ = construir_enlace_evidencia(materiales, "material")
                # Detectar tipo
                ext = materiales.split('.')[-1].lower() if '.' in materiales else ''
                icono = "📷" if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'] else "📎"
                materiales_texto = f"{icono} {enlace}"
            else:
                # Es texto
                materiales_texto = f"📝 {materiales}"
        
        # ============================================================
        # CONSTRUIR MENSAJE COMPLETO
        # ============================================================
        mensaje = f"""
🔍 *REPARACIÓN PARA REVISIÓN - Reporte #{reporte.id}*

📍 *UBICACIÓN:*
{reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}
{reporte.localidad.nombre if reporte.localidad else 'N/D'}

👤 *REPORTANTE:*
{reporte.reportante} (📱 {reporte.telefono})

🔧 *PROBLEMA:*
{reporte.tipo} - {reporte.subtipo}
{reporte.descripcion_problema[:150]}{'...' if len(reporte.descripcion_problema) > 150 else ''}

👷 *CUADRILLA RESPONSABLE:*
{cuadrilla.nombre}

📸 *EVIDENCIA DE REPARACIÓN:*
{evidencias_texto}

📦 *MATERIALES UTILIZADOS:*
{materiales_texto}

💬 *COMENTARIOS DE LA CUADRILLA:*
{asignacion.observaciones or 'Sin comentarios'}

⏰ *FECHA REPARACIÓN:*
{asignacion.timestamp.strftime('%d/%m/%Y %H:%M') if asignacion.timestamp else 'N/D'}

*📋 ACCIONES DISPONIBLES:*
• ✅ *Validar:* Aceptar reparación y finalizar reporte
• ❌ *Rechazar:* Devolver a cuadrilla con comentario
"""
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Validar reparación", callback_data=f"super_validar_{reporte.id}"),
                InlineKeyboardButton("❌ Rechazar", callback_data=f"super_rechazar_{reporte.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot_app.bot.send_message(
            chat_id=int(supervisor.telegram_id),
            text=mensaje,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )
        
        logger.info(f"✅ Supervisor {supervisor.nombre} notificado sobre reparación terminada")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_supervisor_revision: {e}", exc_info=True)
        return False


# ============================================================
# 7. NOTIFICAR DIRECTOR DE ÁREA NO-AGUA PARA VALIDACIÓN
# ============================================================
async def notificar_director_validacion(reporte_id: int, team_id: int):
    """
    Notifica al director del área (no-agua) que una cuadrilla ha terminado reparación.
    Incluye enlaces a las evidencias y materiales.
    """
    try:
        from app.models.report import Report, Assignment
        from app.models.user import User
        from app.models.team import Team
        from app.routes.telegram_routes import get_telegram_app
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            logger.error(f"❌ Reporte {reporte_id} no encontrado")
            return False
        
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion:
            logger.error(f"❌ No hay asignación para reporte {reporte_id}")
            return False
        
        cuadrilla = Team.query.get(team_id)
        if not cuadrilla or not cuadrilla.area:
            logger.error(f"❌ Cuadrilla {team_id} sin área")
            return False
        
        director = User.query.filter_by(
            area=cuadrilla.area,
            rol_especifico='director',
            is_active=True
        ).first()
        
        if not director or not director.telegram_id:
            logger.warning(f"⚠️ Director para {cuadrilla.area} no configurado")
            return False
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return False
        
        # ============================================================
        # CONSTRUIR EVIDENCIAS DE REPARACIÓN (CON ENLACES)
        # ============================================================
        evidencias_texto = "• No hay evidencia"
        if asignacion.evidencia_cuadrilla:
            evidencias_lista = asignacion.evidencia_cuadrilla.split(',')
            evidencias_texto = ""
            for i, evidencia in enumerate(evidencias_lista, 1):
                evidencia = evidencia.strip()
                if evidencia:
                    enlace, _ = construir_enlace_evidencia(evidencia, f"evidencia_{i}")
                    ext = evidencia.split('.')[-1].lower() if '.' in evidencia else ''
                    icono = "📷" if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'] else "🎬" if ext in ['mp4', 'mov', 'avi', 'mkv'] else "📎"
                    evidencias_texto += f"• {icono} {enlace}\n"
        
        # ============================================================
        # CONSTRUIR MATERIALES UTILIZADOS (CON ENLACE)
        # ============================================================
        materiales_texto = "• No especificado"
        if asignacion.materiales_utilizados:
            materiales = asignacion.materiales_utilizados.strip()
            if '.' in materiales or '/' in materiales:
                enlace, _ = construir_enlace_evidencia(materiales, "material")
                ext = materiales.split('.')[-1].lower() if '.' in materiales else ''
                icono = "📷" if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'] else "📎"
                materiales_texto = f"{icono} {enlace}"
            else:
                materiales_texto = f"📝 {materiales}"
        
        # ============================================================
        # CONSTRUIR MENSAJE COMPLETO
        # ============================================================
        mensaje = f"""
✅ *REPARACIÓN TERMINADA - ÁREA {cuadrilla.area.upper()}*

📋 *Reporte:* #{reporte.id}
📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}
👤 *Reportante:* {reporte.reportante}
🔧 *Problema:* {reporte.tipo} - {reporte.subtipo}
👷 *Cuadrilla:* {cuadrilla.nombre}

📸 *EVIDENCIA DE REPARACIÓN:*
{evidencias_texto}

📦 *MATERIALES UTILIZADOS:*
{materiales_texto}

💬 *Comentarios:* {asignacion.observaciones or 'Sin comentarios'}

⏰ *Fecha:* {asignacion.timestamp.strftime('%d/%m/%Y %H:%M') if asignacion.timestamp else 'N/D'}

*📋 VALIDAR REPARACIÓN:*
"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Validar", callback_data=f"dir_validar_{reporte.id}"),
                InlineKeyboardButton("❌ Rechazar", callback_data=f"dir_rechazar_{reporte.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot_app.bot.send_message(
            chat_id=int(director.telegram_id),
            text=mensaje,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )
        
        logger.info(f"✅ Director {director.nombre} notificado para validación de reparación")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_director_validacion: {e}", exc_info=True)
        return False


# ============================================================
# 8. FUNCIONES ADICIONALES (presidente, admin, etc.)
# ============================================================

async def notificar_presidente_reporte(reporte_id: int, motivo: str = "nuevo_reporte"):
    """Notifica al presidente sobre reportes importantes."""
    try:
        from app.models.report import Report, Localidad, Calle
        from app.models.user import User
        from app.routes.telegram_routes import get_telegram_app
        from datetime import datetime
        
        presidente = User.query.filter_by(
            rol_especifico='presidente',
            is_active=True
        ).first()
        
        if not presidente or not presidente.telegram_id:
            logger.warning("⚠️ Presidente no configurado o sin Telegram")
            return False
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            logger.error(f"❌ Reporte {reporte_id} no encontrado")
            return False
        
        localidad = Localidad.query.get(reporte.localidad_id)
        calle = Calle.query.get(reporte.calle_id)
        
        if motivo == 'nuevo_reporte':
            mensaje = f"""🏛️ *NUEVO REPORTE - PRESIDENCIA*

📋 *ID:* #{reporte.id}
👤 *Reportante:* {reporte.reportante}
📞 *Teléfono:* {reporte.telefono}
🏢 *Dependencia:* {reporte.tipo}
🔧 *Subtipo:* {reporte.subtipo}
📍 *Ubicación:* {calle.nombre if calle else 'N/D'} #{reporte.numero}, {localidad.nombre if localidad else 'N/D'}
📝 *Descripción:* {reporte.descripcion_problema[:100]}...
🕒 *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}
🔍 *Estado:* Sin asignar
"""
        elif motivo == 'reporte_urgente':
            horas = int((datetime.now() - reporte.timestamp).total_seconds() / 3600)
            mensaje = f"""🚨 *REPORTE URGENTE - ATENCIÓN INMEDIATA*

📋 *ID:* #{reporte.id}
👤 *Reportante:* {reporte.reportante}
🏢 *Área:* {reporte.tipo}
🔧 *Problema:* {reporte.subtipo}
📍 *Dirección:* {calle.nombre if calle else 'N/D'} #{reporte.numero}
🕒 *Reportado hace:* {horas} horas
"""
        else:
            mensaje = f"""📈 *REPORTE IMPORTANTE PARA REVISIÓN*

📋 *ID:* #{reporte.id}
🏢 *Departamento:* {reporte.tipo}
📍 *Zona:* {localidad.nombre if localidad else 'N/D'}
📊 *Estado:* Sin asignar
🕒 *Creado:* {reporte.timestamp.strftime('%d/%m/%Y')}
"""
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return False
        
        await bot_app.bot.send_message(
            chat_id=int(presidente.telegram_id),
            text=mensaje,
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"✅ Presidente notificado sobre reporte #{reporte_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_presidente_reporte: {e}", exc_info=True)
        return False


async def notificar_admin_vinculacion_original(usuario, telegram_user_id, telegram_username, context):
    try:
        from flask import current_app
        from app.routes.telegram_routes import get_telegram_app
        
        admin_id = current_app.config.get('TELEGRAM_ADMIN_ID')
        if not admin_id:
            logger.warning("⚠️ TELEGRAM_ADMIN_ID no configurado")
            return False
        
        mensaje = (
            f"📎 nueva vinculacion telegram\n"
            f"usuario: {usuario.nombre}\n"
            f"username: {usuario.username}\n"
            f"telegram id: {telegram_user_id}\n"
            f"telegram username: @{telegram_username or 'N/A'}\n"
            f"cuadrilla: {usuario.team.nombre if usuario.team else 'Sin asignar'}\n"
            f"fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        
        bot_app = get_telegram_app()
        if bot_app and bot_app.bot:
            await bot_app.bot.send_message(
                chat_id=int(admin_id),
                text=mensaje
            )
            logger.info(f"📤 Notificación de vinculación enviada al admin {admin_id}")
            return True
        else:
            logger.error("❌ Bot de Telegram no disponible")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error notificando admin: {e}")
        return False


def notificar_asignacion_sync(reporte_id: int, user_id: int):
    """Versión síncrona para notificar asignaciones (para admin.py)"""
    try:
        import asyncio
        from app.routes.telegram_routes import get_telegram_app
        
        async def ejecutar():
            return await notificar_asignacion_a_cuadrilla(reporte_id, user_id)
        
        bot_app = get_telegram_app()
        if bot_app and bot_app.bot:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Loop cerrado")
            except:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(ejecutar())
            logger.info(f"📤 Notificación de asignación síncrona completada: reporte {reporte_id}")
            return True
        else:
            logger.error("❌ Bot no disponible para notificación síncrona")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error en notificar_asignacion_sync: {e}")
        return False


# ============================================================
# 9. NOTIFICAR USUARIO REPORTANTE PARA VALIDACIÓN FINAL
# ============================================================
async def notificar_usuario_reporte_finalizado(reporte, asignacion, quien_valido: str = "Sistema"):
    """Notifica al usuario reportante que su reporte ha sido atendido y pide validación final."""
    try:
        from app.models.team import Team
        from app.models.status import Status
        from app.routes.telegram_routes import get_telegram_app
        
        if not reporte.telefono:
            logger.warning(f"⚠️ Reporte {reporte.id} no tiene teléfono/telegram_id")
            return False
        
        try:
            telegram_id = int(reporte.telefono)
        except:
            logger.warning(f"⚠️ Telegram ID inválido: {reporte.telefono}")
            return False
        
        cuadrilla = Team.query.get(asignacion.team_id)
        
        estado_pendiente = Status.query.filter_by(descripcion="Pendiente validación usuario").first()
        if not estado_pendiente:
            estado_pendiente = Status(descripcion="Pendiente validación usuario")
            db.session.add(estado_pendiente)
            db.session.commit()
        
        asignacion.status_id = estado_pendiente.id
        asignacion.observaciones = f"Validado por {quien_valido} el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        db.session.commit()
        
        mensaje = f"""
✅ *¡TU REPORTE HA SIDO ATENDIDO!*

📋 *Folio:* #{reporte.id}
📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}
🔧 *Problema:* {reporte.tipo} - {reporte.subtipo}
👷 *Cuadrilla:* {cuadrilla.nombre if cuadrilla else 'N/D'}

*¿La reparación fue satisfactoria?*

⚠️ Tienes 48 horas para responder. Si no respondes, se considerará aceptada automáticamente.
"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Sí, está resuelto", callback_data=f"usuario_aceptar_{reporte.id}"),
                InlineKeyboardButton("❌ No, persiste el problema", callback_data=f"usuario_rechazar_{reporte.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return False
        
        await bot_app.bot.send_message(
            chat_id=telegram_id,
            text=mensaje,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        logger.info(f"📤 Usuario notificado para validación final - Reporte #{reporte.id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_usuario_reporte_finalizado: {e}", exc_info=True)
        return False


# ============================================================
# 10. NOTIFICAR RECHAZO DEL USUARIO AL RESPONSABLE
# ============================================================
async def notificar_rechazo_usuario(reporte_id: int, usuario_id: int):
    """Notifica al responsable (Jefe Técnico o Director) que el usuario rechazó la reparación."""
    try:
        from app.models.report import Report
        from app.models.user import User
        from app.routes.telegram_routes import get_telegram_app
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            return
        
        if reporte.tipo in ["Agua potable", "Drenaje"]:
            responsable = User.query.filter_by(
                area='agua',
                rol_especifico='jefe_area_tecnica',
                is_active=True
            ).first()
        else:
            mapeo = {
                "Aseo público": "aseo",
                "Alumbrado público": "alumbrado",
                "Parques y jardines": "parques",
                "Ecología": "ecologia",
                "Seguridad pública": "seguridad",
                "Obras públicas": "obras",
                "Bomberos": "bomberos"
            }
            area = mapeo.get(reporte.tipo)
            if area:
                responsable = User.query.filter_by(
                    area=area,
                    rol_especifico='director',
                    is_active=True
                ).first()
        
        if not responsable or not responsable.telegram_id:
            logger.warning(f"⚠️ No se encontró responsable para notificar rechazo")
            return
        
        bot_app = get_telegram_app()
        if not bot_app or not bot_app.bot:
            logger.error("❌ Bot de Telegram no disponible")
            return
        
        await bot_app.bot.send_message(
            chat_id=int(responsable.telegram_id),
            text=f"🚨 *RECHAZO DE USUARIO - Reporte #{reporte.id}*\n\nEl usuario ha rechazado la reparación.\nPor favor, revisa y reasigna o toma acciones.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"📤 Responsable notificado sobre rechazo de usuario - Reporte #{reporte.id}")
        
    except Exception as e:
        logger.error(f"❌ Error en notificar_rechazo_usuario: {e}", exc_info=True)
