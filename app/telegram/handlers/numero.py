from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from app.telegram.states import *
from app.telegram.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
from app.services.db_manager import DatabaseManager
import logging

logger = logging.getLogger(__name__)

async def numero_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    numero = update.message.text.strip()
    user_data[user_id]["numero"] = numero
    
    # Obtener datos de ubicación y tipo
    loc_id = user_data[user_id].get("localidad_id")
    calle_id = user_data[user_id].get("calle_id")
    tipo_actual = user_data[user_id].get("tipo")
    subtipo_actual = user_data[user_id].get("subtipo", "")
    
    duplicado = False
    
    # Si tenemos los datos necesarios, verificar duplicados
    if loc_id and calle_id and tipo_actual:
        try:
            app = DatabaseManager.get_app()
            with app.app_context():
                from app.models.report import Report, Assignment
                from app.models.user import User
                from app.models.team import Team
                from app.models.status import Status
                
                # Buscar reporte exacto (misma dirección y tipo)
                existente_exacto = Report.query.filter_by(
                    localidad_id=loc_id,
                    calle_id=calle_id,
                    numero=numero,
                    tipo=tipo_actual,
                    subtipo=subtipo_actual
                ).first()
                
                if existente_exacto:
                    duplicado = True
                    # Guardar info del duplicado
                    asignacion = Assignment.query.filter_by(
                        report_id=existente_exacto.id
                    ).order_by(Assignment.timestamp.desc()).first()
                    
                    estado = asignacion.status if asignacion else None
                    cuadrilla = asignacion.team if asignacion else None
                    usuario_cuadrilla = None
                    if cuadrilla:
                        usuario = User.query.filter_by(team_id=cuadrilla.id).first()
                        usuario_cuadrilla = usuario.nombre if usuario else None
                    
                    user_data[user_id]["posible_duplicado_id"] = existente_exacto.id
                    user_data[user_id]["duplicado_info"] = {
                        "folio": existente_exacto.id,
                        "estado": estado.descripcion if estado else "Sin estado",
                        "cuadrilla": cuadrilla.nombre if cuadrilla else "Sin asignar",
                        "atendiendo": usuario_cuadrilla or "No asignado",
                        "fecha": existente_exacto.timestamp.strftime("%d/%m/%Y %H:%M") if existente_exacto.timestamp else "N/D"
                    }
        except Exception as e:
            logger.error(f"Error verificando duplicados: {e}")
            duplicado = False
    
    if duplicado:
        info = user_data[user_id]["duplicado_info"]
        mensaje = (
            f"⚠️ *Ya existe un reporte IDENTICO activo*\n\n"
            f"📋 *Folio:* #{info['folio']}\n"
            f"🏷️ *Estado:* {info['estado']}\n"
            f"🛠️ *Cuadrilla:* {info['cuadrilla']}\n"
            f"👷 *Atendiendo:* {info['atendiendo']}\n"
            f"⏰ *Fecha:* {info['fecha']}\n\n"
            f"¿Deseas continuar con un nuevo reporte?"
        )
        keyboard = [["✅ Continuar con nuevo reporte", "❌ Cancelar", "📋 Ver detalles"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=reply_markup)
        return DUPLICADO_CONFIRMACION
    else:
        localidad_nombre = user_data[user_id].get("localidad_nombre", "Localidad no especificada")
        calle_nombre = user_data[user_id].get("calle_nombre", "Calle no especificada")
        
        await update.message.reply_text(
            f"✅ *Ubicación confirmada:*\n\n"
            f"📍 *Localidad:* {localidad_nombre}\n"
            f"🛣️ *Calle:* {calle_nombre}\n"
            f"🔢 *Número:* {numero}\n\n"
            f"*¿Entre qué calles está?* (Ej: 'Entre Morelos e Hidalgo' o 'No'):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTRE_CALLES

async def duplicado_confirmacion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    opcion = update.message.text.lower()
    
    if "continuar" in opcion or "✅" in opcion:
        await update.message.reply_text(
            "¿Entre qué calles está?",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTRE_CALLES
    elif "detalles" in opcion or "ver" in opcion or "📋" in opcion:
        info = user_data[user_id].get("duplicado_info", {})
        mensaje = (
            f"📋 *Detalles del reporte #{info.get('folio', 'N/A')}*\n\n"
            f"🏷️ *Estado:* {info.get('estado', 'N/A')}\n"
            f"🛠️ *Cuadrilla:* {info.get('cuadrilla', 'Sin asignar')}\n"
            f"👷 *Atendiendo:* {info.get('atendiendo', 'No asignado')}\n"
            f"📅 *Fecha:* {info.get('fecha', 'N/D')}\n\n"
            f"¿Deseas continuar con un nuevo reporte?"
        )
        keyboard = [["✅ Continuar", "❌ Cancelar"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=reply_markup)
        return DUPLICADO_CONFIRMACION
    else:
        await update.message.reply_text(
            "❌ Reporte cancelado. Usa /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END

async def consulta_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe ID para consulta"""
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    reporte_id = update.message.text.strip()
    
    user_data[user_id] = {"reporte_id_consulta": reporte_id}
    
    await update.message.reply_text(
        "🔐 Para verificar tu identidad, escribe el nombre de quien levantó el reporte.",
        reply_markup=ReplyKeyboardRemove()
    )
    return VERIFICAR_REPORTANTE

async def verificar_reportante_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica reportante y muestra estado"""
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    nombre = update.message.text.strip().lower()
    reporte_id = user_data[user_id].get("reporte_id_consulta")
    
    if not reporte_id:
        await update.message.reply_text(
            "❌ No hay un reporte en consulta. Usa /start para comenzar.",
            reply_markup=ReplyKeyboardRemove()
        )
        limpiar_estado(user_id)
        return ConversationHandler.END
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment, Localidad, Calle
            from app.models.user import User
            from app.models.team import Team
            from app.models.status import Status
            
            rep = Report.query.filter_by(id=reporte_id).first()
            
            if rep:
                if (rep.reportante or "").strip().lower() == nombre:
                    asignacion_reporte = Assignment.query.filter_by(
                        report_id=rep.id
                    ).order_by(Assignment.timestamp.desc()).first()
                    
                    if asignacion_reporte:
                        estado_desc = asignacion_reporte.status.descripcion if asignacion_reporte.status else "Sin estatus"
                        cuadrilla = asignacion_reporte.team.nombre if asignacion_reporte.team else "Sin cuadrilla asignada"
                        observaciones = asignacion_reporte.observaciones or "Sin observaciones"
                        usuario = User.query.filter_by(team_id=asignacion_reporte.team_id).first()
                        nombre_usuario = usuario.nombre if usuario else "Sin usuario asignado"
                        calle = Calle.query.get(rep.calle_id)
                        loc = Localidad.query.get(rep.localidad_id)
                        
                        mensaje = (
                            f"📋 *Estado del Reporte #{rep.id}*\n\n"
                            f"📍 *Dirección:* {calle.nombre if calle else 'N/D'} #{rep.numero}, "
                            f"{loc.nombre if loc else 'N/D'}\n"
                            f"👤 *Reportante:* {rep.reportante}\n"
                            f"🛠 *Cuadrilla:* {cuadrilla}\n"
                            f"👷 *Atendiendo:* {nombre_usuario}\n"
                            f"📌 *Estatus:* {estado_desc}\n"
                            f"📝 *Observaciones:* {observaciones}"
                        )
                    else:
                        mensaje = f"⚠️ Tu reporte #{rep.id} aún no ha sido asignado a ninguna cuadrilla."
                    
                    await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
                else:
                    await update.message.reply_text("❌ El nombre no coincide con quien levantó el reporte.", reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text("❌ No se encontró el folio.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logger.error(f"Error en verificar_reportante_handler: {e}")
        await update.message.reply_text("❌ Error al consultar el reporte. Intenta más tarde.", reply_markup=ReplyKeyboardRemove())
    
    limpiar_estado(user_id)
    return ConversationHandler.END
