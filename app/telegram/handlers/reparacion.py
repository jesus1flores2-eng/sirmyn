"""
Maneja el flujo de subida de evidencia de reparación por parte de la cuadrilla
"""
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from app.telegram.states import *
from app.telegram.utils import user_data
from app.services.db_manager import DatabaseManager
from app.models.report import Report, Assignment
from app.models.user import User
from app.models.team import Team
from app.models.status import Status
from app.extensions import db
from app.telegram.keyboards import obtener_carpeta_departamento
from datetime import datetime
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


async def manejar_modo_reparacion(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Maneja el flujo de subida de evidencia de reparación"""
    if user_id not in user_data or not user_data[user_id].get('modo_reparacion'):
        return

    datos = user_data[user_id]
    paso = datos.get('paso')

    # Obtener carpeta del departamento
    app = DatabaseManager.get_app()
    reporte_id = datos.get('reporte_id')
    if reporte_id:
        with app.app_context():
            reporte = Report.query.get(reporte_id)
            if reporte:
                carpeta_departamento = obtener_carpeta_departamento(reporte.tipo)
            else:
                carpeta_departamento = "general"
    else:
        carpeta_departamento = "general"

    # Ruta base: app/static/evidencias/{carpeta_departamento}/
    static_folder = app.config.get('STATIC_FOLDER', 'app/static')
    base_path = Path(static_folder) / 'evidencias' / carpeta_departamento

    # ============================================================
    # PASO 1: EVIDENCIA DE TRABAJO
    # ============================================================
    if paso == 'evidencia':
        # Si es texto
        if update.message.text:
            texto = update.message.text.lower()

            if texto == 'cancelar':
                claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id']
                for clave in claves:
                    user_data[user_id].pop(clave, None)

                mensaje = (
                    "❌ *Reparación cancelada.*\n\n"
                    "No se ha guardado ninguna evidencia.\n\n"
                    "📌 *Para volver a intentarlo:*\n"
                    "1. Ve al mensaje original del reporte\n"
                    "2. Presiona el botón *'🔧 Subir evidencia reparación'*\n"
                    "3. Sigue el flujo nuevamente\n\n"
                    "💡 *Recuerda:* Puedes cancelar en cualquier momento escribiendo 'cancelar'."
                )

                await update.message.reply_text(
                    mensaje,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardRemove()
                )
                return

            if texto == 'listo':
                if not datos.get('evidencias'):
                    await update.message.reply_text(
                        "❌ No has enviado evidencia. Envía al menos una foto/video o escribe 'cancelar'.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                datos['paso'] = 'materiales'
                user_data[user_id] = datos
                await update.message.reply_text(
                    "📦 *Materiales utilizados:*\n\n"
                    "Envía una foto de los materiales usados o escribe la lista (ej: '5 tubos PVC, 3 codos'):",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardRemove()
                )
                return

        # Si es foto/video
        if update.message.photo or update.message.video:
            try:
                with app.app_context():
                    carpeta = base_path / 'cuadrilla'
                    carpeta.mkdir(parents=True, exist_ok=True)

                    if update.message.photo:
                        file = await update.message.photo[-1].get_file()
                        extension = 'jpg'
                    else:
                        file = await update.message.video.get_file()
                        extension = 'mp4'

                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    filename = f"evidencia_{datos['reporte_id']}_{timestamp}_{uuid.uuid4().hex[:4]}.{extension}"
                    filepath = carpeta / filename
                    await file.download_to_drive(filepath)

                    # Guardar ruta relativa: evidencias/{area}/cuadrilla/filename
                    ruta_relativa = f"evidencias/{carpeta_departamento}/cuadrilla/{filename}"

                    if 'evidencias' not in datos:
                        datos['evidencias'] = []
                    datos['evidencias'].append(ruta_relativa)
                    user_data[user_id] = datos

                    await update.message.reply_text(
                        f"✅ Evidencia {len(datos['evidencias'])} recibida. Envía más o escribe 'listo'.",
                        parse_mode=ParseMode.MARKDOWN
                    )
            except Exception as e:
                logger.error(f"❌ Error guardando evidencia: {e}")
                await update.message.reply_text(
                    "❌ Error al guardar la evidencia. Intenta de nuevo.",
                    parse_mode=ParseMode.MARKDOWN
                )
        return

    # ============================================================
    # PASO 2: MATERIALES
    # ============================================================
    elif paso == 'materiales':
        # Si es foto
        if update.message.photo:
            try:
                with app.app_context():
                    carpeta = base_path / 'materiales'
                    carpeta.mkdir(parents=True, exist_ok=True)

                    file = await update.message.photo[-1].get_file()
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    filename = f"materiales_{datos['reporte_id']}_{timestamp}.jpg"
                    filepath = carpeta / filename
                    await file.download_to_drive(filepath)

                    ruta_relativa = f"evidencias/{carpeta_departamento}/materiales_utilizados/{filename}"
                    datos['materiales'] = ruta_relativa
                    user_data[user_id] = datos
            except Exception as e:
                logger.error(f"❌ Error guardando materiales: {e}")
                await update.message.reply_text(
                    "❌ Error al guardar la foto. Escribe la lista de materiales.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        # Si es texto
        elif update.message.text:
            texto = update.message.text.strip()
            if texto.lower() == 'cancelar':
                claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id']
                for clave in claves:
                    user_data[user_id].pop(clave, None)

                await update.message.reply_text(
                    "❌ *Reparación cancelada.*\n\n"
                    "📌 *Para volver a intentarlo:*\n"
                    "Presiona el botón *'🔧 Subir evidencia reparación'* en el mensaje original del reporte.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=ReplyKeyboardRemove()
                )
                return

            datos['materiales'] = texto
            user_data[user_id] = datos

        datos['paso'] = 'comentario'
        user_data[user_id] = datos
        await update.message.reply_text(
            "💬 *Comentarios adicionales:*\n\n"
            "Describe el trabajo realizado o cualquier observación (opcional, escribe 'omitir' para saltar):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # ============================================================
    # PASO 3: COMENTARIO
    # ============================================================
    elif paso == 'comentario':
        texto = update.message.text.strip()

        if texto.lower() == 'cancelar':
            claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id']
            for clave in claves:
                user_data[user_id].pop(clave, None)

            await update.message.reply_text(
                "❌ *Reparación cancelada.*\n\n"
                "📌 *Para volver a intentarlo:*\n"
                "Presiona el botón *'🔧 Subir evidencia reparación'* en el mensaje original del reporte.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            return

        if texto.lower() != 'omitir':
            datos['comentario'] = texto
        else:
            datos['comentario'] = ''

        user_data[user_id] = datos

        # Mostrar resumen
        mensaje = (
            f"📋 *Resumen de reparación*\n\n"
            f"📷 Evidencias: {len(datos.get('evidencias', []))}\n"
        )
        if isinstance(datos.get('materiales'), str) and datos['materiales'].endswith(('.jpg', '.jpeg', '.png')):
            mensaje += "📦 Materiales: Foto adjunta\n"
        else:
            mensaje += f"📦 Materiales: {datos.get('materiales', 'No especificado')}\n"
        mensaje += f"💬 Comentarios: {datos.get('comentario', 'Sin comentarios')}\n\n"
        mensaje += "¿Guardar y enviar a revisión?"

        keyboard = [["✅ Sí, guardar"], ["❌ Cancelar"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            mensaje,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        datos['paso'] = 'confirmacion'
        user_data[user_id] = datos
        return

    # ============================================================
    # PASO 4: CONFIRMACIÓN
    # ============================================================
    elif paso == 'confirmacion':
        if update.message.text == "✅ Sí, guardar":
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

                    await update.message.reply_text(
                        "✅ ¡Reparación guardada! Enviada a revisión.",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    await update.message.reply_text(
                        "❌ Error: no se encontró la asignación.",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=ReplyKeyboardRemove()
                    )
        else:
            await update.message.reply_text(
                "❌ *Reparación cancelada.*\n\n"
                "📌 *Para volver a intentarlo:*\n"
                "Presiona el botón *'🔧 Subir evidencia reparación'* en el mensaje original del reporte.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )

        if user_id in user_data:
            claves = ['modo_reparacion', 'paso', 'evidencias', 'materiales', 'comentario', 'asignacion_id', 'reporte_id']
            for clave in claves:
                user_data[user_id].pop(clave, None)
        return

async def manejar_media_reparacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler específico para fotos/videos durante el modo reparación.
    Si el usuario está en modo_reparacion, redirige a manejar_modo_reparacion.
    Si no, muestra un mensaje informativo.
    """
    user_id = update.effective_user.id

    if user_id in user_data and user_data[user_id].get('modo_reparacion'):
        logger.info(f"📸 [REPARACION] Usuario {user_id} envió foto/video en modo reparación")
        await manejar_modo_reparacion(update, context, user_id)
        return

    logger.warning(f"⚠️ [REPARACION] Usuario {user_id} envió foto pero no está en modo reparación")
    await update.message.reply_text(
        "📸 *No estás en modo reparación.*\n\n"
        "Si deseas subir evidencia de reparación:\n"
        "1. Ve al mensaje original del reporte\n"
        "2. Presiona el botón *'🔧 Subir evidencia reparación'*\n"
        "3. Sigue el flujo para enviar fotos/videos\n\n"
        "Si esto es un error, ignora este mensaje.",
        parse_mode=ParseMode.MARKDOWN
    )
