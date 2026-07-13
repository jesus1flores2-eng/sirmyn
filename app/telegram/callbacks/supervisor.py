"""
Maneja los callbacks del supervisor de agua (validación de reparaciones)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from datetime import datetime
from app.telegram.utils import limpiar_estado
from telegram import ReplyKeyboardRemove
import logging

logger = logging.getLogger(__name__)

async def supervisor_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del supervisor (validar/rechazar reparación)"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    
    if not callback_data.startswith('super_'):
        return
    
    # ⭐ IGNORAR callbacks que no sean validar o rechazar
    if not callback_data.startswith(('super_validar_', 'super_rechazar_')):
        logger.info(f"⏩ Callback {callback_data} ignorado por supervisor_callback_handler (va a otro handler)")
        return
    
    partes = callback_data.split('_')
    if len(partes) < 3:
        await query.answer("❌ Formato inválido", show_alert=True)
        return
    
    accion = partes[1]  # 'validar' o 'rechazar'
    reporte_id = int(partes[2])
    
    app = DatabaseManager.get_app()
    with app.app_context():
        # Verificar que el usuario sea supervisor
        usuario = User.query.filter_by(
            telegram_id=str(query.from_user.id),
            rol_especifico='supervisor',
            is_active=True
        ).first()
        
        if not usuario:
            await query.edit_message_text("❌ No autorizado. Solo supervisores pueden realizar esta acción.")
            return
        
        reporte = Report.query.get(reporte_id)
        if not reporte:
            await query.edit_message_text("❌ Reporte no encontrado.")
            return
        
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion:
            await query.edit_message_text("❌ No hay asignación para este reporte.")
            return
        
        cuadrilla = Team.query.get(asignacion.team_id)
        
        # ============================================================
        # ACCIÓN: VALIDAR
        # ============================================================
        if accion == 'validar':
            # Cambiar estado a "Finalizado"
            estado_finalizado = Status.query.filter_by(descripcion="Finalizado").first()
            if not estado_finalizado:
                estado_finalizado = Status(descripcion="Finalizado")
                db.session.add(estado_finalizado)
                db.session.commit()
            
            asignacion.status_id = estado_finalizado.id
            asignacion.observaciones = f"Validado por supervisor {usuario.nombre} el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
            
            # Actualizar mensaje del supervisor
            mensaje_original = query.message.text
            if "📋 ACCIONES DISPONIBLES:" in mensaje_original:
                mensaje_original = mensaje_original.split("📋 ACCIONES DISPONIBLES:")[0].strip()
            
            nuevo_mensaje = mensaje_original + f"\n\n✅ *VALIDADO POR SUPERVISOR*\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n👷 Cuadrilla: {cuadrilla.nombre if cuadrilla else 'N/D'}\n🏷️ Estado: Finalizado ✓"
            
            await query.edit_message_text(
                text=nuevo_mensaje,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Notificar al usuario reportante para validación final
            from app.services.notification_service import notificar_usuario_reporte_finalizado
            await notificar_usuario_reporte_finalizado(reporte, asignacion, "supervisor")
            
            logger.info(f"✅ Supervisor {usuario.nombre} validó reporte #{reporte_id}")
            await query.answer("✅ Reparación validada", show_alert=False)
        
        # ============================================================
        # ACCIÓN: RECHAZAR
        # ============================================================
        elif accion == 'rechazar':
            # ⭐ GUARDAR ESTADO PARA ESPERAR MOTIVO
            user_data[query.from_user.id] = {
                'modo_esperando_motivo_rechazo': True,
                'reporte_id': reporte_id,
                'cuadrilla_id': asignacion.team_id,
                'cuadrilla_nombre': cuadrilla.nombre if cuadrilla else 'Cuadrilla desconocida'
            }
            
            # ⭐ PEDIR MOTIVO AL SUPERVISOR
            await query.edit_message_text(
                text=f"❌ *RECHAZO DE REPARACIÓN - Reporte #{reporte_id}*\n\n"
                     f"Escribe el *motivo del rechazo*:\n"
                     f"(Ej: 'La reparación no cumple con los estándares de calidad')\n\n"
                     f"📌 *El reporte volverá a estado 'En proceso' para que la cuadrilla corrija.*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=None
            )
            
            logger.info(f"❌ Supervisor {usuario.nombre} inició rechazo para reporte #{reporte_id}")
            await query.answer("⚠️ Escribe el motivo del rechazo", show_alert=False)


async def rechazo_opciones_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las opciones de rechazo del supervisor (reasignar, admin, devolver)"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    
    if not callback_data.startswith('rechazar_'):
        return
    
    partes = callback_data.split('_')
    if len(partes) < 3:
        await query.answer("❌ Formato inválido", show_alert=True)
        return
    
    sub_accion = partes[1]  # 'rea', 'admin', 'misma', 'cancel'
    reporte_id = int(partes[2])
    
    app = DatabaseManager.get_app()
    with app.app_context():
        reporte = Report.query.get(reporte_id)
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not reporte or not asignacion:
            await query.edit_message_text("❌ Reporte o asignación no encontrada.")
            return
        
        # ============================================================
        # OPCIÓN: CANCELAR
        # ============================================================
        if sub_accion == 'cancel':
            # Volver al estado anterior
            keyboard = [
                [
                    InlineKeyboardButton("✅ Validar reparación", callback_data=f"super_validar_{reporte_id}"),
                    InlineKeyboardButton("❌ Rechazar", callback_data=f"super_rechazar_{reporte_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            mensaje_original = query.message.text
            if "❌ REPARACIÓN RECHAZADA" in mensaje_original:
                mensaje_original = mensaje_original.split("❌ REPARACIÓN RECHAZADA")[0].strip()
            
            await query.edit_message_text(
                text=mensaje_original,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
        
        # ============================================================
        # OPCIÓN: REASIGNAR AUTOMÁTICAMENTE
        # ============================================================
        elif sub_accion == 'rea':
            # Buscar otra cuadrilla del mismo departamento
            cuadrilla_actual = Team.query.get(asignacion.team_id)
            if not cuadrilla_actual or not cuadrilla_actual.area:
                await query.edit_message_text("❌ No se pudo determinar el departamento.")
                return
            
            otras_cuadrillas = Team.query.filter(
                Team.area == cuadrilla_actual.area,
                Team.id != asignacion.team_id,
                Team.nombre != "Sin asignar"
            ).all()
            
            if not otras_cuadrillas:
                # Si no hay, asignar a "Sin asignar"
                cuadrilla_sin = Team.query.filter_by(nombre="Sin asignar").first()
                if cuadrilla_sin:
                    await realizar_reasignacion(reporte_id, asignacion, cuadrilla_sin.id, "No hay otras cuadrillas disponibles")
                    await query.edit_message_text(
                        f"🔄 *Reasignado a 'Sin asignar'*\n\nEl reporte #{reporte_id} ha sido reasignado a la cuadrilla 'Sin asignar'.\nEstado: Sin asignar."
                    )
                else:
                    await query.edit_message_text("❌ No hay cuadrillas disponibles para reasignación.")
                return
            
            # Crear teclado con las cuadrillas disponibles
            keyboard = []
            for cuad in otras_cuadrillas:
                keyboard.append([
                    InlineKeyboardButton(f"👷 {cuad.nombre}", callback_data=f"reasignar_{reporte_id}_{cuad.id}")
                ])
            
            keyboard.append([
                InlineKeyboardButton("↩️ Cancelar", callback_data=f"rechazar_cancel_{reporte_id}")
            ])
            
            await query.edit_message_text(
                text=f"👷 *Selecciona una cuadrilla para reasignar el reporte #{reporte_id}:*",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        # ============================================================
        # OPCIÓN: ENVIAR A ADMINISTRADOR
        # ============================================================
        elif sub_accion == 'admin':
            # Cambiar estado a "Revisión administrador"
            estado_revision_admin = Status.query.filter_by(descripcion="Revisión administrador").first()
            if not estado_revision_admin:
                estado_revision_admin = Status(descripcion="Revisión administrador")
                db.session.add(estado_revision_admin)
                db.session.commit()
            
            asignacion.status_id = estado_revision_admin.id
            asignacion.observaciones = f"Enviado a administrador por supervisor {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
            
            # Notificar al administrador
            from flask import current_app
            admin_id = current_app.config.get('TELEGRAM_ADMIN_ID')
            if admin_id:
                from app.routes.telegram_routes import get_telegram_app
                bot_app = get_telegram_app()
                await bot_app.bot.send_message(
                    chat_id=int(admin_id),
                    text=f"⚠️ *Reporte #{reporte_id} enviado a revisión*\n\nMotivo: Rechazado por supervisor.\nRequiere reasignación manual.",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await query.edit_message_text(
                f"📤 *Enviado a administrador*\n\nEl reporte #{reporte_id} ha sido enviado para revisión y reasignación manual."
            )
        
        # ============================================================
        # OPCIÓN: DEVOLVER A MISMA CUADRILLA
        # ============================================================
        elif sub_accion == 'misma':
            # Cambiar estado a "En proceso"
            estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
            if not estado_en_proceso:
                estado_en_proceso = Status(descripcion="En proceso")
                db.session.add(estado_en_proceso)
                db.session.commit()
            
            asignacion.status_id = estado_en_proceso.id
            asignacion.observaciones = f"Devuelto a misma cuadrilla por supervisor {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
            
            # Notificar a la cuadrilla
            if asignacion.team_id:
                usuarios_cuadrilla = User.query.filter_by(team_id=asignacion.team_id).all()
                for usuario in usuarios_cuadrilla:
                    if usuario.telegram_id:
                        from app.routes.telegram_routes import get_telegram_app
                        bot_app = get_telegram_app()
                        await bot_app.bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=f"🔄 *Reparación rechazada - Requiere corrección*\n\nReporte #{reporte_id}\nMotivo: Rechazado por supervisor.\nPor favor, corrige el trabajo y vuelve a subir evidencia.",
                            parse_mode=ParseMode.MARKDOWN
                        )
            
            await query.edit_message_text(
                f"🔄 *Devuelto a misma cuadrilla*\n\nEl reporte #{reporte_id} ha sido devuelto a la cuadrilla para corrección."
            )


async def realizar_reasignacion(reporte_id, asignacion_actual, nueva_cuadrilla_id, motivo):
    """Función auxiliar para reasignar un reporte"""
    try:
        from app.models.report import Assignment
        from app.models.status import Status
        from app.extensions import db
        
        estado_asignado = Status.query.filter_by(descripcion="Asignado").first()
        if not estado_asignado:
            estado_asignado = Status(descripcion="Asignado")
            db.session.add(estado_asignado)
            db.session.commit()
        
        nueva_asignacion = Assignment(
            report_id=reporte_id,
            team_id=nueva_cuadrilla_id,
            status_id=estado_asignado.id,
            timestamp=datetime.utcnow(),
            observaciones=f"Reasignado automáticamente: {motivo}"
        )
        db.session.add(nueva_asignacion)
        
        # Cambiar estado de la asignación anterior a "Reasignado"
        estado_reasignado = Status.query.filter_by(descripcion="Reasignado").first()
        if estado_reasignado:
            asignacion_actual.status_id = estado_reasignado.id
            asignacion_actual.observaciones = f"Reasignado a {nueva_cuadrilla_id} el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        
        db.session.commit()
        
        # Notificar a la nueva cuadrilla
        from app.services.notification_service import notificar_asignacion_a_cuadrilla
        usuarios_nueva = User.query.filter_by(team_id=nueva_cuadrilla_id).all()
        for usuario in usuarios_nueva:
            if usuario.telegram_id:
                await notificar_asignacion_a_cuadrilla(reporte_id, usuario.id)
        
        logger.info(f"✅ Reporte {reporte_id} reasignado a cuadrilla {nueva_cuadrilla_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error en reasignación: {e}")
        return False

# ============================================================
# SUPERVISOR CONFIRMA RECEPCIÓN DE SOLICITUD DE APOYO
# ============================================================

async def apoyo_confirmar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja cuando el supervisor presiona "✅ Confirmar recepción" en una solicitud de apoyo.
    Actualiza el mensaje pero MANTIENE el botón de asignar.
    """
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    callback_data = query.data
    if not callback_data.startswith('apoyo_confirmar_'):
        return

    reporte_id = int(callback_data.split('_')[-1])
    supervisor_telegram_id = query.from_user.id

    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.user import User
            from app.models.team import Team
            from app.routes.telegram_routes import get_telegram_app
            from datetime import datetime

            # Obtener el supervisor
            supervisor = User.query.filter_by(telegram_id=str(supervisor_telegram_id)).first()
            if not supervisor:
                await query.edit_message_text("❌ No autorizado.")
                return

            # Obtener el reporte
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return

            # Obtener la cuadrilla asignada
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()

            if not asignacion or not asignacion.team_id:
                await query.edit_message_text("❌ No hay cuadrilla asignada.")
                return

            cuadrilla = Team.query.get(asignacion.team_id)
            if not cuadrilla:
                await query.edit_message_text("❌ Cuadrilla no encontrada.")
                return

            # Obtener el bot
            bot = context.bot

            # ⭐ ACTUALIZAR MENSAJE PERO MANTENER EL BOTÓN DE ASIGNAR
            mensaje_original = query.message.text
            
            # Remover la sección "ACCIONES" si existe para reemplazarla
            if "📋 ACCIONES:" in mensaje_original:
                mensaje_base = mensaje_original.split("📋 ACCIONES:")[0].strip()
            else:
                mensaje_base = mensaje_original

            # Construir nuevo mensaje con confirmación
            nuevo_mensaje = (
                mensaje_base + 
                f"\n\n✅ *Confirmado por {supervisor.nombre}*\n"
                f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )

            # ⭐ CREAR TECLADO CON EL BOTÓN DE ASIGNAR (MANTENER)
            keyboard = [
                [
                    InlineKeyboardButton("👷 Asignar cuadrilla de apoyo", callback_data=f"apoyo_asignar_{reporte_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Editar mensaje con el nuevo texto y el botón de asignar
            await query.edit_message_text(
                text=nuevo_mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )

            # ============================================================
            # NOTIFICAR A LA CUADRILLA QUE EL SUPERVISOR CONFIRMÓ
            # ============================================================
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla.id, is_active=True).all()
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            direccion = f"{calle_nombre} #{reporte.numero}, {localidad_nombre}"

            # ⭐ CONSTRUIR MENSAJE CON GPS
            gps_texto = ""
            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                gps_texto = f"\n📍 *Ubicación exacta:* [Ver en Google Maps]({maps_url})"

            mensaje_cuadrilla = (
                f"👷 *SUPERVISOR CONFIRMADO - Solicitud de Apoyo*\n\n"
                f"*{supervisor.nombre}* ha confirmado estar enterado de la solicitud de apoyo para el reporte #{reporte.id}.\n\n"
                f"📍 *Ubicación:* {direccion}"
                f"{gps_texto}"
                f"\n\n👷 *Cuadrilla solicitante:* {cuadrilla.nombre}\n\n"
                f"*📋 El supervisor asignará una cuadrilla de apoyo próximamente.*"
            )

            # Notificar a todos los miembros de la cuadrilla
            notificados = 0
            for usuario in usuarios_cuadrilla:
                if usuario.telegram_id:
                    try:
                        await bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje_cuadrilla,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=False
                        )
                        notificados += 1
                        logger.info(f"✅ Notificación enviada a {usuario.nombre} (cuadrilla)")
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario.nombre}: {e}")

            logger.info(f"✅ Supervisor {supervisor.nombre} confirmó recepción de solicitud de apoyo para reporte {reporte_id}. {notificados} notificaciones enviadas a la cuadrilla.")
            
            # Confirmar al supervisor
            await query.answer(f"✅ Confirmación enviada a {notificados} miembros de la cuadrilla", show_alert=False)

    except Exception as e:
        logger.error(f"❌ Error en apoyo_confirmar_handler: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await query.answer("❌ Error al procesar", show_alert=True)
        
# ============================================================
# MANEJAR MOTIVO DE RECHAZO DEL SUPERVISOR
# ============================================================

async def manejar_motivo_rechazo_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Procesa el motivo de rechazo escrito por el supervisor.
    Notifica a la cuadrilla y vuelve el reporte a "En proceso".
    """
    user_id = update.effective_user.id
    motivo = update.message.text.strip()
    
    # Obtener datos del estado
    datos = user_data.get(user_id, {})
    reporte_id = datos.get('reporte_id')
    cuadrilla_id = datos.get('cuadrilla_id')
    cuadrilla_nombre = datos.get('cuadrilla_nombre', 'Cuadrilla desconocida')
    
    if not reporte_id:
        await update.message.reply_text("❌ No se encontró el reporte. Intenta nuevamente.")
        limpiar_estado(user_id)
        return
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.user import User
            from app.models.status import Status
            from app.extensions import db
            from datetime import datetime
            from app.routes.telegram_routes import get_telegram_app
            
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await update.message.reply_text("❌ Reporte no encontrado.")
                limpiar_estado(user_id)
                return
            
            # Obtener el supervisor
            supervisor = User.query.filter_by(telegram_id=str(user_id)).first()
            nombre_supervisor = supervisor.nombre if supervisor else "Supervisor"
            
            # ⭐ CAMBIAR ESTADO A "En proceso"
            estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
            if not estado_en_proceso:
                estado_en_proceso = Status(descripcion="En proceso")
                db.session.add(estado_en_proceso)
                db.session.commit()
            
            # Actualizar la asignación actual
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            if asignacion:
                asignacion.status_id = estado_en_proceso.id
                asignacion.observaciones = f"Rechazado por supervisor {nombre_supervisor} el {datetime.now().strftime('%d/%m/%Y %H:%M')}. Motivo: {motivo}"
                db.session.commit()
            
            # ⭐ NOTIFICAR A LA CUADRILLA
            bot = context.bot
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            
            mensaje_cuadrilla = (
                f"❌ *REPARACIÓN RECHAZADA - Reporte #{reporte.id}*\n\n"
                f"*Supervisor:* {nombre_supervisor}\n"
                f"*Motivo:* {motivo}\n\n"
                f"📋 *Acción requerida:*\n"
                f"Corrige el trabajo y vuelve a subir evidencia de reparación.\n\n"
                f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                f"⏰ *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"*📌 El reporte ha sido regresado a estado 'En proceso'*"
            )
            
            # Notificar a todos los miembros de la cuadrilla
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id, is_active=True).all()
            notificados = 0
            for usuario in usuarios_cuadrilla:
                if usuario.telegram_id:
                    try:
                        await bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje_cuadrilla,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        notificados += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario.nombre}: {e}")
            
            # ⭐ CONFIRMAR AL SUPERVISOR
            await update.message.reply_text(
                f"✅ *Rechazo enviado correctamente*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"👷 *Cuadrilla notificada:* {cuadrilla_nombre}\n"
                f"📝 *Motivo:* {motivo}\n\n"
                f"*📌 El reporte ha vuelto a estado 'En proceso' para corrección.*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            
            logger.info(f"✅ Supervisor {nombre_supervisor} rechazó reporte #{reporte_id} con motivo: {motivo[:50]}...")
            
    except Exception as e:
        logger.error(f"❌ Error en manejar_motivo_rechazo_supervisor: {e}")
        await update.message.reply_text("❌ Error al procesar el rechazo. Intenta nuevamente.")
    
    finally:
        # ⭐ LIMPIAR ESTADO
        limpiar_estado(user_id)
