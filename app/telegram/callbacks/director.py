# app/telegram/callbacks/director.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data
from app.services.db_manager import DatabaseManager
from app.telegram.common.keyboards import construir_botones_reporte
from app.models.report import Report, Assignment, Localidad, Calle
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============================================================
# CALLBACKS DE DIRECTORES
# ============================================================

async def director_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja acciones de directores Y jefes de área"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    
    if not callback_data.startswith('dir_'):
        return
    
    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
        if not usuario:
            await query.edit_message_text("❌ No autorizado. Usuario no encontrado.")
            return
        
        # Validar rol
        roles_permitidos = ['director', 'jefe_area', 'jefe_area_tecnica', 'jefe_area_comercial']
        tiene_rol = (
            usuario.role in roles_permitidos or 
            usuario.rol_especifico in roles_permitidos or
            (usuario.rol_especifico and 'jefe_area' in usuario.rol_especifico)
        )
        if not tiene_rol:
            await query.edit_message_text("❌ No autorizado. Solo directores y jefes de área pueden realizar esta acción.")
            return
        
        # Procesar acción
        if callback_data.startswith('dir_asignar_'):
            reporte_id = int(callback_data.split('_')[2])
            await mostrar_cuadrillas_para_asignar(query, reporte_id, usuario)
        
        elif callback_data.startswith('dir_detalle_'):
            reporte_id = int(callback_data.split('_')[2])
            await mostrar_detalle_reporte_director(query, reporte_id, usuario)
        
        elif callback_data.startswith('dir_asignarc_'):
            partes = callback_data.split('_')
            reporte_id = int(partes[2])
            cuadrilla_id = int(partes[3])
            await asignar_a_cuadrilla_director(query, reporte_id, cuadrilla_id, usuario)
        
        elif callback_data.startswith('dir_volver_'):
            reporte_id = int(callback_data.split('_')[2])
            await volver_a_resumen(query, reporte_id, usuario)
        
        elif callback_data.startswith('dir_evidencia_'):
            reporte_id = int(callback_data.split('_')[2])
            await manejar_evidencia_director(query, reporte_id, usuario)
        
        else:
            await query.answer("⚠️ Acción no reconocida", show_alert=True)


# ============================================================
# MOSTRAR CUADRILLAS PARA ASIGNAR (CORREGIDO)
# ============================================================

async def mostrar_cuadrillas_para_asignar(query, reporte_id: int, usuario: User):
    """Muestra las cuadrillas disponibles para asignar - VERSIÓN CORREGIDA"""
    try:
        app = DatabaseManager.get_app()
        
        with app.app_context():
            from app.models.report import Report
            from app.models.team import Team
            from app.models.user import User
            
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return
            
            # Determinar área según el usuario o el reporte
            area_a_buscar = None
            
            # 1. Usar área del usuario si existe
            if usuario.area and usuario.area.strip():
                area_a_buscar = usuario.area
                logger.info(f"📌 Usando área del usuario: {area_a_buscar}")
            else:
                # 2. Usar el tipo de reporte
                mapeo_tipo_a_area = {
                    "Agua potable": "agua",
                    "Drenaje": "agua",
                    "Aseo público": "aseo",
                    "Alumbrado público": "alumbrado", 
                    "Parques y jardines": "parques",
                    "Ecología": "ecologia",
                    "Seguridad pública": "seguridad",
                    "Obras públicas": "obra",
                    "Bomberos": "bomberos"
                }
                area_a_buscar = mapeo_tipo_a_area.get(reporte.tipo, "general")
                logger.info(f"📌 Determinando área por tipo de reporte: {reporte.tipo} -> {area_a_buscar}")
            
            if not area_a_buscar:
                area_a_buscar = "general"
                logger.warning(f"⚠️ No se pudo determinar área, usando 'general'")
            
            # Buscar cuadrillas del área
            cuadrillas = Team.query.filter(
                Team.area == area_a_buscar,
                Team.nombre != "Sin asignar"
            ).order_by(Team.nombre).all()
            
            # Si no hay cuadrillas del área, mostrar todas excepto "Sin asignar"
            if not cuadrillas:
                logger.warning(f"⚠️ No hay cuadrillas para área {area_a_buscar}, mostrando todas")
                cuadrillas = Team.query.filter(
                    Team.nombre != "Sin asignar"
                ).order_by(Team.nombre).all()
            
            if not cuadrillas:
                await query.edit_message_text("❌ No hay cuadrillas disponibles en este momento.")
                return
            
            # Crear teclado con cuadrillas
            keyboard = []
            for cuadrilla in cuadrillas:
                # Contar usuarios en la cuadrilla para mostrar info
                usuarios_count = User.query.filter_by(team_id=cuadrilla.id).count()
                texto_boton = f"👷 {cuadrilla.nombre}"
                if usuarios_count > 0:
                    texto_boton += f" ({usuarios_count})"
                keyboard.append([
                    InlineKeyboardButton(
                        texto_boton,
                        callback_data=f"dir_asignarc_{reporte_id}_{cuadrilla.id}"
                    )
                ])
            
            # Agregar opción de volver
            keyboard.append([
                InlineKeyboardButton("↩️ Volver", callback_data=f"dir_volver_{reporte_id}")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Construir mensaje informativo
            area_display = area_a_buscar.replace('_', ' ').title()
            
            mensaje = (
                f"👷 *ASIGNAR REPORTE #{reporte_id}*\n\n"
                f"*Área:* {area_display}\n"
                f"*Problema:* {reporte.subtipo}\n"
                f"*Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n\n"
                f"*Selecciona la cuadrilla:*\n"
                f"({len(cuadrillas)} cuadrillas disponibles)"
            )
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            logger.info(f"✅ Mostrando {len(cuadrillas)} cuadrillas para área {area_a_buscar}")
            
    except Exception as e:
        logger.error(f"❌ Error mostrando cuadrillas: {e}")
        import traceback
        logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
        await query.edit_message_text("❌ Error al cargar cuadrillas.")


# ============================================================
# OTRAS FUNCIONES DE DIRECTOR (RESTO SIN CAMBIOS)
# ============================================================

async def mostrar_detalle_reporte_director(query, reporte_id: int, director: User):
    """Muestra detalles completos del reporte al director"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return
            
            localidad = Localidad.query.get(reporte.localidad_id)
            calle = Calle.query.get(reporte.calle_id)
            
            mensaje = (
                f"📋 *DETALLES COMPLETOS - Reporte #{reporte.id}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔧 *Tipo:* {reporte.tipo}\n"
                f"📝 *Subtipo:* {reporte.subtipo}\n"
                f"📍 *Dirección:* {calle.nombre if calle else 'N/D'} #{reporte.numero}\n"
                f"🏘️ *Localidad:* {localidad.nombre if localidad else 'N/D'}\n"
                f"🚧 *Entre calles:* {reporte.entre_calles or 'No especificado'}\n"
                f"👤 *Reportante:* {reporte.reportante}\n"
                f"📱 *Teléfono:* {reporte.telefono}\n"
                f"💳 *Cuenta:* {reporte.numero_cuenta or 'No aplica'}\n\n"
                f"📄 *Descripción del problema:*\n{reporte.descripcion_problema}\n\n"
                f"📎 *Evidencia:* {'✅ Adjunta' if reporte.evidencia else '❌ No adjunta'}\n"
                f"⏰ *Fecha registro:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("👷 Asignar a Cuadrilla", callback_data=f"dir_asignar_{reporte.id}")],
                [InlineKeyboardButton("↩️ Volver al Resumen", callback_data=f"dir_volver_{reporte.id}")]
            ]
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        logger.error(f"❌ Error mostrando detalles al director: {e}")
        await query.edit_message_text("❌ Error al cargar detalles.")


async def volver_a_resumen(query, reporte_id: int, director: User):
    """Vuelve al mensaje de resumen del reporte"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return
            
            localidad = Localidad.query.get(reporte.localidad_id)
            calle = Calle.query.get(reporte.calle_id)
            
            mensaje = (
                f"🚨 *NUEVO REPORTE - {reporte.tipo.upper()}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📋 *Folio:* #{reporte.id}\n"
                f"📍 *Ubicación:* {calle.nombre if calle else 'N/D'} #{reporte.numero}, "
                f"{localidad.nombre if localidad else 'N/D'}\n"
                f"📞 *Reportante:* {reporte.reportante}\n"
                f"🔧 *Tipo:* {reporte.tipo}\n"
                f"📝 *Subtipo:* {reporte.subtipo}\n"
                f"📄 *Descripción:*\n{reporte.descripcion_problema[:150]}"
                f"{'...' if len(reporte.descripcion_problema) > 150 else ''}\n\n"
                f"⏰ *Fecha:* {reporte.timestamp.strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*👷 ACCIONES RÁPIDAS:*"
            )
            
            keyboard = [
                [InlineKeyboardButton("👷 Asignar a Cuadrilla", callback_data=f"dir_asignar_{reporte.id}")],
                [InlineKeyboardButton("📋 Ver Detalles", callback_data=f"dir_detalle_{reporte.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"❌ Error volviendo al resumen: {e}")
        await query.edit_message_text("❌ Error al cargar el resumen.")


async def asignar_a_cuadrilla_director(query, reporte_id: int, cuadrilla_id: int, usuario: User):
    """Asigna un reporte a una cuadrilla desde director/jefe"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            cuadrilla = Team.query.get(cuadrilla_id)
            if not reporte or not cuadrilla:
                await query.edit_message_text("❌ Datos no válidos.")
                return
            
            quien_asigna = usuario.nombre if usuario else "Sistema"
            
            status_asignado = Status.query.filter_by(descripcion="Asignado").first()
            if not status_asignado:
                status_asignado = Status(descripcion="Asignado")
                db.session.add(status_asignado)
                db.session.commit()
            
            nueva_asignacion = Assignment(
                report_id=reporte_id,
                team_id=cuadrilla_id,
                status_id=status_asignado.id,
                timestamp=datetime.utcnow(),
                observaciones=f"Asignado por {quien_asigna} via Telegram"
            )
            db.session.add(nueva_asignacion)
            db.session.commit()
            
            # Notificar a la cuadrilla
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id).all()
            notificaciones_enviadas = 0
            for usuario_cuadrilla in usuarios_cuadrilla:
                if usuario_cuadrilla.telegram_id:
                    try:
                        from app.services.notification_service import notificar_asignacion_a_cuadrilla
                        await notificar_asignacion_a_cuadrilla(reporte_id, usuario_cuadrilla.id)
                        notificaciones_enviadas += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario_cuadrilla.nombre}: {e}")
            
            mensaje_confirmacion = (
                f"✅ *REPORTE ASIGNADO CORRECTAMENTE*\n\n"
                f"📋 *Folio:* #{reporte.id}\n"
                f"👷 *Cuadrilla asignada:* {cuadrilla.nombre}\n"
                f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
                f"📞 *Reportante:* {reporte.reportante}\n"
                f"🔧 *Problema:* {reporte.subtipo}\n\n"
                f"*📤 Notificaciones enviadas:* {notificaciones_enviadas} de {len(usuarios_cuadrilla)}\n\n"
                f"*Asignado por:* {quien_asigna}\n"
                f"*Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            
            await query.edit_message_text(
                text=mensaje_confirmacion,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ {quien_asigna} asignó reporte #{reporte_id} a cuadrilla {cuadrilla.nombre}")
            
    except Exception as e:
        logger.error(f"❌ Error asignando reporte: {e}")
        await query.edit_message_text("❌ Error al asignar reporte.")


async def manejar_evidencia_director(query, reporte_id: int, director: User):
    """Maneja el botón de evidencia para director - CORREGIDO (mensaje nuevo + botón volver)"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if not reporte or not reporte.evidencia:
                await query.answer("❌ No hay evidencia disponible", show_alert=True)
                return
            
            # ✅ EXTRAER SOLO EL NOMBRE DEL ARCHIVO
            import os
            nombre_archivo = os.path.basename(reporte.evidencia)
            
            server_url = app.config.get('SERVER_URL', 'http://localhost:5000')
            evidencia_url = f"{server_url}/admin/uploads/{reporte.evidencia}"
            
            # ✅ ENVIAR MENSAJE NUEVO (NO editar el original)
            mensaje = (
                f"📎 *Evidencia del reporte #{reporte.id}*\n\n"
                f"📄 *Archivo:* `{nombre_archivo}`\n\n"
                f"🔗 [Ver evidencia]({evidencia_url})"
            )
            
            # ✅ BOTÓN PARA VOLVER AL MENSAJE ORIGINAL
            keyboard = [[
                InlineKeyboardButton("↩️ Volver al reporte", callback_data=f"dir_volver_{reporte.id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Usar context.bot.send_message (o query.message.reply_text)
            await query.message.reply_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=False
            )
            
            await query.answer("📎 Evidencia enviada", show_alert=False)
            logger.info(f"📎 Evidencia enviada para reporte {reporte_id} (solo nombre: {nombre_archivo})")
            
    except Exception as e:
        logger.error(f"❌ Error en evidencia director: {e}")
        await query.answer("❌ Error al obtener evidencia", show_alert=True)


# ============================================================
# FUNCIÓN AUXILIAR PARA COMENTARIO DE RECHAZO
# ============================================================

async def manejar_comentario_rechazo_director(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comentarios de rechazo del director (desde router)"""
    user_id = update.effective_user.id
    if user_id not in user_data or not user_data[user_id].get('modo_comentario_rechazo'):
        return
    
    comentario = update.message.text
    reporte_id = user_data[user_id]['reporte_id']
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            if not reporte or not asignacion:
                await update.message.reply_text("❌ Reporte o asignación no encontrada.")
                return
            
            cuadrilla = Team.query.get(asignacion.team_id)
            usuario_director = User.query.filter_by(telegram_id=user_id).first()
            
            estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
            if not estado_en_proceso:
                estado_en_proceso = Status(descripcion="En proceso")
                db.session.add(estado_en_proceso)
                db.session.commit()
            
            asignacion.status_id = estado_en_proceso.id
            asignacion.observaciones = (
                f"{asignacion.observaciones or ''}\n\n"
                f"❌ RECHAZADO POR DIRECTOR:\n"
                f"• Director: {usuario_director.nombre if usuario_director else 'N/D'}\n"
                f"• Comentario: {comentario}\n"
                f"• Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            db.session.commit()
            
            # Notificar a la cuadrilla
            if cuadrilla:
                usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla.id).all()
                for usuario_cuadrilla in usuarios_cuadrilla:
                    if usuario_cuadrilla.telegram_id:
                        try:
                            await context.bot.send_message(
                                chat_id=usuario_cuadrilla.telegram_id,
                                text=f"❌ *REPARACIÓN RECHAZADA - REQUIERE CORRECCIÓN*\n\n"
                                     f"📋 *Reporte:* #{reporte_id}\n"
                                     f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
                                     f"🔧 *Problema:* {reporte.tipo} - {reporte.subtipo}\n"
                                     f"👨‍💼 *Director:* {usuario_director.nombre if usuario_director else 'N/D'}\n\n"
                                     f"📝 *COMENTARIO DEL DIRECTOR:*\n_{comentario}_\n\n"
                                     f"*🚀 ACCIÓN REQUERIDA:* Corregir y volver a subir evidencia.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception as e:
                            logger.error(f"❌ Error notificando cuadrilla: {e}")
            
            await update.message.reply_text(
                f"✅ *Comentario guardado y enviado*\n\n"
                f"📋 *Reporte:* #{reporte_id}\n"
                f"👷 *Cuadrilla notificada:* {cuadrilla.nombre if cuadrilla else 'N/D'}\n"
                f"📝 *Tu comentario:*\n_{comentario[:100]}{'...' if len(comentario) > 100 else ''}_",
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"❌ Error en manejar_comentario_rechazo_director: {e}")
        await update.message.reply_text("❌ Error al procesar el comentario.")
    finally:
        if user_id in user_data:
            user_data[user_id].pop('modo_comentario_rechazo', None)
            user_data[user_id].pop('reporte_id', None)
