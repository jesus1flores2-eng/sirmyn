# app/telegram/callbacks/presidente.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
from telegram.constants import ParseMode
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def presidencia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            from app.models.report import Report
            from app.models.municipio_config import MunicipioConfig
            
            usuario = User.query.filter_by(telegram_id=str(user_id)).first()
            if not usuario or usuario.rol_especifico != 'presidente':
                await update.message.reply_text("❌ Solo el presidente puede usar este comando.")
                return
            
            muni_id = usuario.municipio_id or 1
            municipio = MunicipioConfig.query.get(muni_id)
            
            # Departamentos normales (de dicts.py)
            departamentos_activos = municipio.get_departamentos_lista() if municipio else []
            mapeo_normales = {
                'agua': ('💧 Agua', 'Agua potable', 'pres_agua'),
                'drenaje': ('🚰 Drenaje', 'Drenaje', 'pres_drenaje'),
                'aseo': ('🗑️ Aseo', 'Aseo público', 'pres_aseo'),
                'alumbrado': ('💡 Alumbrado', 'Alumbrado público', 'pres_alumbrado'),
                'parques': ('🌳 Parques', 'Parques y jardines', 'pres_parques'),
                'ecologia': ('🌍 Ecología', 'Ecología', 'pres_ecologia'),
                'obras': ('🏗️ Obras', 'Obras públicas', 'pres_obra'),
            }
            
            # Emergencias (de emergencias/handlers.py)
            emergencias_activas = municipio.get_emergencias_lista() if municipio else []
            mapeo_emergencias = {
                'seguridad': ('👮 Seguridad', 'Seguridad pública', 'pres_seguridad'),
                'bomberos': ('🚒 Bomberos', 'Bomberos', 'pres_bomberos'),
                'proteccion_civil': ('🛡️ Protección Civil', 'Protección Civil', 'pres_proteccion_civil'),
                'punto_violeta': ('💜 Punto Violeta', 'Punto Violeta', 'pres_punto_violeta'),
                'ambulancia': ('🚑 Ambulancia', 'Ambulancia', 'pres_ambulancia'),
            }
            
            total = Report.query.filter_by(municipio_id=muni_id).count()
            
            mensaje = f"""🏛️ *DASHBOARD PRESIDENCIAL*
📅 {datetime.now().strftime('%d/%m/%Y')} | 🕐 {datetime.now().strftime('%H:%M')}
━━━━━━━━━━━━━━━━━━━━━━

📊 *REPORTES EN SISTEMA:*
• 📋 Total: {total}
"""
            
            keyboard = []
            fila = []
            
            # Agregar departamentos normales activos
            for dep_key in departamentos_activos:
                if dep_key in mapeo_normales:
                    nombre, tipo, callback = mapeo_normales[dep_key]
                    count = Report.query.filter_by(municipio_id=muni_id, tipo=tipo).count()
                    mensaje += f"• {nombre}: {count}\n"
                    fila.append(InlineKeyboardButton(nombre, callback_data=callback))
                    if len(fila) == 2:
                        keyboard.append(fila)
                        fila = []
            
            # Agregar emergencias activas
            for emp_key in emergencias_activas:
                if emp_key in mapeo_emergencias:
                    nombre, tipo, callback = mapeo_emergencias[emp_key]
                    count = Report.query.filter_by(municipio_id=muni_id, tipo=tipo).count()
                    mensaje += f"• {nombre}: {count}\n"
                    fila.append(InlineKeyboardButton(nombre, callback_data=callback))
                    if len(fila) == 2:
                        keyboard.append(fila)
                        fila = []
            
            if fila:
                keyboard.append(fila)
            
            mensaje += "\n*Selecciona un área:*"
            
            keyboard.append([InlineKeyboardButton("🔄 Actualizar", callback_data="pres_refresh")])
            keyboard.append([InlineKeyboardButton("🚪 Salir", callback_data="pres_salir")])
            
            await update.message.reply_text(mensaje, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(f"❌ Error en presidencia: {e}")
        await update.message.reply_text("❌ Error al cargar dashboard.")


async def presidente_callback_handler_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    
    try:
        if callback_data == 'pres_refresh':
            await recargar_dashboard_presidencial_simple(query)
        elif callback_data == 'pres_salir':
            await query.edit_message_text(
                "👋 *Has salido del dashboard presidencial.*\n\n"
                "Puedes volver a entrar en cualquier momento con /presidencia.\n\n"
                "🏠 *Para iniciar un reporte, usa /start*",
                parse_mode="Markdown",
                reply_markup=None
            )
        elif callback_data.startswith('pres_asignar_urgente_'):
            # ⭐ NUEVO: Asignación urgente desde presidente
            reporte_id = int(callback_data.replace('pres_asignar_urgente_', ''))
            await mostrar_cuadrillas_para_asignar_urgente(query, reporte_id)
        elif callback_data.startswith('pres_asignarc_urgente_'):
            # ⭐ NUEVO: Asignar a cuadrilla específica
            partes = callback_data.split('_')
            reporte_id = int(partes[3])
            cuadrilla_id = int(partes[4])
            await asignar_cuadrilla_urgente(query, reporte_id, cuadrilla_id)
        elif callback_data.startswith('pres_'):
            area = callback_data.replace('pres_', '')
            await mostrar_area_detalle_simple(query, area)
    except Exception as e:
        logger.error(f"❌ Error callback presidente: {e}")
        await query.answer("❌ Error", show_alert=True)


# ⭐ NUEVA FUNCIÓN: Mostrar cuadrillas para asignación urgente
async def mostrar_cuadrillas_para_asignar_urgente(query, reporte_id: int):
    """Muestra las cuadrillas disponibles para asignación urgente (presidente)"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.models.team import Team
            from app.models.user import User
            
            reporte = Report.query.get(reporte_id)
            if not reporte:
                await query.edit_message_text("❌ Reporte no encontrado.")
                return
            
            # Mapear tipo de reporte a área
            mapeo = {
                "Agua potable": "agua", "Drenaje": "agua",
                "Aseo público": "aseo", "Alumbrado público": "alumbrado",
                "Parques y jardines": "parques", "Ecología": "ecologia",
                "Seguridad pública": "seguridad", "Obras públicas": "obras",
                "Bomberos": "bomberos"
            }
            area = mapeo.get(reporte.tipo, None)

            if area:
                cuadrillas = Team.query.filter(
                    Team.area == area,
                    Team.nombre != "Sin asignar"
                ).order_by(Team.nombre).all()
            else:
                cuadrillas = Team.query.filter(
                    Team.nombre != "Sin asignar"
                ).order_by(Team.nombre).all()
        
            if not cuadrillas:
                await query.edit_message_text("❌ No hay cuadrillas disponibles en este momento.")
                return
            
            # Crear teclado con cuadrillas
            keyboard = []
            for cuadrilla in cuadrillas:
                usuarios_count = User.query.filter_by(team_id=cuadrilla.id).count()
                texto_boton = f"👷 {cuadrilla.nombre}"
                if usuarios_count > 0:
                    texto_boton += f" ({usuarios_count})"
                keyboard.append([
                    InlineKeyboardButton(
                        texto_boton,
                        callback_data=f"pres_asignarc_urgente_{reporte_id}_{cuadrilla.id}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton("↩️ Cancelar", callback_data="pres_salir")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            mensaje = (
                f"👷 *ASIGNACIÓN URGENTE - Reporte {reporte.folio_display}*\n\n"
                f"*🔴 ASIGNACIÓN PRESIDENCIAL*\n"
                f"Este reporte lleva más de 48 horas sin atender.\n\n"
                f"*Selecciona la cuadrilla para asignar:*"
            )
            
            await query.edit_message_text(
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            logger.info(f"✅ Mostrando cuadrillas para asignación urgente del reporte {reporte_id}")
            
    except Exception as e:
        logger.error(f"❌ Error mostrando cuadrillas para urgente: {e}")
        await query.edit_message_text("❌ Error al cargar cuadrillas.")


# ⭐ NUEVA FUNCIÓN: Asignar cuadrilla urgente
async def asignar_cuadrilla_urgente(query, reporte_id: int, cuadrilla_id: int):
    """Asigna un reporte urgente a una cuadrilla (presidente)"""
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report, Assignment
            from app.models.team import Team
            from app.models.status import Status
            from app.models.user import User
            from app.extensions import db
            
            reporte = Report.query.get(reporte_id)
            cuadrilla = Team.query.get(cuadrilla_id)
            
            if not reporte or not cuadrilla:
                await query.edit_message_text("❌ Datos no válidos.")
                return
            
            # Obtener presidente
            presidente = User.query.filter_by(
                rol_especifico='presidente',
                is_active=True
            ).first()
            
            quien_asigna = presidente.nombre if presidente else "Presidente"
            
            # Estado "Asignado"
            status_asignado = Status.query.filter_by(descripcion="Asignado").first()
            if not status_asignado:
                status_asignado = Status(descripcion="Asignado")
                db.session.add(status_asignado)
                db.session.commit()
            
            # Crear asignación con marca presidencial
            nueva_asignacion = Assignment(
                report_id=reporte_id,
                team_id=cuadrilla_id,
                status_id=status_asignado.id,
                timestamp=datetime.utcnow(),
                observaciones=f"Asignado URGENTE por PRESIDENTE {quien_asigna} via Telegram"
            )
            db.session.add(nueva_asignacion)
            db.session.commit()
            
            # Notificar a la cuadrilla (marca presidencial)
            usuarios_cuadrilla = User.query.filter_by(team_id=cuadrilla_id).all()
            notificaciones_enviadas = 0
            
            from app.services.notification_service import notificar_asignacion_a_cuadrilla
            
            for usuario_cuadrilla in usuarios_cuadrilla:
                if usuario_cuadrilla.telegram_id:
                    try:
                        await notificar_asignacion_a_cuadrilla(
                            reporte_id, 
                            usuario_cuadrilla.id, 
                            es_presidencial=True  # ⭐ Marca presidencial
                        )
                        notificaciones_enviadas += 1
                    except Exception as e:
                        logger.error(f"❌ Error notificando a {usuario_cuadrilla.nombre}: {e}")
            
            # ⭐ Notificar al director del área
            from app.services.notification_service import notificar_director_asignacion_presidencial
            await notificar_director_asignacion_presidencial(reporte_id, cuadrilla.nombre)
            
            # Confirmar al presidente
            mensaje_confirmacion = (
                f"✅ *REPORTE ASIGNADO URGENTEMENTE*\n\n"
                f"📋 *Folio:* {reporte.folio_display}\n"
                f"👷 *Cuadrilla:* {cuadrilla.nombre}\n"
                f"📍 *Ubicación:* {reporte.calle.nombre if reporte.calle else 'N/D'} #{reporte.numero}\n"
                f"🔧 *Problema:* {reporte.subtipo}\n\n"
                f"*🔴 ASIGNACIÓN PRESIDENCIAL - URGENTE*\n"
                f"• Notificaciones enviadas: {notificaciones_enviadas}\n"
                f"• Director notificado: ✅\n\n"
                f"*Asignado por:* {quien_asigna}\n"
                f"*Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            
            await query.edit_message_text(
                text=mensaje_confirmacion,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ Presidente {quien_asigna} asignó URGENTE reporte {reporte.folio_display} a cuadrilla {cuadrilla.nombre}")
            
    except Exception as e:
        logger.error(f"❌ Error asignando urgente: {e}")
        await query.edit_message_text("❌ Error al asignar reporte.")


async def mostrar_area_detalle_simple(query, area: str):
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.models.user import User
            
            usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            muni_id = usuario.municipio_id if usuario else 1
            
            mapeo = {
                'agua': {'nombre': '💧 Agua Potable', 'tipo': 'Agua potable'},
                'alumbrado': {'nombre': '💡 Alumbrado Público', 'tipo': 'Alumbrado público'},
                'drenaje': {'nombre': '🚰 Drenaje', 'tipo': 'Drenaje'},
                'aseo': {'nombre': '🗑️ Aseo Público', 'tipo': 'Aseo público'},
                'parques': {'nombre': '🌳 Parques y Jardines', 'tipo': 'Parques y jardines'},
                'obra': {'nombre': '🏗️ Obras Públicas', 'tipo': 'Obras públicas'},
                'seguridad': {'nombre': '👮 Seguridad Pública', 'tipo': 'Seguridad pública'},
                'bomberos': {'nombre': '🚒 Bomberos', 'tipo': 'Bomberos'},
                'ecologia': {'nombre': '🌍 Ecología', 'tipo': 'Ecología'}
            }
            
            if area not in mapeo:
                await query.edit_message_text(f"❌ Área no válida: {area}")
                return
            
            config = mapeo[area]
            reportes = Report.query.filter_by(municipio_id=muni_id, tipo=config['tipo']).order_by(Report.timestamp.desc()).all()
            
            mensaje = f"{config['nombre']}\n📊 Total: {len(reportes)} reportes\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            if reportes:
                for i, reporte in enumerate(reportes[:6], 1):
                    horas = int((datetime.now() - reporte.timestamp).total_seconds() / 3600)
                    estado = reporte.get_estado_actual()
                    mensaje += f"{i}. *{reporte.folio_display}*\n"
                    mensaje += f"   🔧 {reporte.subtipo[:30]}\n"
                    if reporte.entre_calles:
                        mensaje += f"   📍 {reporte.entre_calles[:30]}\n"
                    mensaje += f"   🏷️ {estado}\n"
                    mensaje += f"   ⏰ {horas} horas\n\n"
                
                if len(reportes) > 6:
                    mensaje += f"📝 ... y {len(reportes) - 6} más\n"
            else:
                mensaje += "📭 No hay reportes en esta área.\n"
            
            keyboard = [
                [InlineKeyboardButton("↩ Volver al dashboard", callback_data="pres_refresh")],
                [InlineKeyboardButton("🚪 Salir", callback_data="pres_salir")]
            ]
            await query.edit_message_text(mensaje, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(f"❌ Error en área {area}: {e}")
        await query.edit_message_text("❌ Error")


async def recargar_dashboard_presidencial_simple(query):
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from app.models.user import User
            
            usuario = User.query.filter_by(telegram_id=str(query.from_user.id)).first()
            muni_id = usuario.municipio_id if usuario else 1
            
            total = Report.query.filter_by(municipio_id=muni_id).count()
            agua = Report.query.filter_by(municipio_id=muni_id, tipo='Agua potable').count()
            alumbrado = Report.query.filter_by(municipio_id=muni_id, tipo='Alumbrado público').count()
            drenaje = Report.query.filter_by(municipio_id=muni_id, tipo='Drenaje').count()
            aseo = Report.query.filter_by(municipio_id=muni_id, tipo='Aseo público').count()
            parques = Report.query.filter_by(municipio_id=muni_id, tipo='Parques y jardines').count()
            obras = Report.query.filter_by(municipio_id=muni_id, tipo='Obras públicas').count()
            seguridad = Report.query.filter_by(municipio_id=muni_id, tipo='Seguridad pública').count()
            bomberos = Report.query.filter_by(municipio_id=muni_id, tipo='Bomberos').count()
            ecologia = Report.query.filter_by(municipio_id=muni_id, tipo='Ecología').count()

            fecha = datetime.now().strftime('%d/%m/%Y')
            hora = datetime.now().strftime('%H:%M')
            
            mensaje = f"""🏛️ *DASHBOARD PRESIDENCIAL*
📅 {fecha} | 🕐 {hora}
━━━━━━━━━━━━━━━━━━━━━━

📊 *REPORTES EN SISTEMA:*
• 📋 Total: {total}
• 💧 Agua: {agua}
• 🚰 Drenaje: {drenaje}
• 💡 Alumbrado: {alumbrado}
• 🗑️ Aseo: {aseo}
• 🌳 Parques: {parques}
• 🏗️ Obras: {obras}
• 👮 Seguridad: {seguridad}
• 🚒 Bomberos: {bomberos}
• 🌍 Ecología: {ecologia}

*Selecciona un área:*
"""
            
            keyboard = [
                [InlineKeyboardButton("💧 Agua", callback_data="pres_agua"),
                 InlineKeyboardButton("🚰 Drenaje", callback_data="pres_drenaje")],
                [InlineKeyboardButton("💡 Alumbrado", callback_data="pres_alumbrado"),
                 InlineKeyboardButton("🗑️ Aseo", callback_data="pres_aseo")],
                [InlineKeyboardButton("🌳 Parques", callback_data="pres_parques"),
                 InlineKeyboardButton("🏗️ Obras", callback_data="pres_obra")],
                [InlineKeyboardButton("👮 Seguridad", callback_data="pres_seguridad"),
                 InlineKeyboardButton("🚒 Bomberos", callback_data="pres_bomberos")],
                [InlineKeyboardButton("🌍 Ecología", callback_data="pres_ecologia")],
                [InlineKeyboardButton("🔄 Actualizar", callback_data="pres_refresh")],
                [InlineKeyboardButton("🚪 Salir del dashboard", callback_data="pres_salir")]
            ]
            
            await query.edit_message_text(mensaje, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(f"❌ Error recargando dashboard: {e}")
        await query.answer("❌ Error", show_alert=True)
