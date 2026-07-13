"""
Maneja el flujo de rechazo de usuario (simplificado)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data, limpiar_estado
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.status import Status
from app.extensions import db
from app.telegram.keyboards import construir_botones_reporte
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================
# MANEJAR SELECCIÓN DE MOTIVO DE RECHAZO
# ============================================================

async def rechazo_motivo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja la selección de un motivo de rechazo por parte del usuario.
    Si es "OTRO MOTIVO", pide texto; si es predefinido, ejecuta rechazo directo.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if not callback_data.startswith('rech_motivo_'):
        return
    
    # Extraer reporte_id y motivo_key
    partes = callback_data.split('_')
    reporte_id = int(partes[-1])
    motivo_key = partes[1]  # 'problema_persiste', 'reparacion_incompleta', etc.
    
    # Diccionario de motivos predefinidos
    motivos_predefinidos = {
        'problema_persiste': 'El problema persiste igual, no se resolvió nada.',
        'reparacion_incompleta': 'La reparación está incompleta, faltan cosas por hacer.',
        'no_termino_tapar': 'No terminaron de tapar el hueco / zanja.',
        'causo_otro': 'La reparación causó otro problema adicional.'
    }
    
    # Si es "otro", pedir texto personalizado
    if motivo_key == 'otro':
        user_data[query.from_user.id] = {
            'modo_rechazo_usuario': True,
            'reporte_id': reporte_id,
            'paso_actual': 'escribir_motivo'
        }
        await query.edit_message_text(
            text="✍️ *Escribe tu motivo de rechazo:*\n\n"
                 "Describe por qué rechazas la reparación.\n"
                 "(Máximo 200 caracteres)",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Motivo predefinido
    motivo = motivos_predefinidos.get(motivo_key, 'Motivo no especificado')
    
    # Ejecutar rechazo con el motivo
    await ejecutar_rechazo_usuario(query, context, reporte_id, motivo)


# ============================================================
# MANEJAR "OTRO MOTIVO" (TEXTO PERSONALIZADO)
# ============================================================

async def rechazo_otro_motivo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recibe el texto personalizado del usuario cuando selecciona "OTRO MOTIVO".
    """
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    
    if not texto:
        await update.message.reply_text("❌ El motivo no puede estar vacío. Escribe el motivo o usa /cancelar.")
        return
    
    # Verificar que esté en modo rechazo y reporte_id
    datos = user_data.get(user_id, {})
    reporte_id = datos.get('reporte_id')
    
    if not reporte_id:
        await update.message.reply_text("❌ No se encontró el reporte. Usa /start para comenzar.")
        limpiar_estado(user_id)
        return
    
    # Ejecutar rechazo con el texto personalizado
    # Simulamos un query para reutilizar la función
    class FakeQuery:
        def __init__(self, user_id):
            self.from_user = type('obj', (object,), {'id': user_id})()
        async def edit_message_text(self, *args, **kwargs):
            pass
        async def answer(self, *args, **kwargs):
            pass
    
    fake_query = FakeQuery(user_id)
    await ejecutar_rechazo_usuario(fake_query, context, reporte_id, texto)


# ============================================================
# EJECUTAR RECHAZO DE USUARIO (ACCIÓN PRINCIPAL) - CORREGIDO
# ============================================================

async def ejecutar_rechazo_usuario(query, context, reporte_id, motivo):
    """
    Ejecuta el rechazo del usuario: cambia estado a "En proceso" (ID 2), notifica a cuadrilla y responsable.
    """
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.services.notification_service import notificar_responsable_rechazo_usuario
            
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return
            
            usuario_reportante = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            nombre_reportante = usuario_reportante.nombre if usuario_reportante else "Usuario reportante"
            
            # Obtener la asignación actual
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            if not asignacion or not asignacion.team_id:
                await query.edit_message_text("❌ No hay cuadrilla asignada a este reporte.")
                return
            
            # ⭐ CAMBIAR ESTADO A "En proceso" (ID 2 directamente)
            estado_en_proceso = Status.query.get(2)  # Usa el ID exacto que ya existe en tu BD
            if not estado_en_proceso:
                # Si por alguna razón no existe el ID 2, buscarlo por descripción
                estado_en_proceso = Status.query.filter_by(descripcion="En proceso").first()
                if not estado_en_proceso:
                    estado_en_proceso = Status(descripcion="En proceso")
                    db.session.add(estado_en_proceso)
                    db.session.commit()
                    logger.info(f"✅ Estado 'En proceso' creado con ID {estado_en_proceso.id}")
            
            # Asignar el estado a la asignación
            asignacion.status_id = estado_en_proceso.id
            asignacion.observaciones = f"Rechazado por usuario {nombre_reportante} el {datetime.now().strftime('%d/%m/%Y %H:%M')}. Motivo: {motivo}"
            db.session.commit()
            
            logger.info(f"✅ [RECHAZO USUARIO] Estado cambiado a 'En proceso' (ID: {estado_en_proceso.id}) para reporte {reporte_id}")
            logger.info(f"✅ [RECHAZO USUARIO] Asignación {asignacion.id} actualizada -> status_id {asignacion.status_id}")
            
            # ============================================================
            # NOTIFICAR A LA CUADRILLA (CON MENSAJE COMPLETO Y BOTÓN REPARACIÓN)
            # ============================================================
            cuadrilla_id = asignacion.team_id
            bot = context.bot
            
            calle_nombre = reporte.calle.nombre if reporte.calle else 'N/D'
            localidad_nombre = reporte.localidad.nombre if reporte.localidad else 'N/D'
            
            mensaje_base = (
                f"🚨 *REPORTE RECHAZADO POR USUARIO - REQUIERE CORRECCIÓN*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📋 *Folio:* #{reporte.id}\n"
                f"📍 *Ubicación:* {calle_nombre} #{reporte.numero}, {localidad_nombre}\n"
                f"📞 *Reportante:* {reporte.reportante}\n"
                f"🔧 *Tipo:* {reporte.tipo} - {reporte.subtipo}\n"
                f"📄 *Descripción:* {reporte.descripcion_problema[:150]}...\n\n"
            )
            
            # Agregar evidencia si existe
            if reporte.evidencia:
                from app.services.notification_service import construir_enlace_evidencia
                enlace, _ = construir_enlace_evidencia(reporte.evidencia, "evidencia_usuario")
                mensaje_base += f"📎 *Evidencia:* {enlace}\n\n"
            
            # Agregar mapa si hay coordenadas
            if reporte.latitud and reporte.longitud:
                maps_url = f"https://www.google.com/maps?q={reporte.latitud},{reporte.longitud}"
                mensaje_base += f"📍 *Ver en mapa:* [Google Maps]({maps_url})\n\n"
            
            mensaje_base += (
                f"❌ *RECHAZADO POR USUARIO*\n"
                f"*Motivo:* {motivo}\n\n"
                f"*📌 Acción requerida:* Corrige el trabajo y vuelve a subir evidencia.\n\n"
                f"*📋 Acciones rápidas:*"
            )
            
            # Notificar a la cuadrilla
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id, is_active=True).all()
            notificados = 0
            for usuario in usuarios_cuadrilla:
                if usuario.telegram_id:
                    try:
                        reply_markup = construir_botones_reporte(
                            reporte_id,
                            confirmado=True,
                            problema_reportado=False,
                            context=context,
                            user_id=usuario.telegram_id
                        )
                        await bot.send_message(
                            chat_id=int(usuario.telegram_id),
                            text=mensaje_base,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        notificados += 1
                        logger.info(f"✅ Rechazo enviado a {usuario.nombre}")
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario.nombre}: {e}")
            
            # ============================================================
            # NOTIFICAR AL RESPONSABLE (SUPERVISOR/DIRECTOR)
            # ============================================================
            await notificar_responsable_rechazo_usuario(reporte_id, motivo, nombre_reportante)
            
            # ============================================================
            # CONFIRMAR AL USUARIO
            # ============================================================
            await query.edit_message_text(
                f"✅ *Rechazo enviado correctamente*\n\n"
                f"📋 *Reporte:* #{reporte.id}\n"
                f"📝 *Motivo:* {motivo}\n\n"
                f"*📌 La cuadrilla ha sido notificada para corregir el trabajo.*\n"
                f"*Recibirás una nueva notificación cuando la reparación sea reenviada.*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ Usuario {nombre_reportante} rechazó reporte #{reporte_id}, estado cambiado a 'En proceso', notificados {notificados} miembros de cuadrilla")
            
    except Exception as e:
        logger.error(f"❌ Error en ejecutar_rechazo_usuario: {e}")
        await query.edit_message_text("❌ Error al procesar el rechazo. Intenta nuevamente.")
    
    finally:
        limpiar_estado(query.from_user.id)


# ============================================================
# MANEJAR VOLVER DESDE RECHAZO (BOTÓN "↩️ Volver")
# ============================================================

async def rechazo_volver_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja el botón "↩️ Volver" en el flujo de rechazo del usuario.
    Regresa al mensaje de validación original.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if not callback_data.startswith('rech_volver_'):
        return
    
    reporte_id = int(callback_data.split('_')[-1])
    user_id = query.from_user.id
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.team import Team
            
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                limpiar_estado(user_id)
                return
            
            # Obtener la asignación y la cuadrilla
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            cuadrilla = Team.query.get(asignacion.team_id) if asignacion else None
            
            # ⭐ RECONSTRUIR EL MENSAJE DE VALIDACIÓN ORIGINAL
            mensaje = f"""
✅ *¡TU REPORTE HA SIDO ATENDIDO!*

📋 *Folio:* #{reporte.id}
📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}
🔧 *Problema:* {reporte.tipo} - {reporte.subtipo}
👷 *Cuadrilla:* {cuadrilla.nombre if cuadrilla else 'N/D'}

*¿La reparación fue satisfactoria?*

⚠️ Tienes 48 horas para responder. Si no respondes, se considerará aceptada automáticamente.
"""
            keyboard = [
                [
                    InlineKeyboardButton("✅ Sí, está resuelto", callback_data=f"usuario_aceptar_{reporte.id}"),
                    InlineKeyboardButton("❌ No, persiste el problema", callback_data=f"usuario_rechazar_{reporte.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            # ⭐ LIMPIAR ESTADO DE RECHAZO
            limpiar_estado(user_id)
            
            await query.answer("↩️ Volviendo a la validación", show_alert=False)
            logger.info(f"↩️ Usuario volvió desde rechazo al reporte {reporte_id}")
            
    except Exception as e:
        logger.error(f"❌ Error en rechazo_volver_handler: {e}")
        await query.answer("❌ Error al volver", show_alert=True)
