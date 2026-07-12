from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.db_manager import DatabaseManager
import os
import logging

logger = logging.getLogger(__name__)

def crear_teclado_subtipos(subtipos_dict: dict, columnas: int = 2):
    keyboard = []
    items = list(subtipos_dict.items())
    for i in range(0, len(items), columnas):
        fila = []
        for key, value in items[i:i+columnas]:
            texto_display = value[:25] + "..." if len(value) > 25 else value
            fila.append(f"{key}️⃣ {texto_display}")
        keyboard.append(fila)
    return keyboard

def obtener_carpeta_departamento(tipo_reporte: str) -> str:
    mapeo = {
        "Agua potable": "agua_potable",
        "Drenaje": "agua_potable",
        "Aseo público": "aseo_publico",
        "Alumbrado público": "alumbrado_publico",
        "Parques y jardines": "parques_jardines",
        "Ecología": "ecologia",
        "Seguridad pública": "seguridad_publica",
        "Obras públicas": "obras_publicas",
        "Bomberos": "bomberos"
    }
    return mapeo.get(tipo_reporte, "general")

def construir_botones_reporte(reporte_id, confirmado=False, problema_reportado=False, es_director=False, context=None, user_id=None):
    """
    Construye los botones para el mensaje de reporte.
    
    Args:
        reporte_id: ID del reporte
        confirmado: Si ya fue confirmado por la cuadrilla
        problema_reportado: Si ya se reportó problema de ubicación
        es_director: Si es para vista de director
        context: Contexto de Telegram (para obtener user_id desde el callback)
        user_id: ID del usuario de Telegram (para verificar asignación)
    """
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.user import User
            from app.models.team import Team
            from app.models.status import Status
            
            reporte = Report.query.get(reporte_id)
            if not reporte:
                return InlineKeyboardMarkup([[]])
            
            # ⭐ DETECTAR ESTADO REAL DE LA ASIGNACIÓN
            asignacion_actual = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            estado_actual = None
            if asignacion_actual and asignacion_actual.status:
                estado_actual = asignacion_actual.status.descripcion
            
            # ⭐ SI EL ESTADO ES "En proceso", confirmado = True
            if estado_actual == "En proceso":
                confirmado = True
            # ⭐ SI EL ESTADO ES "Problema ubicación", problema_reportado = True
            elif estado_actual == "Problema ubicación":
                problema_reportado = True
            
            keyboard = []
            
            # ========== BOTONES PARA DIRECTOR ==========
            if es_director:
                fila1 = [
                    InlineKeyboardButton(
                        "👷 Asignar a Cuadrilla",
                        callback_data=f"dir_asignar_{reporte_id}"
                    )
                ]
                
                if reporte.evidencia:
                    fila1.append(
                        InlineKeyboardButton(
                            "📎 Ver Evidencia",
                            callback_data=f"dir_evidencia_{reporte_id}"
                        )
                    )
                
                keyboard.append(fila1)
                keyboard.append([
                    InlineKeyboardButton(
                        "📋 Ver Detalles Completos",
                        callback_data=f"dir_detalle_{reporte_id}"
                    )
                ])
                return InlineKeyboardMarkup(keyboard)
            
            # ========== BOTONES PARA CUADRILLA ==========
            # FILA 1: Confirmar / Problema
            if confirmado:
                fila1 = [
                    InlineKeyboardButton("✅ Confirmado ✓", callback_data="confirmado_ya"),
                    InlineKeyboardButton("❌ Problema con ubicación", callback_data=f"problema_{reporte_id}")
                ]
            elif problema_reportado:
                fila1 = [
                    InlineKeyboardButton("✅ Confirmar recepción", callback_data=f"confirmar_{reporte_id}"),
                    InlineKeyboardButton("❌ Problema reportado ✓", callback_data="problema_ya")
                ]
            else:
                fila1 = [
                    InlineKeyboardButton("✅ Confirmar recepción", callback_data=f"confirmar_{reporte_id}"),
                    InlineKeyboardButton("❌ Problema con ubicación", callback_data=f"problema_{reporte_id}")
                ]
            
            keyboard.append(fila1)
            
            # FILA 2: Mapa + Evidencia
            if reporte.latitud and reporte.longitud:
                texto_mapa = "📍 Ubicación Exacta (GPS)"
            else:
                calle_nombre = reporte.calle.nombre if reporte.calle else ''
                localidad_nombre = reporte.localidad.nombre if reporte.localidad else ''
                direccion = f"{calle_nombre} {reporte.numero}, {localidad_nombre}"
                texto_mapa = "🗺️ Ver en mapa"
            
            fila2 = [InlineKeyboardButton(texto_mapa, callback_data=f"mapa_{reporte_id}")]
            
            if reporte.evidencia:
                if reporte.evidencia.startswith('http'):
                    icono = "☁️"
                else:
                    ext = reporte.evidencia.split('.')[-1].lower() if '.' in reporte.evidencia else ''
                    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                        icono = "🖼️"
                    elif ext in ['mp4', 'mov', 'avi', 'mkv']:
                        icono = "🎬"
                    else:
                        icono = "📎"
                fila2.append(
                    InlineKeyboardButton(f"{icono} Ver evidencia", callback_data=f"evidencia_{reporte_id}")
                )
            
            keyboard.append(fila2)
            
            # ============================================================
            # ⭐ BOTONES DE REPARACIÓN Y APOYO (USANDO user_id O context)
            # ============================================================
            
            # Determinar user_id (prioridad: user_id > context)
            user_id_efectivo = user_id
            if user_id_efectivo is None and context is not None:
                if hasattr(context, 'user_data') and context.user_data:
                    user_id_efectivo = context.user_data.get('user_id')
                elif hasattr(context, '_user_id'):
                    user_id_efectivo = context._user_id
            
            if user_id_efectivo:
                asignacion = Assignment.query.filter_by(
                    report_id=reporte_id
                ).order_by(Assignment.timestamp.desc()).first()
                
                if asignacion and asignacion.team_id:
                    usuario_actual = User.query.filter_by(telegram_id=str(user_id_efectivo)).first()
                    
                    if usuario_actual and usuario_actual.team_id == asignacion.team_id:
                        # ⭐ SOLO mostrar si el estado NO es "Finalizado" o "Aceptado por usuario"
                        if estado_actual not in ["Finalizado", "Aceptado por usuario", "Aceptado automáticamente"]:
                            # FILA 3: Subir evidencia reparación
                            keyboard.append([
                                InlineKeyboardButton(
                                    "🔧 Subir evidencia reparación",
                                    callback_data=f"reparacion_{reporte_id}"
                                )
                            ])
                            
                            # FILA 4: Solicitudes de apoyo
                            keyboard.append([
                                InlineKeyboardButton(
                                    "🛠️ Solicitar retroexcavadora",
                                    callback_data=f"solicitar_retro_{reporte_id}"
                                ),
                                InlineKeyboardButton(
                                    "🚛 Solicitar camión de material",
                                    callback_data=f"solicitar_camion_{reporte_id}"
                                )
                            ])
                            keyboard.append([
                                InlineKeyboardButton(
                                    "👷 Solicitar apoyo de otra cuadrilla",
                                    callback_data=f"solicitar_apoyo_cuadrilla_{reporte_id}"
                                )
                            ])
            
            return InlineKeyboardMarkup(keyboard)
            
    except Exception as e:
        logger.error(f"❌ Error en construir_botones_reporte: {e}")
        return InlineKeyboardMarkup([[]])
