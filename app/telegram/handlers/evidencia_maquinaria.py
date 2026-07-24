"""
ConversationHandler para subida de evidencia de maquinaria (retroexcavadora, camión)
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

# Estados
MAQ_FOTO_ANTES, MAQ_FOTO_DESPUES, MAQ_CONFIRMAR = range(84, 87)


async def maquinaria_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: operador presiona 'Subir evidencia' en mensaje de solicitud"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Formato: maq_retro_REPORTEID o maq_camion_REPORTEID
    partes = callback_data.split('_')
    tipo_maq = partes[1]  # 'retro' o 'camion'
    reporte_id = int(partes[2])
    
    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(user_id)).first()
        reporte = Report.query.get(reporte_id)
        
        if not reporte:
            await query.edit_message_text("❌ Reporte no encontrado.")
            return ConversationHandler.END
    
    # Guardar estado
    user_data[user_id] = {
        'modo_maquinaria': True,
        'reporte_id': reporte_id,
        'tipo_maquinaria': tipo_maq,
        'paso': 'foto_antes',
        'foto_antes': None,
        'foto_despues': None
    }
    
    nombre_maq = "Retroexcavadora" if tipo_maq == 'retro' else "Camión de volteo"
    texto_accion = "del trabajo a realizar (ej: tubería rota, fuga)" if tipo_maq == 'retro' else "del material cargado"
    
    await query.message.reply_text(
        f"📸 *{nombre_maq.upper()} - EVIDENCIA*\n\n"
        f"Paso 1/2: Toma una foto *ANTES* {texto_accion}\n\n"
        f"Envía la foto ahora.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    
    return MAQ_FOTO_ANTES


async def maquinaria_foto_antes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe foto del antes y pide foto del después"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if update.message and update.message.photo:
        try:
            file = await update.message.photo[-1].get_file()
            app = DatabaseManager.get_app()
            
            with app.app_context():
                reporte = Report.query.get(datos.get('reporte_id'))
                carpeta = "agua_potable"
            
            static_folder = app.config.get('STATIC_FOLDER', 'app/static')
            base_path = Path(static_folder) / 'evidencias' / carpeta / 'cuadrilla'
            base_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"antes_{datos['tipo_maquinaria']}_{datos['reporte_id']}_{timestamp}.jpg"
            filepath = base_path / filename
            await file.download_to_drive(filepath)
            
            public_id = f"antes_{datos['tipo_maquinaria']}_{datos['reporte_id']}_{uuid.uuid4().hex[:4]}"
            url = subir_archivo(str(filepath), folder=f"{carpeta}/cuadrilla", public_id=public_id)
            
            if url:
                datos['foto_antes'] = url
                try: os.remove(filepath)
                except: pass
            else:
                datos['foto_antes'] = f"evidencias/{carpeta}/cuadrilla/{filename}"
            
            user_data[user_id] = datos
            
            nombre_maq = "Retroexcavadora" if datos['tipo_maquinaria'] == 'retro' else "Camión de volteo"
            texto_accion = "del trabajo terminado (ej: reparación finalizada)" if datos['tipo_maquinaria'] == 'retro' else "del material ya descargado en el sitio"
            
            await update.message.reply_text(
                f"✅ Foto ANTES recibida.\n\n"
                f"Paso 2/2: Toma una foto *DESPUÉS* {texto_accion}\n\n"
                f"Envía la foto ahora o escribe 'cancelar'.",
                parse_mode=ParseMode.MARKDOWN
            )
            return MAQ_FOTO_DESPUES
            
        except Exception as e:
            logger.error(f"Error guardando foto antes: {e}")
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
            return MAQ_FOTO_ANTES
    
    if update.message and update.message.text:
        texto = update.message.text.strip().lower()
        if texto == 'cancelar':
            claves = ['modo_maquinaria', 'reporte_id', 'tipo_maquinaria', 'paso', 'foto_antes', 'foto_despues']
            for clave in claves:
                user_data[user_id].pop(clave, None)
            await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
    
    await update.message.reply_text("Por favor, envía una foto.")
    return MAQ_FOTO_ANTES


async def maquinaria_foto_despues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe foto del después y pide confirmación"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if update.message and update.message.photo:
        try:
            file = await update.message.photo[-1].get_file()
            app = DatabaseManager.get_app()
            
            with app.app_context():
                reporte = Report.query.get(datos.get('reporte_id'))
                carpeta = "agua_potable"
            
            static_folder = app.config.get('STATIC_FOLDER', 'app/static')
            base_path = Path(static_folder) / 'evidencias' / carpeta / 'materiales_utilizados'
            base_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"despues_{datos['tipo_maquinaria']}_{datos['reporte_id']}_{timestamp}.jpg"
            filepath = base_path / filename
            await file.download_to_drive(filepath)
            
            public_id = f"despues_{datos['tipo_maquinaria']}_{datos['reporte_id']}_{uuid.uuid4().hex[:4]}"
            url = subir_archivo(str(filepath), folder=f"{carpeta}/materiales_utilizados", public_id=public_id)
            
            if url:
                datos['foto_despues'] = url
                try: os.remove(filepath)
                except: pass
            else:
                datos['foto_despues'] = f"evidencias/{carpeta}/materiales_utilizados/{filename}"
            
            datos['paso'] = 'confirmar'
            user_data[user_id] = datos
            
            nombre_maq = "Retroexcavadora" if datos['tipo_maquinaria'] == 'retro' else "Camión de volteo"
            
            await update.message.reply_text(
                f"✅ Foto DESPUÉS recibida.\n\n"
                f"📋 *Resumen {nombre_maq}:*\n"
                f"📸 Foto ANTES: ✅\n"
                f"📸 Foto DESPUÉS: ✅\n\n"
                f"¿Guardar evidencia y notificar a la cuadrilla?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardMarkup([["✅ Sí, guardar"], ["❌ Cancelar"]], resize_keyboard=True)
            )
            return MAQ_CONFIRMAR
            
        except Exception as e:
            logger.error(f"Error guardando foto después: {e}")
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
            return MAQ_FOTO_DESPUES
    
    if update.message and update.message.text:
        texto = update.message.text.strip().lower()
        if texto == 'cancelar':
            claves = ['modo_maquinaria', 'reporte_id', 'tipo_maquinaria', 'paso', 'foto_antes', 'foto_despues']
            for clave in claves:
                user_data[user_id].pop(clave, None)
            await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
    
    await update.message.reply_text("Por favor, envía una foto del después.")
    return MAQ_FOTO_DESPUES


async def maquinaria_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda evidencia y notifica a la cuadrilla que solicitó"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if update.message.text != "✅ Sí, guardar":
        claves = ['modo_maquinaria', 'reporte_id', 'tipo_maquinaria', 'paso', 'foto_antes', 'foto_despues']
        for clave in claves:
            user_data[user_id].pop(clave, None)
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            asignacion = Assignment.query.filter_by(
                report_id=datos['reporte_id']
            ).order_by(Assignment.timestamp.desc()).first()
            
            if asignacion:
                nombre_maq = "Retroexcavadora" if datos['tipo_maquinaria'] == 'retro' else "Camión de volteo"
                
                # ⭐ CREAR NUEVA ASIGNACIÓN (para que quede en el historial sin sobreescribir)
                nueva_asignacion = Assignment(
                    report_id=datos['reporte_id'],
                    team_id=asignacion.team_id,
                    status_id=asignacion.status_id,
                    timestamp=datetime.utcnow(),
                    observaciones=f"{nombre_maq} completó el trabajo. Evidencia disponible."
                )
                
                # Guardar foto "antes" como evidencia de cuadrilla
                if datos.get('foto_antes'):
                    nueva_asignacion.evidencia_cuadrilla = datos['foto_antes']
                
                # Guardar foto "después" como materiales utilizados
                if datos.get('foto_despues'):
                    nueva_asignacion.materiales_utilizados = datos['foto_despues']
                
                db.session.add(nueva_asignacion)
                db.session.commit()
                
                # Notificar a la cuadrilla que solicitó
                if asignacion.team_id:
                    usuarios_cuadrilla = User.query.filter_by(
                        team_id=asignacion.team_id,
                        is_active=True
                    ).all()
                    
                    reporte = Report.query.get(datos['reporte_id'])
                    calle_nombre = reporte.calle.nombre if reporte and reporte.calle else 'N/D'
                    localidad_nombre = reporte.localidad.nombre if reporte and reporte.localidad else 'N/D'
                    
                    for usuario in usuarios_cuadrilla:
                        if usuario.telegram_id:
                            try:
                                await context.bot.send_message(
                                    chat_id=int(usuario.telegram_id),
                                    text=(
                                        f"✅ *{nombre_maq.upper()} - TRABAJO COMPLETADO*\n\n"
                                        f"📋 *Reporte:* #{datos['reporte_id']}\n"
                                        f"📍 *Ubicación:* {calle_nombre} #{reporte.numero if reporte else ''}, {localidad_nombre}\n\n"
                                        f"📸 *Evidencia disponible en el historial del reporte.*"
                                    ),
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            except Exception as e:
                                logger.error(f"Error notificando a cuadrilla: {e}")
                
                await update.message.reply_text(
                    f"✅ *Evidencia guardada correctamente*\n\n"
                    f"La cuadrilla ha sido notificada.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardRemove()
                )
                
    except Exception as e:
        logger.error(f"Error en maquinaria_confirmar: {e}")
        await update.message.reply_text("❌ Error al guardar.", reply_markup=ReplyKeyboardRemove())
    
    claves = ['modo_maquinaria', 'reporte_id', 'tipo_maquinaria', 'paso', 'foto_antes', 'foto_despues']
    for clave in claves:
        user_data[user_id].pop(clave, None)
    
    return ConversationHandler.END
