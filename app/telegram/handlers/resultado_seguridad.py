"""
Flujo de resultado final para patrullas de Seguridad Pública
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
SEG_RESULTADO, SEG_FOLIO, SEG_DOCUMENTO = range(90, 93)


async def resultado_seguridad_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: patrulla presiona 'Reportar resultado final'"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data  # seg_resultado_REPORTEID
    reporte_id = int(callback_data.split('_')[2])
    
    user_data[user_id] = {
        'modo_resultado_seguridad': True,
        'reporte_id': reporte_id,
        'paso': 'resultado'
    }
    
    keyboard = [
        ["🚔 IPH (Delito) - Ministerio Público"],
        ["📋 Infracción - Juzgado Cívico"],
        ["❌ Falsa alarma"],
        ["↩️ Cancelar"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await query.message.reply_text(
        "📋 *RESULTADO FINAL*\n\n"
        "Selecciona el resultado de la atención:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
    return SEG_RESULTADO


async def resultado_seleccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el tipo de resultado y pide folio"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "↩️ Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    resultados = {
        "🚔 IPH (Delito) - Ministerio Público": "IPH - Ministerio Público",
        "📋 Infracción - Juzgado Cívico": "Infracción - Juzgado Cívico",
        "❌ Falsa alarma": "Falsa alarma"
    }
    
    resultado = resultados.get(texto)
    if not resultado:
        await update.message.reply_text("Selecciona una opción del teclado.")
        return SEG_RESULTADO
    
    user_data[user_id]['tipo_resultado'] = resultado
    
    if resultado == "Falsa alarma":
        await update.message.reply_text(
            "📝 Escribe brevemente el motivo de la falsa alarma:\n(ej: 'Vecino confundió ruido con disparos')",
            reply_markup=ReplyKeyboardRemove()
        )
        user_data[user_id]['paso'] = 'folio'
        return SEG_FOLIO
    
    await update.message.reply_text(
        f"✅ *{resultado}*\n\n"
        "📝 Escribe el *folio o número de parte*:\n"
        "(ej: 'IPH-45672' o 'Boleta-123')",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    user_data[user_id]['paso'] = 'folio'
    return SEG_FOLIO


async def resultado_folio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda folio y pide documento"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    user_data[user_id]['folio'] = texto
    
    keyboard = [["📄 Subir documento (foto)", "➡️ Omitir documento"], ["↩️ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📄 ¿Tienes una foto del *documento/hoja de traslado/IPH*?\n\n"
        "Puedes enviar la foto ahora o presionar 'Omitir'.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
    return SEG_DOCUMENTO


async def resultado_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda documento y finaliza"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    if update.message and update.message.photo:
        try:
            file = await update.message.photo[-1].get_file()
            
            filename = f"seguridad_{datos['reporte_id']}_{uuid.uuid4().hex[:8]}.jpg"
            os.makedirs("uploads/seguridad", exist_ok=True)
            filepath = f"uploads/seguridad/{filename}"
            await file.download_to_drive(filepath)
            
            url = subir_archivo(filepath, folder="seguridad", public_id=f"doc_{datos['reporte_id']}_{uuid.uuid4().hex[:4]}")
            if url:
                datos['documento'] = url
                try: os.remove(filepath)
                except: pass
            else:
                datos['documento'] = f"seguridad/{filename}"
            
            user_data[user_id] = datos
            await update.message.reply_text("✅ Documento recibido.")
            return await guardar_resultado(update, context)
            
        except Exception as e:
            logger.error(f"Error guardando documento: {e}")
            await update.message.reply_text("❌ Error. Intenta de nuevo.")
            return SEG_DOCUMENTO
    
    if update.message and update.message.text:
        texto = update.message.text.strip()
        
        if texto == "↩️ Cancelar":
            await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
            limpiar_estado(user_id)
            return ConversationHandler.END
        
        if texto == "➡️ Omitir documento":
            datos['documento'] = None
            user_data[user_id] = datos
            return await guardar_resultado(update, context)
        
        if texto == "📄 Subir documento (foto)":
            await update.message.reply_text("Envía la foto del documento ahora 📄", reply_markup=ReplyKeyboardRemove())
            return SEG_DOCUMENTO
    
    await update.message.reply_text("Envía una foto del documento o presiona 'Omitir'.")
    return SEG_DOCUMENTO


async def guardar_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el resultado final y notifica a Cabina"""
    user_id = update.effective_user.id
    datos = user_data.get(user_id, {})
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            asignacion = Assignment.query.filter_by(
                report_id=datos['reporte_id']
            ).order_by(Assignment.timestamp.desc()).first()
            
            if asignacion:
                # Crear nueva asignación para el resultado
                observacion = f"{datos['tipo_resultado']}"
                if datos.get('folio'):
                    observacion += f" - Folio: {datos['folio']}"
                
                nueva_asignacion = Assignment(
                    report_id=datos['reporte_id'],
                    team_id=asignacion.team_id,
                    status_id=asignacion.status_id,
                    timestamp=datetime.utcnow(),
                    observaciones=observacion
                )
                
                if datos.get('documento'):
                    nueva_asignacion.materiales_utilizados = datos['documento']
                
                db.session.add(nueva_asignacion)
                db.session.commit()
                
                # Notificar a Cabina
                cabina = User.query.filter_by(area='seguridad', rol_especifico='jefe_area', is_active=True).first()
                if not cabina:
                    cabina = User.query.filter_by(area='seguridad', rol_especifico='director', is_active=True).first()
                
                if cabina and cabina.telegram_id:
                    reporte = Report.query.get(datos['reporte_id'])
                    cuadrilla = Team.query.get(asignacion.team_id)
                    
                    mensaje_cabina = (
                        f"📋 *RESULTADO FINAL - Reporte #{datos['reporte_id']}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"👮 *Patrulla:* {cuadrilla.nombre if cuadrilla else 'N/D'}\n"
                        f"📋 *Resultado:* {datos['tipo_resultado']}\n"
                    )
                    if datos.get('folio'):
                        mensaje_cabina += f"📝 *Folio/Parte:* {datos['folio']}\n"
                    
                    if datos.get('documento'):
                        mensaje_cabina += f"📄 *Documento:* Disponible en historial\n"
                    
                    await context.bot.send_message(
                        chat_id=int(cabina.telegram_id),
                        text=mensaje_cabina,
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                await update.message.reply_text(
                    f"✅ *Resultado guardado*\n\n"
                    f"📋 {datos['tipo_resultado']}\n"
                    f"📝 Folio: {datos.get('folio', 'N/A')}\n\n"
                    f"Cabina ha sido notificada.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardRemove()
                )
                
    except Exception as e:
        logger.error(f"Error en guardar_resultado: {e}")
        await update.message.reply_text("❌ Error al guardar.", reply_markup=ReplyKeyboardRemove())
    
    claves = ['modo_resultado_seguridad', 'reporte_id', 'paso', 'tipo_resultado', 'folio', 'documento']
    for clave in claves:
        user_data[user_id].pop(clave, None)
    
    return ConversationHandler.END
