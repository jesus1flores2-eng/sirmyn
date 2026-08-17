from telegram import Update
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
import logging

logger = logging.getLogger(__name__)


async def ayuda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            
            usuario = User.query.filter_by(telegram_id=str(user_id)).first()
            rol = usuario.rol_especifico if usuario and usuario.rol_especifico else None
            area = usuario.area if usuario and usuario.area else None
            
            # ============================================================
            # PRESIDENTE
            # ============================================================
            if rol == 'presidente':
                mensaje = (
                    "🏛️ *AYUDA - PRESIDENCIA*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/presidencia* - Dashboard general de todos los departamentos\n"
                    "  • Ver total de reportes por área\n"
                    "  • Seleccionar un área para ver detalles\n"
                    "  • Asignar reportes urgentes (+48h sin atender)\n\n"
                    "*/dashboard* - Vista rápida del panel presidencial\n\n"
                    "💡 *Tip:* Los reportes urgentes aparecen con botón rojo para asignar directamente."
                )
            
            # ============================================================
            # DIRECTOR
            # ============================================================
            elif rol == 'director':
                area_nombre = area.upper() if area else 'tu área'
                mensaje = (
                    f"👨‍💼 *AYUDA - DIRECTOR DE {area_nombre}*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/dashboard* - Panel de control de tu área\n"
                    "  • Ver total de reportes, recibidos hoy y urgentes\n"
                    "  • Presiona 'Ver reportes' para ver la lista completa\n"
                    "  • Cada reporte muestra su estado actual\n\n"
                    "*Acciones desde el panel:*\n"
                    "  • Asignar reportes a cuadrillas\n"
                    "  • Ver detalles completos de cada reporte\n"
                    "  • Ver evidencia adjunta\n\n"
                    "💡 *Tip:* Los reportes urgentes (>24h) aparecen marcados con ⚠️"
                )
            
            # ============================================================
            # JEFE DE ÁREA
            # ============================================================
            elif rol and 'jefe_area' in rol:
                area_nombre = area.upper() if area else 'tu área'
                mensaje = (
                    f"🔧 *AYUDA - JEFE DE {area_nombre}*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/dashboard* - Panel de control de tu área\n"
                    "  • Ver estadísticas y lista de reportes\n"
                    "  • Cada reporte muestra su estado actual\n\n"
                    "*Validación de reparaciones:*\n"
                    "  • Cuando una cuadrilla termina, recibes una notificación\n"
                    "  • *✅ Validar:* Aprueba la reparación y finaliza el reporte\n"
                    "  • *❌ Rechazar:* Escribe el motivo y la cuadrilla deberá corregir\n\n"
                    "💡 *Tip:* Revisa bien la evidencia (fotos/videos) antes de validar."
                )
            
            # ============================================================
            # SUPERVISOR
            # ============================================================
            elif rol == 'supervisor':
                mensaje = (
                    "👁️ *AYUDA - SUPERVISOR*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/dashboard* - Panel de supervisión\n"
                    "  • Ver reportes pendientes de validación\n\n"
                    "*Validación de reparaciones:*\n"
                    "  • *✅ Validar:* Aprueba y notifica al ciudadano\n"
                    "  • *❌ Rechazar:* Opciones para reasignar o devolver a cuadrilla\n"
                    "    - Reasignar a otra cuadrilla\n"
                    "    - Devolver a la misma cuadrilla para corrección\n"
                    "    - Enviar a administrador\n\n"
                    "💡 *Tip:* Si la reparación es insuficiente, describe bien el motivo."
                )
            
            # ============================================================
            # CUADRILLA
            # ============================================================
            elif rol == 'cuadrilla':
                mensaje = (
                    "👷 *AYUDA - CUADRILLA*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/pendientes* - Ver TODOS tus reportes activos\n"
                    "  • Muestra folio, dirección, tipo y tiempo transcurrido\n"
                    "  • Sin límite de fecha\n\n"
                    "*/miestado* - Resumen de últimas 24 horas\n\n"
                    "*Cuando recibes un reporte:*\n"
                    "  • *✅ Confirmar recepción:* Indica que vas a atenderlo\n"
                    "  • *❌ Problema con ubicación:* Si no encuentras la dirección\n"
                    "  • *📍 Ubicación GPS:* Ver en Google Maps/Waze\n"
                    "  • *🖼️ Ver evidencia:* Foto/video del reportante\n\n"
                    "*Al terminar el trabajo:*\n"
                    "  • *🔧 Subir evidencia reparación:* Fotos/videos del trabajo\n"
                    "  • *🛠️ Solicitar retroexcavadora:* Solo Agua/Drenaje\n"
                    "  • *🚛 Solicitar camión:* Solo Agua/Drenaje\n"
                    "  • *👷 Solicitar apoyo:* Pedir otra cuadrilla de refuerzo\n\n"
                    "💡 *Tip:* Siempre toma fotos del ANTES y DESPUÉS de la reparación."
                )
            
            # ============================================================
            # OPERADOR DE MAQUINARIA
            # ============================================================
            elif rol in ['retro', 'camion', 'camion_7m', 'volteo', 'vactor', 'pipa']:
                maquina = rol.replace('_', ' ').title()
                mensaje = (
                    f"🚛 *AYUDA - OPERADOR DE {maquina}*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/viajes* - Ver todos tus viajes pendientes\n"
                    "  • Muestra reporte, dirección y material solicitado\n\n"
                    "*Cuando recibes una solicitud:*\n"
                    "  • *✅ Ya voy para allá:* Confirma que vas en camino\n"
                    "  • *📸 Subir evidencia:* Foto del ANTES y DESPUÉS\n\n"
                    "💡 *Tip:* Confirma siempre 'Ya voy' para que la cuadrilla sepa que vas."
                )
            
            # ============================================================
            # COMUNICACIÓN SOCIAL
            # ============================================================
            elif rol == 'comunicacion_social':
                mensaje = (
                    "📣 *AYUDA - COMUNICACIÓN SOCIAL*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/comunicado* - Enviar comunicado con imagen\n"
                    "*/comunicado_video* - Enviar comunicado con video\n\n"
                    "💡 *Tip:* Prepara las imágenes antes de iniciar el comunicado."
                )
            
            # ============================================================
            # CIUDADANO (sin rol o no registrado)
            # ============================================================
            else:
                mensaje = (
                    "🤖 *AYUDA - SIRMYN*\n\n"
                    "*Comandos disponibles:*\n\n"
                    "*/start* - Iniciar un nuevo reporte ciudadano\n"
                    "  • Selecciona el tipo de problema\n"
                    "  • Proporciona ubicación (GPS o manual)\n"
                    "  • Describe el problema y adjunta evidencia\n\n"
                    "*/estado* - Ver todos tus reportes\n"
                    "  • Muestra activos y finalizados\n\n"
                    "*/cancelar* - Cancelar operación actual\n\n"
                    "💡 *Tip:* Puedes enviar fotos y videos como evidencia de tu reporte."
                )
            
            await update.message.reply_text(mensaje, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"❌ Error en /ayuda: {e}")
        await update.message.reply_text(
            "❌ Error al cargar la ayuda. Intenta más tarde.",
            parse_mode="Markdown"
        )
