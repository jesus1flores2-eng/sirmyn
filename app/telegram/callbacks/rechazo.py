"""
Maneja el flujo de rechazo del usuario (motivo, evidencia, confirmación)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.models.feedback import RechazoUsuario
from app.extensions import db
from datetime import datetime
import logging, os, uuid

logger = logging.getLogger(__name__)

async def rechazo_motivo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de motivo de rechazo"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    user_id = query.from_user.id
    
    if not callback_data.startswith('rech_motivo_'):
        return
    
    partes = callback_data.split('_')
    motivo = partes[2]  # 'problema_persiste', 'reparacion_incompleta', etc.
    reporte_id = int(partes[3])
    
    if user_id not in user_data or not user_data[user_id].get('modo_rechazo'):
        await query.edit_message_text("❌ Sesión expirada.")
        return
    
    user_data[user_id]['motivo'] = motivo
    user_data[user_id]['reporte_id'] = reporte_id
    
    if motivo == 'otro':
        await query.edit_message_text(
            "📝 *Describe tu motivo:*\n\nEscribe con detalle por qué rechazas la reparación (mínimo 10 caracteres):",
            parse_mode=ParseMode.MARKDOWN
        )
        return RECHAZO_DESCRIPCION
    else:
        # Pedir evidencia directamente
        user_data[user_id]['paso_actual'] = 'evidencia'
        await query.edit_message_text(
            "📸 *Evidencia obligatoria:*\n\nEnvía una FOTO o VIDEO que muestre la situación (máx 20MB):",
            parse_mode=ParseMode.MARKDOWN
        )
        return RECHAZO_EVIDENCIA


async def rechazo_descripcion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la descripción para motivo 'otro'"""
    user_id = update.effective_user.id
    descripcion = update.message.text.strip()
    
    if len(descripcion) < 10:
        await update.message.reply_text("❌ La descripción es muy corta (mínimo 10 caracteres).")
        return RECHAZO_DESCRIPCION
    
    user_data[user_id]['descripcion'] = descripcion
    user_data[user_id]['paso_actual'] = 'evidencia'
    
    await update.message.reply_text(
        "📸 *Evidencia obligatoria:*\n\nEnvía una FOTO o VIDEO que muestre la situación (máx 20MB):",
        parse_mode=ParseMode.MARKDOWN
    )
    return RECHAZO_EVIDENCIA


async def rechazo_evidencia_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la evidencia del rechazo (foto/video obligatoria)"""
    user_id = update.effective_user.id
    
    if user_id not in user_data or not user_data[user_id].get('modo_rechazo'):
        await update.message.reply_text("❌ Sesión expirada.")
        return ConversationHandler.END
    
    if not (update.message.photo or update.message.video):
        await update.message.reply_text("❌ Debes enviar una FOTO o VIDEO.")
        return RECHAZO_EVIDENCIA
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
            reporte_id = user_data[user_id]['reporte_id']
            
            if update.message.photo:
                file = await update.message.photo[-1].get_file()
                extension = 'jpg'
                tipo = 'foto'
            else:
                file = await update.message.video.get_file()
                extension = 'mp4'
                tipo = 'video'
            
            if file.file_size > 20 * 1024 * 1024:
                await update.message.reply_text("⚠️ El archivo es muy grande (máx 20MB).")
                return RECHAZO_EVIDENCIA
            
            # Guardar en carpeta de rechazos
            carpeta_rechazos = os.path.join(upload_folder, 'rechazos')
            os.makedirs(carpeta_rechazos, exist_ok=True)
            
            filename = f"rechazo_{reporte_id}_{uuid.uuid4().hex[:8]}.{extension}"
            filepath = os.path.join(carpeta_rechazos, filename)
            await file.download_to_drive(filepath)
            
            user_data[user_id]['evidencia_path'] = f"rechazos/{filename}"
            user_data[user_id]['tipo_evidencia'] = tipo
            
            # Mostrar resumen
            motivos_texto = {
                'problema_persiste': '🚫 PROBLEMA PERSISTE IGUAL',
                'reparacion_incompleta': '🔧 REPARACIÓN INCOMPLETA',
                'no_termino_tapar': '🕳️ NO TERMINARON DE TAPAR',
                'causo_otro': '⚠️ CAUSARON OTRO PROBLEMA',
                'otro': '📝 OTRO MOTIVO'
            }
            motivo_texto = motivos_texto.get(user_data[user_id]['motivo'], 'OTRO')
            descripcion = user_data[user_id].get('descripcion', '')
            
            mensaje = f"✅ *Resumen de rechazo*\n\nMotivo: {motivo_texto}\n"
            if descripcion:
                mensaje += f"Descripción: {descripcion}\n"
            mensaje += f"Evidencia: {tipo.upper()} recibida\n\n¿Confirmar el rechazo?"
            
            keyboard = [
                [InlineKeyboardButton("✅ CONFIRMAR", callback_data=f"rech_confirmar_{reporte_id}")],
                [InlineKeyboardButton("❌ CANCELAR", callback_data=f"rech_cancelar_{reporte_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            return RECHAZO_CONFIRMACION
            
    except Exception as e:
        logger.error(f"❌ Error en rechazo_evidencia_handler: {e}")
        await update.message.reply_text("❌ Error al procesar la evidencia. Intenta de nuevo.")
        return RECHAZO_EVIDENCIA


async def rechazo_confirmacion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la confirmación final del rechazo"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    user_id = query.from_user.id
    
    if not callback_data.startswith('rech_'):
        return
    
    partes = callback_data.split('_')
    accion = partes[1]  # 'confirmar' o 'cancelar'
    reporte_id = int(partes[2])
    
    if user_id not in user_data or not user_data[user_id].get('modo_rechazo'):
        await query.edit_message_text("❌ Sesión expirada.")
        return
    
    if accion == 'cancelar':
        await query.edit_message_text("❌ Rechazo cancelado.")
        user_data[user_id].pop('modo_rechazo', None)
        return
    
    # Confirmar rechazo
    app = DatabaseManager.get_app()
    with app.app_context():
        # Guardar en RechazoUsuario
        rechazo = RechazoUsuario(
            reporte_id=reporte_id,
            usuario_id=user_id,
            motivo=user_data[user_id]['motivo'],
            descripcion=user_data[user_id].get('descripcion', ''),
            evidencia_path=user_data[user_id]['evidencia_path'],
            fecha=datetime.utcnow()
        )
        db.session.add(rechazo)
        
        # Cambiar estado del reporte
        estado_rechazado = Status.query.filter_by(descripcion="Rechazado por usuario").first()
        if not estado_rechazado:
            estado_rechazado = Status(descripcion="Rechazado por usuario")
            db.session.add(estado_rechazado)
            db.session.commit()
        
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if asignacion:
            nueva_asignacion = Assignment(
                report_id=reporte_id,
                team_id=asignacion.team_id,
                status_id=estado_rechazado.id,
                timestamp=datetime.utcnow(),
                observaciones=f"Rechazado por usuario: {user_data[user_id]['motivo']}"
            )
            db.session.add(nueva_asignacion)
            db.session.commit()
        
        # Notificar al responsable (Jefe Técnico o Director)
        from app.services.notification_service import notificar_rechazo_usuario
        await notificar_rechazo_usuario(reporte_id, user_id)
        
        await query.edit_message_text(
            f"✅ *Rechazo enviado.*\n\nEl reporte #{reporte_id} ha sido rechazado y notificado al responsable.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"✅ Rechazo registrado para reporte #{reporte_id} por usuario {user_id}")
    
    # Limpiar datos
    if user_id in user_data:
        user_data[user_id].pop('modo_rechazo', None)
        user_data[user_id].pop('motivo', None)
        user_data[user_id].pop('descripcion', None)
        user_data[user_id].pop('evidencia_path', None)
