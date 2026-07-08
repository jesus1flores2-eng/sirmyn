from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
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
            
            usuario = User.query.filter_by(telegram_id=str(user_id)).first()
            if not usuario or usuario.rol_especifico != 'presidente':
                await update.message.reply_text("❌ Solo el presidente puede usar este comando.")
                return
            
            total = Report.query.count()
            agua = Report.query.filter(Report.tipo == 'Agua potable').count()
            alumbrado = Report.query.filter(Report.tipo == 'Alumbrado público').count()
            drenaje = Report.query.filter(Report.tipo == 'Drenaje').count()
            aseo = Report.query.filter(Report.tipo == 'Aseo público').count()
            
            fecha = datetime.now().strftime('%d/%m/%Y')
            hora = datetime.now().strftime('%H:%M')
            
            mensaje = f"""🏛️ *DASHBOARD PRESIDENCIAL*
📅 {fecha} | 🕐 {hora}
━━━━━━━━━━━━━━━━━━━━━━

📊 *REPORTES EN SISTEMA:*
• 📋 Total: {total}
• 💧 Agua: {agua}
• 💡 Alumbrado: {alumbrado}
• 🚰 Drenaje: {drenaje}
• 🗑️ Aseo: {aseo}

*Selecciona un área:*
"""
            
            keyboard = [
                [InlineKeyboardButton("💧 Agua", callback_data="pres_agua"),
                 InlineKeyboardButton("💡 Alumbrado", callback_data="pres_alumbrado")],
                [InlineKeyboardButton("🚰 Drenaje", callback_data="pres_drenaje"),
                 InlineKeyboardButton("🗑️ Aseo", callback_data="pres_aseo")],
                [InlineKeyboardButton("🌳 Parques", callback_data="pres_parques"),
                 InlineKeyboardButton("🏗️ Obras", callback_data="pres_obra")],
                [InlineKeyboardButton("👮 Seguridad", callback_data="pres_seguridad"),
                 InlineKeyboardButton("🚒 Bomberos", callback_data="pres_bomberos")],
                [InlineKeyboardButton("🔄 Actualizar", callback_data="pres_refresh")],
                [InlineKeyboardButton("🚪 Salir del dashboard", callback_data="pres_salir")]
            ]
            
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
        elif callback_data.startswith('pres_'):
            area = callback_data.replace('pres_', '')
            await mostrar_area_detalle_simple(query, area)
    except Exception as e:
        logger.error(f"❌ Error callback presidente: {e}")
        await query.answer("❌ Error", show_alert=True)


async def mostrar_area_detalle_simple(query, area: str):
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            
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
            reportes = Report.query.filter(Report.tipo == config['tipo']).order_by(Report.timestamp.desc()).all()
            
            mensaje = f"{config['nombre']}\n📊 Total: {len(reportes)} reportes\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            if reportes:
                for i, reporte in enumerate(reportes[:6], 1):
                    horas = int((datetime.now() - reporte.timestamp).total_seconds() / 3600)
                    mensaje += f"{i}. *#{reporte.id}*\n"
                    mensaje += f"   🔧 {reporte.subtipo[:30]}\n"
                    if reporte.entre_calles:
                        mensaje += f"   📍 {reporte.entre_calles[:30]}\n"
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
            
            total = Report.query.count()
            agua = Report.query.filter(Report.tipo == 'Agua potable').count()
            alumbrado = Report.query.filter(Report.tipo == 'Alumbrado público').count()
            drenaje = Report.query.filter(Report.tipo == 'Drenaje').count()
            aseo = Report.query.filter(Report.tipo == 'Aseo público').count()
            
            fecha = datetime.now().strftime('%d/%m/%Y')
            hora = datetime.now().strftime('%H:%M')
            
            mensaje = f"""🏛️ *DASHBOARD PRESIDENCIAL*
📅 {fecha} | 🕐 {hora}
━━━━━━━━━━━━━━━━━━━━━━

📊 *REPORTES EN SISTEMA:*
• 📋 Total: {total}
• 💧 Agua: {agua}
• 💡 Alumbrado: {alumbrado}
• 🚰 Drenaje: {drenaje}
• 🗑️ Aseo: {aseo}

*Selecciona un área:*
"""
            
            keyboard = [
                [InlineKeyboardButton("💧 Agua", callback_data="pres_agua"),
                 InlineKeyboardButton("💡 Alumbrado", callback_data="pres_alumbrado")],
                [InlineKeyboardButton("🚰 Drenaje", callback_data="pres_drenaje"),
                 InlineKeyboardButton("🗑️ Aseo", callback_data="pres_aseo")],
                [InlineKeyboardButton("🌳 Parques", callback_data="pres_parques"),
                 InlineKeyboardButton("🏗️ Obras", callback_data="pres_obra")],
                [InlineKeyboardButton("👮 Seguridad", callback_data="pres_seguridad"),
                 InlineKeyboardButton("🚒 Bomberos", callback_data="pres_bomberos")],
                [InlineKeyboardButton("🔄 Actualizar", callback_data="pres_refresh")],
                [InlineKeyboardButton("🚪 Salir del dashboard", callback_data="pres_salir")]
            ]
            
            await query.edit_message_text(mensaje, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(f"❌ Error recargando dashboard: {e}")
        await query.answer("❌ Error", show_alert=True)
