# app/services/notification_service.py
import logging
from datetime import datetime
from app.services.db_manager import DatabaseManager
from app.telegram.keyboards import construir_botones_reporte
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

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
        app = DatabaseManager.get_app()
        with app.app_context():
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
                    # Verificar si es la misma persona que el jefe técnico
                    if jefe_tecnico and jefe_tecnico.id == director_agua.id:
                        logger.info("ℹ️ Misma persona: Director y Jefe Técnico")
                    else:
                        responsables.append({
                            'usuario': director_agua,
                            'tipo_mensaje': 'informativo_simple',
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
        logger.error(f"❌ Error obteniendo responsables: {e}")
        return []


# ============================================================
# 2. NOTIFICAR NUEVO REPORTE
# ============================================================

async def notificar_director_nuevo_reporte(reporte_id: int, telegram_id: int, tipo_reporte: str):
    """
    Notifica a responsables según el tipo de reporte.
    - Agua/Drenaje: Jefe Técnico (completo) + Director (informativo)
    - Otros: Director correspondiente (completo)
    """
    try:
        app = DatabaseManager.get_app()
        
        with app.app_context():
            from app.models.report import Report, Localidad, Calle
            from app.models.user import User
            from app.routes.telegram_routes import get_telegram_app
            
            # Obtener reporte
            reporte = Report.query.get(reporte_id)
            if not reporte:
                logger.error(f"❌ Reporte {reporte_id} no encontrado")
                return False
            
            localidad = Localidad.query.get(reporte.localidad_id)
            calle = Calle.query.get(reporte.calle_id)
            
            # Obtener responsables
            responsables = obtener_directores_por_tipo_reporte(tipo_reporte)
            
            if not responsables:
                logger.warning(f"⚠️ No hay responsables para {tipo_reporte}")
                return False
            
            bot_app = get_telegram_app()
            notificaciones_enviadas = 0
            
            for responsable in responsables:
                usuario = responsable['usuario']
                if not usuario or not usuario.telegram_id:
                    continue
                
                try:
                    telegram_id_destino = int(usuario.telegram_id)
                except:
                    logger.warning(f"⚠️ Telegram ID inválido para {usuario.nombre}")
                    continue
                
                # Construir mensaje según tipo
                if responsable['tipo_mensaje'] == 'completo_con_botones':
                    mensaje = await construir_mensaje_completo(reporte, localidad, calle)
                    reply_markup = construir_botones_reporte(reporte.id, es_director=True)
                else:
                    # Mensaje informativo (solo botón "Ver Detalles")
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


async def construir_mensaje_completo(reporte, localidad, calle):
    """Construye mensaje completo con botones de asignación"""
    # Verificar evidencia
    tiene_evidencia = False
    icono_evidencia = "📎"
    texto_evidencia = "No adjuntada"
    
    if reporte.evidencia:
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        evidencia_completa = reporte.evidencia
        evidencia_path = os.path.join(upload_folder, evidencia_completa)
        
        if os.path.exists(evidencia_path):
            tiene_evidencia = True
            evidencia_lower = evidencia_completa.lower()
            if evidencia_lower.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                icono_evidencia = "🎬"
                texto_evidencia = "Video adjunto"
            elif evidencia_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                icono_evidencia = "🖼️"
                texto_evidencia = "Imagen adjunta"
            else:
                icono_evidencia = "📎"
                texto_evidencia = "Archivo adjunto"
    
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
    
    if tiene_evidencia:
        mensaje += f"{icono_evidencia} *Evidencia:* {texto_evidencia}\n\n"
    
    mensaje += (
        f"⏰ *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
        f"*👷 ACCIONES RÁPIDAS:*"
    )
    
    return mensaje


# ============================================================
# 3. NOTIFICAR ASIGNACIÓN A CUADRILLA
# ============================================================

async def notificar_asignacion_a_cuadrilla(reporte_id: int, user_id_asignado: int):
    """
    Notifica a una cuadrilla que se le ha asignado un reporte.
    """
    try:
        app = DatabaseManager.get_app()
        
        with app.app_context():
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
            
            # Obtener asignación
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            status = Status.query.get(asignacion.status_id) if asignacion else None
            
            # Construir mensaje
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
            
            reply_markup = construir_botones_reporte(reporte_id)
            
            bot_app = get_telegram_app()
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
# 4. NOTIFICAR ADMIN VINCULACIÓN (YA LA TIENES)
# ============================================================

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


# ============================================================
# 5. FUNCIÓN SÍNCRONA PARA ADMIN (compatibilidad)
# ============================================================

def notificar_asignacion_sync(reporte_id: int, user_id: int):
    """Versión síncrona para notificar asignaciones (para admin.py)"""
    try:
        import asyncio
        from app.routes.telegram_routes import get_telegram_app
        
        async def ejecutar():
            return await notificar_asignacion_a_cuadrilla(reporte_id, user_id)
        
        # Ejecutar en el loop existente
        bot_app = get_telegram_app()
        if bot_app and bot_app.bot:
            # Si hay loop, usar run_until_complete
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
