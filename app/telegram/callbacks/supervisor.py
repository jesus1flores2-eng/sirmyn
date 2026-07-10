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
            # Mostrar opciones de rechazo
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Reasignar automáticamente", 
                                       callback_data=f"rechazar_rea_{reporte_id}")
                ],
                [
                    InlineKeyboardButton("👨‍💼 Enviar a administrador", 
                                       callback_data=f"rechazar_admin_{reporte_id}")
                ],
                [
                    InlineKeyboardButton("🔧 Devolver a misma cuadrilla", 
                                       callback_data=f"rechazar_misma_{reporte_id}")
                ],
                [
                    InlineKeyboardButton("❌ Cancelar", 
                                       callback_data=f"rechazar_cancel_{reporte_id}")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            mensaje_original = query.message.text
            if "📋 ACCIONES DISPONIBLES:" in mensaje_original:
                mensaje_original = mensaje_original.split("📋 ACCIONES DISPONIBLES:")[0].strip()
            
            await query.edit_message_text(
                text=mensaje_original + f"\n\n❌ *REPARACIÓN RECHAZADA*\n\n¿Qué deseas hacer con este reporte?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            logger.info(f"❌ Supervisor {usuario.nombre} rechazó reporte #{reporte_id}")
            await query.answer("⚠️ Rechazo iniciado", show_alert=False)


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
