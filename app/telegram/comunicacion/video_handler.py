"""
Flujo de /comunicado_video para crear slideshow y enviar
"""
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.common.utils import user_data, limpiar_estado
from app.services.db_manager import DatabaseManager
from app.services.cloudinary_comunicacion import (
    subir_foto_comunicacion, crear_video_slideshow, borrar_fotos_temporales
)
from app.models.user import User
import logging
import os
import uuid

logger = logging.getLogger(__name__)

# Estados
COMVIDEO_LOCALIDAD, COMVIDEO_FOTOS, COMVIDEO_TITULO, COMVIDEO_MUSICA, COMVIDEO_MENSAJE, COMVIDEO_CONFIRMAR = range(90, 96)


async def comunicado_video_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia flujo de comunicado con video"""
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
            'modo_comunicado_video': True,
            'localidades_list': [(loc.id, loc.nombre) for loc in localidades],
            'fotos_urls': []
        }
        
        await update.message.reply_text(
            "🎬 *COMUNICADO CON VIDEO*\n\n"
            "Selecciona la *localidad* destino:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    return COMVIDEO_LOCALIDAD


async def video_localidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda localidad y pide fotos"""
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
            return COMVIDEO_LOCALIDAD
        user_data[user_id]['localidad_id'] = encontrada[0]
        user_data[user_id]['localidad_nombre'] = encontrada[1]
    
    await update.message.reply_text(
        f"✅ *Localidad:* {user_data[user_id]['localidad_nombre']}\n\n"
        "📸 Envía las *fotos* para el video:\n"
        "• Puedes enviar varias (máximo 50)\n"
        "• Cuando termines, escribe *'listo'*\n"
        "• Para cancelar, escribe *'cancelar'*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    
    return COMVIDEO_FOTOS


async def video_fotos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe fotos/videos y los sube a Cloudinary Comunicación"""
    user_id = update.effective_user.id
    
    # Si es foto o video, subirlo
    if update.message and (update.message.photo or update.message.video):
        try:
            tipo = "foto" if update.message.photo else "video"
            await update.message.reply_text(f"📤 Subiendo {tipo}...", reply_markup=ReplyKeyboardRemove())
            
            if update.message.photo:
                file = await update.message.photo[-1].get_file()
                ext = "jpg"
            else:
                file = await update.message.video.get_file()
                ext = "mp4"
            
            filename = f"com_video_{user_id}_{uuid.uuid4().hex[:8]}.{ext}"
            os.makedirs("uploads/comunicacion", exist_ok=True)
            filepath = f"uploads/comunicacion/{filename}"
            await file.download_to_drive(filepath)
            
            # Subir a Cloudinary Comunicación
            public_id = f"com_video_{user_id}_{uuid.uuid4().hex[:8]}"
            url = subir_foto_comunicacion(filepath, public_id)
            
            # Borrar archivo local
            try:
                os.remove(filepath)
            except:
                pass
            
            if url:
                user_data[user_id]['fotos_urls'].append(url)
                count = len(user_data[user_id]['fotos_urls'])
                await update.message.reply_text(
                    f"✅ {tipo.capitalize()} {count} subida. Envía más o escribe *'listo'*.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text("❌ Error al subir. Intenta de nuevo.")
        except Exception as e:
            logger.error(f"Error subiendo archivo: {e}")
            await update.message.reply_text("❌ Error. Intenta de nuevo.")
        
        return COMVIDEO_FOTOS
    
    # Si es texto
    if update.message and update.message.text:
        texto = update.message.text.strip().lower()
        
        if texto == 'cancelar':
            limpiar_estado(user_id)
            await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        
        if texto == 'listo':
            if len(user_data[user_id]['fotos_urls']) == 0:
                await update.message.reply_text("❌ Envía al menos una foto o video.")
                return COMVIDEO_FOTOS
            
            await update.message.reply_text(
                f"📸 *{len(user_data[user_id]['fotos_urls'])}* archivos recibidos.\n\n"
                "Escribe el *título* del video:\n"
                "(ej: 'Festival del Membrillo 2026')",
                parse_mode=ParseMode.MARKDOWN
            )
            return COMVIDEO_TITULO
    
    return COMVIDEO_FOTOS


async def video_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda título y pregunta si quiere música"""
    user_id = update.effective_user.id
    user_data[user_id]['titulo'] = update.message.text.strip()
    
    keyboard = [["🎵 Agregar música", "➡️ Sin música"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ *Título:* {user_data[user_id]['titulo']}\n\n"
        "🎵 ¿Deseas agregar música de fondo?\n"
        "Puedes enviar un archivo MP3 o continuar sin música.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
    return COMVIDEO_MUSICA

async def video_musica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe archivo de música o salta"""
    user_id = update.effective_user.id
    
    # Si es audio
    if update.message and update.message.audio:
        try:
            file = await update.message.audio.get_file()
            filename = f"musica_{user_id}_{uuid.uuid4().hex[:8]}.mp3"
            os.makedirs("uploads/comunicacion", exist_ok=True)
            filepath = f"uploads/comunicacion/{filename}"
            await file.download_to_drive(filepath)
            user_data[user_id]['musica_path'] = filepath
            await update.message.reply_text("✅ Música recibida.")
        except Exception as e:
            logger.error(f"Error descargando música: {e}")
            await update.message.reply_text("❌ Error. Continuando sin música.")
            user_data[user_id]['musica_path'] = None
    elif update.message and update.message.document:
        try:
            file = await update.message.document.get_file()
            if file.file_path and file.file_path.endswith('.mp3'):
                filename = f"musica_{user_id}_{uuid.uuid4().hex[:8]}.mp3"
                os.makedirs("uploads/comunicacion", exist_ok=True)
                filepath = f"uploads/comunicacion/{filename}"
                await file.download_to_drive(filepath)
                user_data[user_id]['musica_path'] = filepath
                await update.message.reply_text("✅ Música recibida.")
            else:
                await update.message.reply_text("❌ Solo archivos MP3. Continuando sin música.")
                user_data[user_id]['musica_path'] = None
        except:
            user_data[user_id]['musica_path'] = None
    elif update.message and update.message.text:
        texto = update.message.text.strip()
        if texto == "➡️ Sin música":
            user_data[user_id]['musica_path'] = None
        elif texto == "🎵 Agregar música":
            await update.message.reply_text(
                "Envía el archivo MP3 ahora 🎵",
                reply_markup=ReplyKeyboardRemove()
            )
            return COMVIDEO_MUSICA
    
    # Continuar al mensaje
    await update.message.reply_text(
        f"🎵 *Música:* {'Sí' if user_data[user_id].get('musica_path') else 'No'}\n\n"
        "Escribe el *mensaje* que acompañará al video:\n"
        "(ej: 'Gracias a todos los asistentes al Festival')",
        parse_mode=ParseMode.MARKDOWN
    )
    return COMVIDEO_MENSAJE


async def video_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda mensaje, crea video y muestra preview"""
    user_id = update.effective_user.id
    user_data[user_id]['mensaje'] = update.message.text.strip()
    datos = user_data[user_id]
    
    await update.message.reply_text(
        f"⏳ Creando video con {len(datos['fotos_urls'])} imágenes...\n"
        "Esto puede tardar 30-60 segundos.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    titulo = datos.get('titulo', 'Preview')
    musica_path = datos.get('musica_path')
    video_url = crear_video_slideshow(datos['fotos_urls'], titulo, musica_path)
    
    if video_url:
        user_data[user_id]['video_url'] = video_url
        
        await context.bot.send_video(
            chat_id=user_id,
            video=video_url,
            caption=(
                f"🎬 *PREVIEW DEL VIDEO*\n\n"
                f"📍 *Localidad:* {datos.get('localidad_nombre', 'N/A')}\n"
                f"📸 *Imágenes:* {len(datos.get('fotos_urls', []))}\n"
                f"🎯 *Título:* {titulo}\n\n"
                f"¿Enviar a los ciudadanos?"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        
        keyboard = [["✅ CREAR Y ENVIAR", "❌ Cancelar"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("👆 Revisa el preview.\n¿Enviar?", reply_markup=reply_markup)
        return COMVIDEO_CONFIRMAR
    else:
        await update.message.reply_text("❌ Error al crear video. Intenta con más imágenes (mínimo 2).")
        return COMVIDEO_TITULO

async def video_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea el video y lo envía"""
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if texto != "✅ CREAR Y ENVIAR":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    datos = user_data[user_id]
    await update.message.reply_text("⏳ Creando video... Esto puede tardar ~30 segundos.", reply_markup=ReplyKeyboardRemove())
    
    try:
        # Crear video con Cloudinary
        titulo = datos.get('titulo', 'Comunicado Municipal')
        video_url = datos.get('video_url')  # Ya se creó en video_mensaje
        
        if not video_url:
            await update.message.reply_text("❌ Error al crear el video.")
            limpiar_estado(user_id)
            return ConversationHandler.END
        
        # Borrar fotos temporales
        borrar_fotos_temporales(datos['fotos_urls'])
        
        # Enviar a ciudadanos
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
            mensaje = f"🎬 *{titulo}*\n\n{datos.get('mensaje', '')}"
            
            enviados = 0
            for tid in destinatarios:
                try:
                    await bot_app.bot.send_video(
                        chat_id=int(tid),
                        video=video_url,
                        caption=mensaje,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    enviados += 1
                except Exception as e:
                    logger.error(f"Error enviando video a {tid}: {e}")
            
            await update.message.reply_text(
                f"✅ *VIDEO ENVIADO*\n\n"
                f"🎬 *Título:* {titulo}\n"
                f"📍 *Localidad:* {datos.get('localidad_nombre')}\n"
                f"👥 *Destinatarios:* {len(destinatarios)}\n"
                f"✅ *Enviados:* {enviados}\n\n"
                f"📁 El video queda guardado en la nube.",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"❌ Error en video_confirmar: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
    
    limpiar_estado(user_id)
    return ConversationHandler.END
