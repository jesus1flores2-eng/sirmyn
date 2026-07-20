import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from app.telegram.common.states import *
from app.telegram.common.utils import user_data, limpiar_estado, actualizar_timestamp_usuario
from app.services.db_manager import DatabaseManager
from app.services.cloudinary_service import subir_archivo
from datetime import datetime
import os

logger = logging.getLogger(__name__)


# ============================================================
# HANDLER: ENTRE CALLES
# ============================================================

async def entre_calles_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    user_data[user_id]["entre_calles"] = update.message.text

    await update.message.reply_text(
        "Descríbeme un poco el problema:",
        reply_markup=ReplyKeyboardRemove()
    )
    return DESCRIPCION


# ============================================================
# HANDLER: DESCRIPCIÓN
# ============================================================

async def descripcion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    user_data[user_id]["descripcion"] = update.message.text

    keyboard = [["📸 Subir foto/video", "➡️ Omitir evidencia"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "📸 ¿Deseas subir una foto o video del problema?\n"
        "Puedes enviar la imagen/video directamente o presionar 'Omitir evidencia' para continuar.",
        reply_markup=reply_markup
    )
    return EVIDENCIA


# ============================================================
# HANDLER: CONFIRMACIÓN (GUARDADO COMPLETO)
# ============================================================

async def confirmacion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la confirmación del reporte y guarda en BD"""
    user_id = update.effective_user.id
    actualizar_timestamp_usuario(user_id)
    opcion = update.message.text.lower()

    if opcion in ["confirmar", "✅ confirmar", "si", "sí"]:
        datos = user_data[user_id]

        try:
            app = DatabaseManager.get_app()
            with app.app_context():
                from app.models.report import Report, Assignment, Localidad, Calle
                from app.models.team import Team
                from app.models.status import Status
                from app.models.user import User
                from app.extensions import db

                # OBTENER COORDENADAS (PRIORIDAD: GPS > OSM)
                latitud = datos.get("latitud")
                longitud = datos.get("longitud")

                if latitud is None or longitud is None:
                    try:
                        from app.services.geocoding import obtener_coordenadas_osm
                        latitud, longitud = obtener_coordenadas_osm(
                            datos.get("localidad_nombre", ""),
                            datos.get("calle_nombre", ""),
                            datos.get("numero", "")
                        )
                        logger.info(f"📍 Coordenadas obtenidas de OSM: {latitud}, {longitud}")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudieron obtener coordenadas de OSM: {e}")
                        latitud, longitud = None, None
                else:
                    logger.info(f"📍 Usando coordenadas GPS del usuario: {latitud}, {longitud}")

                # CREAR REPORTE
                nuevo_reporte = Report(
                    telefono=str(user_id),
                    reportante=datos["nombre"],
                    tipo=datos["tipo"],
                    subtipo=datos.get("subtipo", ""),
                    numero=datos["numero"],
                    entre_calles=datos.get("entre_calles", ""),
                    descripcion_problema=datos["descripcion"],
                    evidencia=datos.get("evidencia", None),
                    numero_cuenta=datos.get("cuenta"),
                    timestamp=datetime.utcnow(),
                    calle_id=datos["calle_id"],
                    localidad_id=datos["localidad_id"],
                    plataforma="telegram",
                    latitud=latitud,
                    longitud=longitud
                )

                db.session.add(nuevo_reporte)
                db.session.commit()

                # PROCESAR EVIDENCIA CON CLOUDINARY (CON FALLBACK LOCAL)
                if "evidencia_filename" in datos:
                    extension = datos["evidencia_filename"].split(".")[-1]
                    nuevo_nombre = f"reporte_{nuevo_reporte.id}.{extension}"

                    from app.telegram.common.keyboards import obtener_carpeta_departamento
                    carpeta_departamento = obtener_carpeta_departamento(datos.get("tipo", "general"))
                    carpeta_completa = os.path.join("uploads", carpeta_departamento)
                    os.makedirs(carpeta_completa, exist_ok=True)

                    origen = os.path.join("uploads", datos["evidencia_filename"])
                    destino = os.path.join(carpeta_completa, nuevo_nombre)

                    # Intentar subir a Cloudinary
                    public_id = f"reporte_{nuevo_reporte.id}"
                    url = subir_archivo(origen, folder=carpeta_departamento, public_id=public_id)
                    if url:
                        nuevo_reporte.evidencia = url
                        logger.info(f"✅ Evidencia subida a Cloudinary: {url}")
                        try:
                            os.remove(origen)
                        except:
                            pass
                    else:
                        # Fallback: almacenamiento local
                        try:
                            os.rename(origen, destino)
                            nuevo_reporte.evidencia = f"{carpeta_departamento}/{nuevo_nombre}"
                            logger.info(f"✅ Evidencia guardada localmente: {nuevo_reporte.evidencia}")
                        except Exception as e:
                            logger.error(f"❌ Error renombrando evidencia: {e}")
                            nuevo_reporte.evidencia = nuevo_nombre

                    db.session.commit()

                # ASIGNACIÓN INICIAL
                equipo_sin_asignar = Team.query.filter_by(nombre="Sin asignar").first()
                status_sin_asignar = Status.query.filter_by(descripcion="Sin Asignar").first()

                if equipo_sin_asignar and status_sin_asignar:
                    asignacion_inicial = Assignment(
                        report_id=nuevo_reporte.id,
                        team_id=equipo_sin_asignar.id,
                        status_id=status_sin_asignar.id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(asignacion_inicial)
                    db.session.commit()

                # NOTIFICAR A RESPONSABLES
                from app.services.notification_service import notificar_director_nuevo_reporte
                await notificar_director_nuevo_reporte(
                    reporte_id=nuevo_reporte.id,
                    telegram_id=user_id,
                    tipo_reporte=datos["tipo"]
                )

                # CONFIRMACIÓN AL USUARIO
                await update.message.reply_text(
                    f"✅ ¡Gracias {datos['nombre']}!\n\n"
                    f"📋 *Tu reporte ha sido registrado con el folio:*\n"
                    f"*#{nuevo_reporte.id}*\n\n"
                    f"🔐 *La información proporcionada será tratada de forma confidencial.*\n"
                    f"⚖️ *El uso de datos falsos puede conllevar acciones legales.*\n\n"
                    f"📌 *Próximos pasos:*\n"
                    f"• Un responsable revisará tu reporte.\n"
                    f"• Recibirás notificaciones de avance.\n"
                    f"• Usa /estado para consultar el progreso.\n\n"
                    f"📱 *¿Necesitas ayuda?* Usa /ayuda",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )

        except Exception as e:
            logger.error(f"❌ Error en confirmacion: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Ocurrió un error al guardar el reporte. Intenta nuevamente.",
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        await update.message.reply_text(
            "❌ Reporte cancelado. Usa /start para comenzar de nuevo.",
            reply_markup=ReplyKeyboardRemove()
        )

    limpiar_estado(user_id)
    return ConversationHandler.END
