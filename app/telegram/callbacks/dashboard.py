# app/telegram/callbacks/dashboard.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def dashboard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    
    callback_data = query.data
    
    try:
        if not callback_data.startswith('dash_'):
            return
        
        parts = callback_data.split('_')
        
        # Permitir dash_salir con solo 2 partes
        if len(parts) == 2 and parts[1] == 'salir':
            accion = 'salir'
            tipo_reporte = None
        elif len(parts) < 3:
            await query.answer("❌ Error en formato", show_alert=True)
            return
        else:
            accion = parts[1]
            tipo_reporte = parts[2]
        
        user_id = query.from_user.id
        app = DatabaseManager.get_app()
        
        with app.app_context():
            from app.models.user import User
            from app.models.report import Report
            
            usuario = User.query.filter_by(telegram_id=str(user_id)).first()
            if not usuario:
                await query.answer("❌ Usuario no encontrado", show_alert=True)
                return
            
            if accion == 'salir':
                await query.edit_message_text(
                    "👋 *Has salido del dashboard.*\n\n"
                    "Usa `/dashboard` cuando quieras volver a entrar.\n"
                    "Usa `/ayuda` para ver todos los comandos disponibles.",
                    parse_mode="Markdown",
                    reply_markup=None
                )
                return
            
            if accion == 'ver':
                await manejar_ver_reportes(query, usuario, tipo_reporte)
            elif accion == 'detalle':
                reporte_id = int(tipo_reporte)
                await manejar_detalle_reporte(query, usuario, reporte_id)
            elif accion == 'asignar':
                reporte_id = int(tipo_reporte)
                await manejar_asignar_cuadrilla(query, usuario, reporte_id)
            elif accion == 'asignarc':
                # Formato: dash_asignarc_REPORTEID_CUADRILLAID
                reporte_id = int(parts[2])
                cuadrilla_id = int(parts[3])
                await ejecutar_asignacion(query, usuario, reporte_id, cuadrilla_id)
            elif accion == 'refresh':
                from app.telegram.commands.dashboard import generar_dashboard_por_rol, generar_teclado_por_rol
                mensaje = await generar_dashboard_por_rol(usuario)
                keyboard = await generar_teclado_por_rol(usuario)
                await query.edit_message_text(
                    text=mensaje,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                    disable_web_page_preview=True
                )
                
    except Exception as e:
        logger.error(f"❌ Error en dashboard_callback: {e}")
        await query.answer("❌ Error al procesar", show_alert=True)


async def manejar_ver_reportes(query, usuario, tipo_reporte):
    try:
        TIPO_MAP = {
            'agua': 'Agua potable',
            'drenaje': 'Drenaje',
            'alumbrado': 'Alumbrado público',
            'aseo': 'Aseo público',
            'parques': 'Parques y jardines',
            'obra': 'Obras públicas',
            'seguridad': 'Seguridad pública',
            'bomberos': 'Bomberos',
            'ecologia': 'Ecología'
        }
        
        tipo_bd = TIPO_MAP.get(tipo_reporte, tipo_reporte)
        
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            
            ahora = datetime.now()
            
            # ⭐ FILTRAR POR MUNICIPIO Y ESTADO (solo pendientes)
            from app.models.report import Assignment
            from app.models.status import Status
            
            # Obtener IDs de estados finalizados
            estados_finalizados = ['Finalizado', 'Aceptado por usuario', 'Aceptado automáticamente', 'Cancelado', 'Rechazado por usuario']
            
            query_reportes = Report.query.filter(
                Report.tipo == tipo_bd,
                Report.municipio_id == usuario.municipio_id
            )
            
            # Filtrar solo reportes sin asignar o en estados no finalizados
            todos_reportes = query_reportes.order_by(Report.timestamp.desc()).all()
            reportes = []
            for rep in todos_reportes:
                estado = rep.get_estado_actual()
                if estado not in estados_finalizados:
                    reportes.append(rep)
            
            nombres_bonitos = {
                'Agua potable': '💧 AGUA POTABLE',
                'Drenaje': '🚰 DRENAJE',
                'Alumbrado público': '💡 ALUMBRADO PÚBLICO',
                'Aseo público': '🗑️ ASEO PÚBLICO',
                'Parques y jardines': '🌳 PARQUES Y JARDINES',
                'Obras públicas': '🏗️ OBRAS PÚBLICAS',
                'Seguridad pública': '👮 SEGURIDAD PÚBLICA',
                'Bomberos': '🚒 BOMBEROS',
                'Ecología': '🌍 ECOLOGÍA'
            }
            
            titulo = nombres_bonitos.get(tipo_bd, tipo_bd.upper())
            
            if reportes:
                mensaje = f"{titulo}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                mensaje += f"📊 *Total: {len(reportes)} reportes*\n\n"
                mensaje += "*Selecciona un reporte para ver detalles y asignar:*"
                
                keyboard = []
                for rep in reportes[:10]:
                    horas = int((ahora - rep.timestamp).total_seconds() / 3600)
                    estado_actual = rep.get_estado_actual()
                    
                    # Icono según estado
                    if estado_actual in ['Finalizado', 'Aceptado por usuario']:
                        icono = "✅"
                    elif estado_actual == 'En proceso':
                        icono = "🔧"
                    elif estado_actual == 'Asignado':
                        icono = "👷"
                    else:
                        icono = "⏳"
                    
                    texto_boton = f"{icono} {rep.folio_display} - {rep.subtipo[:20]} ({horas}h)"
                    keyboard.append([
                        InlineKeyboardButton(
                            texto_boton,
                            callback_data=f"dash_detalle_{rep.id}"
                        )
                    ])
                
                if len(reportes) > 10:
                    mensaje += f"\n\n📊 *Mostrando 10 de {len(reportes)} reportes*"
                
                keyboard.append([
                    InlineKeyboardButton("↩ Volver al dashboard", callback_data=f"dash_refresh_{usuario.area}")
                ])
            else:
                mensaje = f"{titulo}\n\n✅ No hay reportes en este momento.\n"
                keyboard = [[
                    InlineKeyboardButton("↩ Volver al dashboard", callback_data=f"dash_refresh_{usuario.area}")
                ]]
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"❌ Error mostrando {tipo_reporte}: {e}")
        await query.answer("❌ Error al cargar reportes", show_alert=True)


# ============================================================
# DETALLE DEL REPORTE
# ============================================================
async def manejar_detalle_reporte(query, usuario, reporte_id):
    """Muestra el detalle del reporte con opción de asignar"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.status import Status
            
            reporte = Report.query.filter_by(
                id=reporte_id,
                municipio_id=usuario.municipio_id
            ).first()
            
            if not reporte:
                await query.answer("❌ Reporte no encontrado", show_alert=True)
                return
            
            # Obtener última asignación
            asignacion = Assignment.query.filter_by(
                report_id=reporte_id
            ).order_by(Assignment.timestamp.desc()).first()
            
            estado_actual = reporte.get_estado_actual()
            cuadrilla = reporte.get_cuadrilla_actual()
            horas = int((datetime.now() - reporte.timestamp).total_seconds() / 3600)
            
            mensaje = f"📋 *DETALLE DEL REPORTE {reporte.folio_display}*\n"
            mensaje += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            mensaje += f"🔧 *Tipo:* {reporte.tipo}\n"
            mensaje += f"📝 *Subtipo:* {reporte.subtipo}\n"
            mensaje += f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
            mensaje += f"🏘️ *Localidad:* {reporte.localidad.nombre if reporte.localidad else 'N/D'}\n"
            mensaje += f"👤 *Reportante:* {reporte.reportante}\n"
            mensaje += f"📄 *Descripción:* {reporte.descripcion_problema[:200]}\n"
            mensaje += f"⏰ *Hace:* {horas} horas\n"
            mensaje += f"📊 *Estado:* {estado_actual}\n"
            mensaje += f"👷 *Cuadrilla:* {cuadrilla}\n\n"
            
            # Si está sin asignar, mostrar botón de asignar
            keyboard = []
            if estado_actual in ['Sin Asignar', 'Sin asignar', 'Pendiente']:
                keyboard.append([
                    InlineKeyboardButton(
                        "👷 Asignar a cuadrilla",
                        callback_data=f"dash_asignar_{reporte_id}"
                    )
                ])
            else:
                mensaje += "ℹ️ *Este reporte ya está asignado*\n"
            
            keyboard.append([
                InlineKeyboardButton("↩ Volver", callback_data=f"dash_volver_{reporte.tipo.lower().replace(' ', '_')}")
            ])
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"❌ Error en manejar_detalle_reporte: {e}")
        await query.answer("❌ Error al cargar detalle", show_alert=True)


# ============================================================
# MOSTRAR CUADRILLAS PARA ASIGNAR
# ============================================================
async def manejar_asignar_cuadrilla(query, usuario, reporte_id):
    """Muestra cuadrillas disponibles para asignar"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.models.team import Team
            from app.models.user import User
            
            reporte = Report.query.filter_by(
                id=reporte_id,
                municipio_id=usuario.municipio_id
            ).first()
            
            if not reporte:
                await query.answer("❌ Reporte no encontrado", show_alert=True)
                return
            
            # Determinar área según el tipo de reporte
            mapeo_tipo_a_area = {
                "Agua potable": "agua",
                "Drenaje": "agua",
                "Aseo público": "aseo",
                "Alumbrado público": "alumbrado",
                "Parques y jardines": "parques",
                "Ecología": "ecologia",
                "Seguridad pública": "seguridad",
                "Obras públicas": "obras",
                "Bomberos": "bomberos"
            }
            area = mapeo_tipo_a_area.get(reporte.tipo, "general")
            
            # Buscar cuadrillas del área en el municipio
            cuadrillas = Team.query.filter(
                Team.area == area,
                Team.nombre != "Sin asignar",
                Team.municipio_id == usuario.municipio_id
            ).order_by(Team.nombre).all()
            
            if not cuadrillas:
                await query.edit_message_text(
                    f"❌ *No hay cuadrillas disponibles*\n\n"
                    f"No se encontraron cuadrillas en el área de *{area}* para este municipio.",
                    parse_mode='Markdown'
                )
                return
            
            keyboard = []
            for cuadrilla in cuadrillas:
                usuarios_count = User.query.filter_by(team_id=cuadrilla.id).count()
                texto_boton = f"👷 {cuadrilla.nombre}"
                if usuarios_count > 0:
                    texto_boton += f" ({usuarios_count})"
                keyboard.append([
                    InlineKeyboardButton(
                        texto_boton,
                        callback_data=f"dash_asignarc_{reporte_id}_{cuadrilla.id}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton("↩ Cancelar", callback_data=f"dash_detalle_{reporte_id}")
            ])
            
            mensaje = (
                f"👷 *ASIGNAR REPORTE {reporte.folio_display}*\n\n"
                f"*Área:* {area.title()}\n"
                f"*Problema:* {reporte.subtipo}\n\n"
                f"*Selecciona la cuadrilla:*"
            )
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"❌ Error en manejar_asignar_cuadrilla: {e}")
        await query.answer("❌ Error al cargar cuadrillas", show_alert=True)


# ============================================================
# EJECUTAR ASIGNACIÓN
# ============================================================
async def ejecutar_asignacion(query, usuario, reporte_id, cuadrilla_id):
    """Asigna la cuadrilla al reporte y notifica"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.team import Team
            from app.models.status import Status
            from app.models.user import User
            from app.extensions import db
            
            reporte = Report.query.filter_by(
                id=reporte_id,
                municipio_id=usuario.municipio_id
            ).first()
            
            cuadrilla = Team.query.get(cuadrilla_id)
            
            if not reporte or not cuadrilla:
                await query.answer("❌ Datos inválidos", show_alert=True)
                return
            
            # Estado "Asignado"
            status_asignado = Status.query.filter_by(descripcion="Asignado").first()
            if not status_asignado:
                status_asignado = Status(descripcion="Asignado", color="#007bff")
                db.session.add(status_asignado)
                db.session.commit()
            
            # Crear asignación
            nueva_asignacion = Assignment(
                report_id=reporte_id,
                team_id=cuadrilla_id,
                status_id=status_asignado.id,
                timestamp=datetime.utcnow(),
                observaciones=f"Asignado por {usuario.nombre} ({usuario.rol_especifico}) via Telegram"
            )
            db.session.add(nueva_asignacion)
            db.session.commit()
            
            # Notificar a la cuadrilla
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id).all()
            notificaciones_enviadas = 0
            
            from app.services.notification_service import notificar_asignacion_a_cuadrilla
            
            for usuario_cuadrilla in usuarios_cuadrilla:
                if usuario_cuadrilla.telegram_id:
                    try:
                        await notificar_asignacion_a_cuadrilla(
                            reporte_id,
                            usuario_cuadrilla.id,
                            es_presidencial=False
                        )
                        notificaciones_enviadas += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario_cuadrilla.nombre}: {e}")
            
            mensaje = (
                f"✅ *REPORTE ASIGNADO CORRECTAMENTE*\n\n"
                f"📋 *Folio:* {reporte.folio_display}\n"
                f"👷 *Cuadrilla:* {cuadrilla.nombre}\n"
                f"🔧 *Problema:* {reporte.subtipo}\n\n"
                f"*📤 Notificaciones enviadas:* {notificaciones_enviadas} de {len(usuarios_cuadrilla)}\n\n"
                f"*Asignado por:* {usuario.nombre}\n"
                f"*Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"❌ Error en ejecutar_asignacion: {e}")
        await query.answer("❌ Error al asignar", show_alert=True)
