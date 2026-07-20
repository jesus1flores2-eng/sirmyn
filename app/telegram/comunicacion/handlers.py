from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.services.db_manager import DatabaseManager
from app.models.user import User
from app.telegram.common.utils import user_data, limpiar_estado
import logging

logger = logging.getLogger(__name__)

# Estados
COM_LOCALIDAD, COM_MENSAJE, COM_IMAGEN, COM_CONFIRMAR = range(70, 74)


async def comunicado_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de comunicado"""
    user_id = update.effective_user.id
    
    app = DatabaseManager.get_app()
    with app.app_context():
        usuario = User.query.filter_by(telegram_id=str(user_id), is_active=True).first()
        if not usuario or usuario.rol_especifico != 'comunicacion_social':
            await update.message.reply_text("❌ No autorizado.")
            return ConversationHandler.END
        
        from app.models.report import Localidad
        localidades = Localidad.query.order_by(Localidad.nombre).all()
        
        if not localidades:
            await update.message.reply_text("❌ No hay localidades registradas.")
            return ConversationHandler.END
        
        keyboard = []
        for loc in localidades:
            keyboard.append([f"📍 {loc.nombre}"])
        keyboard.append(["📢 TODAS LAS LOCALIDADES"])
        keyboard.append(["❌ Cancelar"])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        user_data[user_id] = {
            'localidades_list': [(loc.id, loc.nombre) for loc in localidades]
        }
        
        await update.message.reply_text(
            "📣 *COMUNICADO MUNICIPAL*\n\n"
            "Selecciona la *localidad* destino:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return COM_LOCALIDAD


async def seleccionar_localidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda localidad y pide mensaje"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    localidades = user_data[user_id].get('localidades_list', [])
    
    if texto == "📢 TODAS LAS LOCALIDADES":
        user_data[user_id]['localidad_id'] = None
        user_data[user_id]['localidad_nombre'] = "TODAS"
    else:
        nombre = texto.replace("📍 ", "")
        encontrada = None
        for loc_id, loc_nombre in localidades:
            if loc_nombre.lower() == nombre.lower():
                encontrada = (loc_id, loc_nombre)
                break
        
        if not encontrada:
            await update.message.reply_text("❌ Selecciona una localidad del teclado.")
            return COM_LOCALIDAD
        
        user_data[user_id]['localidad_id'] = encontrada[0]
        user_data[user_id]['localidad_nombre'] = encontrada[1]
    
    await update.message.reply_text(
        f"✅ *Localidad:* {user_data[user_id]['localidad_nombre']}\n\n"
        "📝 Escribe el *mensaje* del comunicado:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return COM_MENSAJE


async def escribir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda mensaje y pregunta por imagen"""
    user_id = update.effective_user.id
    user_data[user_id]['mensaje'] = update.message.text.strip()
    
    keyboard = [["📸 Adjuntar imagen", "➡️ Siguiente (sin imagen)"], ["❌ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📸 ¿Deseas agregar una *imagen*?\n\n"
        "• Presiona *📸 Adjuntar imagen* y envía la foto\n"
        "• O presiona *➡️ Siguiente* para continuar sin imagen",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    return COM_IMAGEN


async def manejar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja imagen o salta a confirmación"""
    user_id = update.effective_user.id
    
    # Si es foto
    if update.message and update.message.photo:
        file = await update.message.photo[-1].get_file()
        import os, uuid
        filename = f"comunicado_{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        os.makedirs("uploads/comunicacion", exist_ok=True)
        filepath = f"uploads/comunicacion/{filename}"
        await file.download_to_drive(filepath)
        user_data[user_id]['imagen'] = filepath
        await update.message.reply_text("✅ Imagen recibida.")
        return await mostrar_resumen(update, context)
    
    # Si es texto
    if update.message and update.message.text:
        texto = update.message.text.strip()
        
        if texto == "❌ Cancelar":
            await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
            limpiar_estado(user_id)
            return ConversationHandler.END
        
        if texto == "➡️ Siguiente (sin imagen)":
            user_data[user_id]['imagen'] = None
            return await mostrar_resumen(update, context)
        
        if texto == "📸 Adjuntar imagen":
            await update.message.reply_text("Envía la foto ahora 📸", reply_markup=ReplyKeyboardRemove())
            return COM_IMAGEN
    
    await update.message.reply_text("Envía una foto o selecciona una opción del teclado.")
    return COM_IMAGEN


async def mostrar_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra resumen y pide confirmación"""
    user_id = update.effective_user.id
    datos = user_data[user_id]
    
    resumen = (
        f"📣 *RESUMEN DEL COMUNICADO*\n\n"
        f"📍 *Localidad:* {datos.get('localidad_nombre', 'N/A')}\n"
        f"📝 *Mensaje:* {datos.get('mensaje', '')[:200]}\n"
        f"📸 *Imagen:* {'Sí' if datos.get('imagen') else 'No'}\n\n"
        f"¿Enviar comunicado?"
    )
    
    keyboard = [["✅ ENVIAR", "❌ Cancelar"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(resumen, parse_mode="Markdown", reply_markup=reply_markup)
    return COM_CONFIRMAR


async def confirmar_envio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía el comunicado"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto != "✅ ENVIAR":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    datos = user_data[user_id]
    await update.message.reply_text("📤 Enviando...", reply_markup=ReplyKeyboardRemove())
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.routes.telegram_routes import get_telegram_app
            
            localidad_id = datos.get('localidad_id')
            
            if localidad_id:
                reportes = Report.query.filter_by(localidad_id=localidad_id).distinct(Report.telefono).all()
            else:
                reportes = Report.query.distinct(Report.telefono).all()
            
            destinatarios = set()
            for r in reportes:
                if r.telefono and r.telefono.strip().isdigit():
                    destinatarios.add(r.telefono)
            
            if not destinatarios:
                await update.message.reply_text("⚠️ No se encontraron ciudadanos.")
                limpiar_estado(user_id)
                return ConversationHandler.END
            
            bot_app = get_telegram_app()
            mensaje = f"📣 *COMUNICADO MUNICIPAL*\n\n{datos['mensaje']}"
            
            enviados = 0
            for tid in destinatarios:
                try:
                    if datos.get('imagen'):
                        with open(datos['imagen'], 'rb') as img:
                            await bot_app.bot.send_photo(
                                chat_id=int(tid),
                                photo=img,
                                caption=mensaje,
                                parse_mode="Markdown"
                            )
                    else:
                        await bot_app.bot.send_message(
                            chat_id=int(tid),
                            text=mensaje,
                            parse_mode="Markdown"
                        )
                    enviados += 1
                except:
                    pass
            
            if datos.get('imagen'):
                try:
                    import os
                    os.remove(datos['imagen'])
                except:
                    pass
            
            await update.message.reply_text(
                f"✅ *COMUNICADO ENVIADO*\n\n"
                f"📍 *Localidad:* {datos.get('localidad_nombre')}\n"
                f"👥 *Destinatarios:* {len(destinatarios)}\n"
                f"✅ *Enviados:* {enviados}",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        await update.message.reply_text("❌ Error al enviar.")
    
    limpiar_estado(user_id)
    return ConversationHandler.END
