from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado
from app.services.db_manager import DatabaseManager
import logging, time

logger = logging.getLogger(__name__)

async def registrar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🔐 *VINCULACIÓN DE CUENTA - SISTEMA SIRMYN*\n\n"
            "📋 *Para vincular tu cuenta necesitas:*\n"
            "1. Tu *username* del sistema web\n\n"
            "💡 *Ejemplos:*\n"
            "• `/registrar juan_perez`\n"
            "• `/registrar jefe_tecnico`\n"
            "• `/registrar presidente`\n\n"
            "⚠️ *Nota:* Tu cuenta debe estar previamente registrada por el administrador.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    codigo = ' '.join(args).strip()
    logger.info(f"🔍 Usuario {user_id} intenta registrar: '{codigo}'")
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            
            usuario = User.query.filter_by(username=codigo).first()
            if not usuario and len(codigo) >= 4:
                usuario = User.query.filter(User.nombre.ilike(f"%{codigo}%")).first()
            
            if not usuario:
                await update.message.reply_text(
                    f"❌ *USUARIO NO ENCONTRADO*\n\n"
                    f"No se encontró ningún usuario con: *{codigo}*\n\n"
                    "🔍 *Posibles causas:*\n"
                    "• El username es incorrecto\n"
                    "• Tu cuenta no está registrada en el sistema\n"
                    "• Hay error de escritura\n\n"
                    "💡 *Solución:*\n"
                    "1. Verifica el username exacto\n"
                    "2. Contacta al administrador para registrarte",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                return ConversationHandler.END
            
            if usuario.telegram_id:
                if str(usuario.telegram_id) == str(user_id):
                    await update.message.reply_text(
                        f"ℹ️ *YA ESTÁS VINCULADO*\n\n"
                        f"👤 *Nombre:* {usuario.nombre}\n"
                        f"📋 *Username:* `{usuario.username}`\n"
                        f"📱 *Estado:* ✅ **VINCULADO**\n\n"
                        f"*Usa /miestado para ver tus reportes.*",
                        parse_mode="Markdown",
                        reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    await update.message.reply_text(
                        "⚠️ *CUENTA YA VINCULADA*\n\n"
                        "Esta cuenta ya tiene otra cuenta de Telegram vinculada.\n\n"
                        "📞 *Para cambiar:* Contacta al administrador del sistema.",
                        parse_mode="Markdown",
                        reply_markup=ReplyKeyboardRemove()
                    )
                return ConversationHandler.END
            
            user_data[user_id] = {
                "registro_usuario_id": usuario.id,
                "registro_nombre": usuario.nombre,
                "registro_username": usuario.username,
                "registro_area": usuario.area,
                "registro_rol": usuario.rol_especifico,
                "registro_team": usuario.team.nombre if usuario.team else None,
                "registro_timestamp": time.time()
            }
            
            keyboard = [["✅ CONFIRMAR VINCULACIÓN", "❌ CANCELAR"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            area_display = usuario.area.replace('_', ' ').title() if usuario.area else 'N/A'
            rol_display = usuario.rol_especifico.replace('_', ' ').title() if usuario.rol_especifico else 'N/A'
            team_display = usuario.team.nombre if usuario.team else 'Sin asignar'
            
            mensaje = (
                f"🔐 *CONFIRMACIÓN DE VINCULACIÓN*\n\n"
                f"*👤 Nombre:* {usuario.nombre}\n"
                f"*🔑 Username:* `{usuario.username}`\n"
                f"*🏛️ Departamento:* {area_display}\n"
                f"*🎯 Rol:* {rol_display}\n"
                f"*👷 Equipo:* {team_display}\n\n"
                f"*📝 ¿CONFIRMAS LA VINCULACIÓN?*\n\n"
                f"⚠️ *Al confirmar, recibirás notificaciones automáticas*"
            )
            
            await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=reply_markup)
            return REGISTRO_CONFIRMACION
            
    except Exception as e:
        logger.error(f"❌ Error en /registrar: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ *ERROR DEL SISTEMA*\n\n"
            "Ocurrió un error al procesar tu solicitud.\n\n"
            "Por favor, intenta nuevamente o contacta al administrador.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


async def registro_confirmacion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    respuesta = update.message.text.strip().lower()
    
    if user_id not in user_data or "registro_usuario_id" not in user_data.get(user_id, {}):
        await update.message.reply_text(
            "❌ *SESIÓN EXPIRADA*\n\n"
            "La sesión de vinculación ha expirado.\n\n"
            "🔄 *Por favor:* Usa `/registrar` nuevamente.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    respuestas_afirmativas = ["sí", "si", "confirmar", "✅ confirmar vinculación", "aceptar", "ok"]
    respuestas_negativas = ["no", "cancelar", "❌ cancelar", "rechazar"]
    
    if any(p in respuesta for p in respuestas_negativas):
        await update.message.reply_text(
            "❌ *VINCULACIÓN CANCELADA*\n\n"
            "No se ha vinculado ninguna cuenta a tu Telegram.\n\n"
            "📌 *Puedes:* Usar `/registrar` cuando desees vincular.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    if not any(p in respuesta for p in respuestas_afirmativas):
        await update.message.reply_text(
            "🤔 *RESPUESTA NO CLARA*\n\n"
            "Por favor, selecciona una opción del teclado:\n"
            "• *'✅ CONFIRMAR VINCULACIÓN'* para continuar\n"
            "• *'❌ CANCELAR'* para cancelar el registro",
            parse_mode="Markdown"
        )
        return REGISTRO_CONFIRMACION
    
    datos = user_data.get(user_id, {})
    usuario_id = datos.get("registro_usuario_id")
    
    if not usuario_id:
        await update.message.reply_text(
            "❌ *SESIÓN EXPIRADA*\n\n"
            "La sesión de vinculación ha expirado.\n\n"
            "🔄 *Por favor:* Usa `/registrar` nuevamente.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            from app.extensions import db
            
            usuario = User.query.get(usuario_id)
            if not usuario:
                await update.message.reply_text(
                    "❌ *ERROR: USUARIO NO ENCONTRADO*\n\n"
                    "El usuario ya no existe en el sistema.\n"
                    "Contacta al administrador.",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
            
            if usuario.telegram_id:
                await update.message.reply_text(
                    "ℹ️ *YA ESTÁ VINCULADO*\n\n"
                    "Esta cuenta ya tiene un Telegram vinculado.",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
            
            usuario.telegram_id = user_id
            db.session.commit()
            
            await update.message.reply_text(
                f"🎉 *¡VINCULACIÓN EXITOSA!*\n\n"
                f"*👤 Nombre:* {usuario.nombre}\n"
                f"*📋 Username:* `{usuario.username}`\n"
                f"*📱 Telegram vinculado:* @{update.effective_user.username or 'N/A'}\n\n"
                f"*🔔 Recibirás notificaciones de reportes asignados.*\n\n"
                f"*📊 Comandos disponibles:*\n"
                f"• `/miestado` - Ver tus reportes\n"
                f"• `/dashboard` - Panel según tu rol\n"
                f"• `/presidencia` - Panel presidencial\n"
                f"• `/ayuda` - Todos los comandos",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            
            try:
                from app.services.notification_service import notificar_admin_vinculacion_original
                await notificar_admin_vinculacion_original(
                    usuario=usuario,
                    telegram_user_id=user_id,
                    telegram_username=update.effective_user.username,
                    context=context
                )
            except Exception as admin_error:
                logger.error(f"⚠️ Error notificando admin: {admin_error}")
            
            limpiar_estado(user_id)
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"❌ Error en registro_confirmacion_handler: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *ERROR DE VINCULACIÓN*\n\n"
            "Ocurrió un error al vincular tu cuenta.\n\n"
            "Por favor, intenta nuevamente con `/registrar`.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
