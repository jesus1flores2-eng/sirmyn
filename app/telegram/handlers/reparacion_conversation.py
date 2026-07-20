"""
ConversationHandler exclusivo para el flujo de reparación de cuadrillas.
Se activa con el botón "🔧 Subir evidencia reparación" desde los callbacks.
"""

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from app.services.cloudinary_service import subir_archivo
from datetime import datetime
from pathlib import Path
import logging
import os
import uuid

logger = logging.getLogger(__name__)

# Estados exclusivos para reparación
REP_EVIDENCIA, REP_MATERIALES, REP_COMENTARIO, REP_CONFIRMAR = range(80, 84)


async def reparacion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: Se llama desde el callback de 'Subir evidencia reparación'"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data  # formato: reparacion_REPORTEID
    
    reporte_id = int(callback_data.split('_')[1])
    
    app = DatabaseManager.get_app()
    with app.app_context():
        asignacion = Assignment.query.filter_by(
            report_id=reporte_id
        ).order_by(Assignment.timestamp.desc()).first()
        
        if not asignacion:
            await query.edit_message_text("❌ No se encontró la asignación del reporte.")
            return ConversationHandler.END
        
        usuario = User.query.filter_by(telegram_id=str(user_id)).first()
        if not usuario or usuario.team_id != asignacion.team_id:
            await query.edit_message_text("❌ No estás asignado a este reporte.")
            return ConversationHandler.END
        
        reporte = Report.query.get(reporte_id)
    
    # Guardar estado
    user_data[user_id] = {
        'modo_reparacion': True,
        'reporte_id': reporte_id,
        'asignacion_id': asignacion.id,
        'paso': 'evidencia',
        'evidencias': [],
        'materiales': [],
        'comentario': '',
        'tipo_reporte': reporte.tipo if reporte else 'General'
    }
    
    await query.message.reply_text(
        "🔧 *EVIDENCIA DE REPARACIÓN*\n\n"
        "Envía las fotos/videos del trabajo realizado:\n"
        "• Puedes enviar múltiples archivos\n"
        "• Cuando termines, escribe *'listo'*\n"
        "• Para cancelar, escribe *'cancelar'*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    
    return REP_EVIDENCIA


async def reparacion_evidencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe fotos/videos o texto (listo/cancelar)"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    # Si es texto
    if update.message and update.message.text:
        texto = update.message.text.lower()
        
        if texto == 'cancelar':
            claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id', 'tipo_reporte']
            for clave in claves:
                user_data[user_id].pop(clave, None)
            await update.message.reply_text("❌ *Reparación cancelada.*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        
        if texto == 'listo':
            if not datos.get('evidencias'):
                await update.message.reply_text("❌ No has enviado evidencia. Envía al menos una foto/video o escribe 'cancelar'.", parse_mode=ParseMode.MARKDOWN)
                return REP_EVIDENCIA
            
            # Si es Aseo, saltar materiales
            if datos.get('tipo_reporte') == "Aseo público":
                datos['materiales'] = 'No aplica'
                datos['paso'] = 'comentario'
                user_data[user_id] = datos
                await update.message.reply_text("💬 *Comentarios adicionales:*\n\nDescribe el trabajo realizado (opcional, escribe 'omitir' para saltar):", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
                return REP_COMENTARIO
            
            datos['paso'] = 'materiales'
            user_data[user_id] = datos
            await update.message.reply_text("📦 *Materiales utilizados:*\n\nEnvía una foto de los materiales usados o escribe la lista (ej: '5 tubos PVC, 3 codos'):", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
            return REP_MATERIALES
    
    # Si es foto/video
    if update.message and (update.message.photo or update.message.video):
        try:
            app = DatabaseManager.get_app()
            with app.app_context():
                from app.telegram.common.keyboards import obtener_carpeta_departamento
                reporte = Report.query.get(datos.get('reporte_id'))
                carpeta = obtener_carpeta_departamento(reporte.tipo) if reporte else "general"
            
            static_folder = app.config.get('STATIC_FOLDER', 'app/static')
            base_path = Path(static_folder) / 'evidencias' / carpeta / 'cuadrilla'
            base_path.mkdir(parents=True, exist_ok=True)
            
            if update.message.photo:
                file = await update.message.photo[-1].get_file()
                extension = 'jpg'
            else:
                file = await update.message.video.get_file()
                extension = 'mp4'
            
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"evidencia_{datos['reporte_id']}_{timestamp}_{uuid.uuid4().hex[:4]}.{extension}"
            filepath = base_path / filename
            await file.download_to_drive(filepath)
            
            public_id = f"reparacion_{datos['reporte_id']}_{uuid.uuid4().hex[:4]}"
            url = subir_archivo(str(filepath), folder=f"{carpeta}/cuadrilla", public_id=public_id)
            if url:
                datos['evidencias'].append(url)
                try: os.remove(filepath)
                except: pass
            else:
                datos['evidencias'].append(f"evidencias/{carpeta}/cuadrilla/{filename}")
            
            user_data[user_id] = datos
            await update.message.reply_text(f"✅ Evidencia {len(datos['evidencias'])} recibida. Envía más o escribe 'listo'.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error guardando evidencia: {e}")
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.", parse_mode=ParseMode.MARKDOWN)
        
        return REP_EVIDENCIA
    
    return REP_EVIDENCIA


async def reparacion_materiales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe materiales (foto o texto)"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if update.message and update.message.photo:
        try:
            app = DatabaseManager.get_app()
            with app.app_context():
                from app.telegram.common.keyboards import obtener_carpeta_departamento
                reporte = Report.query.get(datos.get('reporte_id'))
                carpeta = obtener_carpeta_departamento(reporte.tipo) if reporte else "general"
            
            static_folder = app.config.get('STATIC_FOLDER', 'app/static')
            base_path = Path(static_folder) / 'evidencias' / carpeta / 'materiales_utilizados'
            base_path.mkdir(parents=True, exist_ok=True)
            
            file = await update.message.photo[-1].get_file()
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"materiales_{datos['reporte_id']}_{timestamp}.jpg"
            filepath = base_path / filename
            await file.download_to_drive(filepath)
            
            public_id = f"material_{datos['reporte_id']}_{uuid.uuid4().hex[:4]}"
            url = subir_archivo(str(filepath), folder=f"{carpeta}/materiales_utilizados", public_id=public_id)
            if url:
                datos['materiales'] = url
                try: os.remove(filepath)
                except: pass
            else:
                datos['materiales'] = f"evidencias/{carpeta}/materiales_utilizados/{filename}"
            
            user_data[user_id] = datos
        except Exception as e:
            logger.error(f"Error guardando materiales: {e}")
            await update.message.reply_text("❌ Error. Escribe la lista de materiales.", parse_mode=ParseMode.MARKDOWN)
            return REP_MATERIALES
    elif update.message and update.message.text:
        texto = update.message.text.strip()
        if texto.lower() == 'cancelar':
            claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id', 'tipo_reporte']
            for clave in claves:
                user_data[user_id].pop(clave, None)
            await update.message.reply_text("❌ *Reparación cancelada.*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        datos['materiales'] = texto
        user_data[user_id] = datos
    
    datos['paso'] = 'comentario'
    user_data[user_id] = datos
    await update.message.reply_text("💬 *Comentarios adicionales:*\n\nDescribe el trabajo realizado (opcional, escribe 'omitir' para saltar):", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    return REP_COMENTARIO


async def reparacion_comentario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe comentario y muestra resumen"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if not update.message or not update.message.text:
        return REP_COMENTARIO
    
    texto = update.message.text.strip()
    if texto.lower() == 'cancelar':
        claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id', 'tipo_reporte']
        for clave in claves:
            user_data[user_id].pop(clave, None)
        await update.message.reply_text("❌ *Reparación cancelada.*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    if texto.lower() != 'omitir':
        datos['comentario'] = texto
    else:
        datos['comentario'] = ''
    
    user_data[user_id] = datos
    
    mensaje = f"📋 *Resumen de reparación*\n\n📷 Evidencias: {len(datos.get('evidencias', []))}\n"
    if isinstance(datos.get('materiales'), str) and datos['materiales'].endswith(('.jpg', '.jpeg', '.png')):
        mensaje += "📦 Materiales: Foto adjunta\n"
    else:
        mensaje += f"📦 Materiales: {datos.get('materiales', 'No especificado')}\n"
    mensaje += f"💬 Comentarios: {datos.get('comentario', 'Sin comentarios')}\n\n¿Guardar y enviar a revisión?"
    
    keyboard = [["✅ Sí, guardar"], ["❌ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    datos['paso'] = 'confirmacion'
    user_data[user_id] = datos
    return REP_CONFIRMAR


async def reparacion_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda reparación y notifica"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if not update.message or not update.message.text:
        return REP_CONFIRMAR
    
    if update.message.text == "✅ Sí, guardar":
        app = DatabaseManager.get_app()
        with app.app_context():
            asignacion = Assignment.query.get(datos['asignacion_id'])
            if asignacion:
                if datos.get('evidencias'):
                    asignacion.evidencia_cuadrilla = ','.join(datos['evidencias'])
                if isinstance(datos.get('materiales'), str) and datos['materiales'].endswith(('.jpg', '.jpeg', '.png')):
                    asignacion.materiales_utilizados = datos['materiales']
                else:
                    asignacion.materiales_utilizados = datos.get('materiales', '')
                if datos.get('comentario'):
                    asignacion.observaciones = datos['comentario']
                
                estado_revision = Status.query.filter_by(descripcion="En revisión").first()
                if not estado_revision:
                    estado_revision = Status(descripcion="En revisión")
                    db.session.add(estado_revision)
                    db.session.commit()
                
                asignacion.status_id = estado_revision.id
                db.session.commit()
                
                team = Team.query.get(asignacion.team_id)
                if team and team.area == 'agua':
                    from app.services.notification_service import notificar_supervisor_revision
                    await notificar_supervisor_revision(datos['reporte_id'], team.id)
                else:
                    from app.services.notification_service import notificar_director_validacion
                    await notificar_director_validacion(datos['reporte_id'], team.id)
                
                await update.message.reply_text("✅ ¡Reparación guardada! Enviada a revisión.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text("❌ Error: no se encontró la asignación.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ *Reparación cancelada.*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    
    claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id', 'tipo_reporte']
    for clave in claves:
        user_data[user_id].pop(clave, None)
    
    return ConversationHandler.END
