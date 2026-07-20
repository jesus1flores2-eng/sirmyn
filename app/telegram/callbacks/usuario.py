"""
Maneja la validación final del usuario (aceptar/rechazar reparación)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)

async def usuario_validacion_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja cuando el usuario ACEPTA o RECHAZA la reparación"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    user_id = query.from_user.id
    
    logger.info(f"🔍🔍🔍 USUARIO CALLBACK RECIBIDO: {callback_data}")
    
    # IGNORAR CALLBACKS DE MOTIVOS (que empiezan con usuario_rechazo_motivo_)
    if callback_data.startswith('usuario_rechazo_motivo_'):
        logger.info(f"⏩ Callback de motivo ignorado por usuario_validacion_callback_handler: {callback_data}")
        return
    
    if not callback_data.startswith('usuario_'):
        return
    
    partes = callback_data.split('_')
    if len(partes) < 3:
        await query.answer("❌ Formato inválido", show_alert=True)
        return
    
    accion = partes[1]  # 'aceptar' o 'rechazar'
    reporte_id = int(partes[2])
    
    app = DatabaseManager.get_app()
    with app.app_context():
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
        # USUARIO ACEPTA
        # ============================================================
        if accion == 'aceptar':
            # Cambiar estado a "Aceptado por usuario"
            estado_aceptado = Status.query.filter_by(descripcion="Aceptado por usuario").first()
            if not estado_aceptado:
                estado_aceptado = Status(descripcion="Aceptado por usuario")
                db.session.add(estado_aceptado)
                db.session.commit()
            
            asignacion.status_id = estado_aceptado.id
            asignacion.observaciones = f"✅ Aceptado por el usuario reportante el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            db.session.commit()
            
            await query.edit_message_text(
                text=f"✅ *¡Gracias por tu confirmación!*\n\nEl reporte #{reporte_id} ha sido marcado como RESUELTO.\n\n📞 Para nuevos reportes, usa /start.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ Usuario ACEPTÓ reporte #{reporte_id}")
            
            # Iniciar encuesta de satisfacción
            user_data[user_id] = {
                'modo_encuesta': True,
                'reporte_id': reporte_id,
                'paso_actual': 'calificacion',
                'timestamp': time.time()
            }
            
            # Mostrar encuesta
            keyboard = [
                [
                    InlineKeyboardButton("1️⃣ 😠", callback_data=f"enc_calif_1_{reporte_id}"),
                    InlineKeyboardButton("2️⃣ 😟", callback_data=f"enc_calif_2_{reporte_id}"),
                    InlineKeyboardButton("3️⃣ 😐", callback_data=f"enc_calif_3_{reporte_id}"),
                    InlineKeyboardButton("4️⃣ 😊", callback_data=f"enc_calif_4_{reporte_id}"),
                    InlineKeyboardButton("5️⃣ 😍", callback_data=f"enc_calif_5_{reporte_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="🎉 *ENCUESTA DE SATISFACCIÓN (OPCIONAL)*\n\nCalifica el servicio (1-5):",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        
        # ============================================================
        # USUARIO RECHAZA LA REPARACIÓN (CON NUEVOS CALLBACKS)
        # ============================================================
        elif accion == 'rechazar':
            # Guardar en user_data para el flujo de rechazo
            user_data[user_id] = {
                'modo_rechazo_usuario': True,
                'reporte_id': reporte_id,
                'paso_actual': 'motivo'
            }
    
            # Detectar el tipo de reporte para mostrar motivos personalizados
            if reporte.tipo == "Aseo público":
                keyboard = [
                    [InlineKeyboardButton("🗑️ NO RECOGIERON TODA LA BASURA", callback_data=f"usuario_rechazo_motivo_basura_incompleta_{reporte_id}")],
                    [InlineKeyboardButton("🚛 NO PASÓ EL CAMIÓN", callback_data=f"usuario_rechazo_motivo_no_paso_camion_{reporte_id}")],
                    [InlineKeyboardButton("🧹 DEJARON ESCOMBROS TIRADOS", callback_data=f"usuario_rechazo_motivo_escombros_{reporte_id}")],
                    [InlineKeyboardButton("🤢 MAL OLOR PERSISTE", callback_data=f"usuario_rechazo_motivo_mal_olor_{reporte_id}")],
                    [InlineKeyboardButton("📝 OTRO MOTIVO", callback_data=f"usuario_rechazo_motivo_otro_{reporte_id}")],
                    [InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")]
                ]
            elif reporte.tipo in ["Alumbrado público"]:
                keyboard = [
                    [InlineKeyboardButton("💡 LÁMPARA SIGUE SIN FUNCIONAR", callback_data=f"usuario_rechazo_motivo_lampara_sigue_mal_{reporte_id}")],
                    [InlineKeyboardButton("⚡ CABLES SIGUEN SUELTOS", callback_data=f"usuario_rechazo_motivo_cables_sueltos_{reporte_id}")],
                    [InlineKeyboardButton("🔧 POSTE SIGUE DAÑADO", callback_data=f"usuario_rechazo_motivo_poste_danado_{reporte_id}")],
                    [InlineKeyboardButton("📝 OTRO MOTIVO", callback_data=f"usuario_rechazo_motivo_otro_{reporte_id}")],
                    [InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")]
                ]
            elif reporte.tipo in ["Parques y jardines"]:
                keyboard = [
                    [InlineKeyboardButton("🌳 NO PODARON CORRECTAMENTE", callback_data=f"usuario_rechazo_motivo_no_podaron_{reporte_id}")],
                    [InlineKeyboardButton("🏞️ ÁREA VERDE SIGUE SUCIA", callback_data=f"usuario_rechazo_motivo_area_sucia_{reporte_id}")],
                    [InlineKeyboardButton("💧 NO REGARON LAS PLANTAS", callback_data=f"usuario_rechazo_motivo_no_regaron_{reporte_id}")],
                    [InlineKeyboardButton("🛝 JUEGOS SIGUEN ROTOS", callback_data=f"usuario_rechazo_motivo_juegos_rotos_{reporte_id}")],
                    [InlineKeyboardButton("📝 OTRO MOTIVO", callback_data=f"usuario_rechazo_motivo_otro_{reporte_id}")],
                    [InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")]
                ]
            elif reporte.tipo in ["Seguridad pública"]:
                keyboard = [
                    [InlineKeyboardButton("🚔 NO HUBO RESPUESTA POLICIAL", callback_data=f"usuario_rechazo_motivo_sin_respuesta_{reporte_id}")],
                    [InlineKeyboardButton("👮 NO SE RESOLVIÓ EL PROBLEMA", callback_data=f"usuario_rechazo_motivo_no_resuelto_{reporte_id}")],
                    [InlineKeyboardButton("📝 OTRO MOTIVO", callback_data=f"usuario_rechazo_motivo_otro_{reporte_id}")],
                    [InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")]
                ]
            elif reporte.tipo in ["Bomberos"]:
                keyboard = [
                    [InlineKeyboardButton("🔥 INCENDIO NO CONTROLADO", callback_data=f"usuario_rechazo_motivo_incendio_{reporte_id}")],
                    [InlineKeyboardButton("🚒 NO LLEGÓ LA UNIDAD", callback_data=f"usuario_rechazo_motivo_no_llego_{reporte_id}")],
                    [InlineKeyboardButton("⚠️ FALTA ATENCIÓN", callback_data=f"usuario_rechazo_motivo_falta_atencion_{reporte_id}")],
                    [InlineKeyboardButton("📝 OTRO MOTIVO", callback_data=f"usuario_rechazo_motivo_otro_{reporte_id}")],
                    [InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")]
                ]
            else:
                # Agua, Drenaje y otros
                keyboard = [
                    [InlineKeyboardButton("🚫 PROBLEMA PERSISTE IGUAL", callback_data=f"usuario_rechazo_motivo_problema_persiste_{reporte_id}")],
                    [InlineKeyboardButton("🔧 REPARACIÓN INCOMPLETA", callback_data=f"usuario_rechazo_motivo_reparacion_incompleta_{reporte_id}")],
                    [InlineKeyboardButton("🕳️ NO TERMINARON DE TAPAR", callback_data=f"usuario_rechazo_motivo_no_termino_tapar_{reporte_id}")],
                    [InlineKeyboardButton("⚠️ CAUSARON OTRO PROBLEMA", callback_data=f"usuario_rechazo_motivo_causo_otro_{reporte_id}")],
                    [InlineKeyboardButton("📝 OTRO MOTIVO", callback_data=f"usuario_rechazo_motivo_otro_{reporte_id}")],
                    [InlineKeyboardButton("↩️ Volver", callback_data=f"rech_volver_{reporte_id}")]
                ]

            reply_markup = InlineKeyboardMarkup(keyboard)
    
            # ⭐ CORRECCIÓN: Usar reply_text en lugar de edit_message_text
            await query.message.reply_text(
                text="🚨 *FORMULARIO DE RECHAZO*\n\n"
                     "Selecciona el motivo principal por el que rechazas la reparación:\n\n"
                     "📌 *Si seleccionas 'OTRO MOTIVO', podrás escribir tu propio texto.*\n"
                     "📌 *Si te equivocaste, presiona '↩️ Volver' para regresar.*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    
            logger.info(f"❌ Usuario inició rechazo para reporte #{reporte_id}")
            await query.answer("Selecciona un motivo o vuelve atrás", show_alert=False)
