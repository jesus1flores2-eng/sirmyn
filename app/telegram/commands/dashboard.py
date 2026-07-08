from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from app.services.db_manager import DatabaseManager
import logging

logger = logging.getLogger(__name__)

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.user import User
            
            usuario = User.query.filter_by(telegram_id=str(user_id)).first()
            if not usuario:
                await update.message.reply_text(
                    "❌ No tienes cuenta vinculada. Usa /registrar",
                    parse_mode="Markdown"
                )
                return
            
            # Si es presidente, redirigir a presidencia
            if usuario.rol_especifico == 'presidente' or usuario.username == 'presidente':
                from app.telegram.callbacks.presidente import presidencia_command
                await presidencia_command(update, context)
                return
            
            # Generar dashboard según rol
            mensaje = await generar_dashboard_por_rol(usuario)
            keyboard = await generar_teclado_por_rol(usuario)
            
            await update.message.reply_text(
                text=mensaje,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"❌ Error en /dashboard: {e}")
        await update.message.reply_text("❌ Error al cargar dashboard.")


async def generar_dashboard_por_rol(usuario):
    try:
        app = DatabaseManager.get_app()
        with app.app_context():
            from app.models.report import Report
            from datetime import datetime, timedelta
            
            rol = usuario.rol_especifico or usuario.role
            area = usuario.area
            ahora = datetime.now()
            hoy = ahora.date()
            inicio_hoy = datetime.combine(hoy, datetime.min.time())
            
            AREA_A_TIPOS = {
                'agua': ['Agua potable', 'Drenaje'],
                'alumbrado': ['Alumbrado público'],
                'aseo': ['Aseo público'],
                'parques': ['Parques y jardines'],
                'obra': ['Obras públicas'],
                'seguridad': ['Seguridad pública'],
                'bomberos': ['Bomberos'],
                'ecologia': ['Ecología'],
                'jefe_area_tecnica': ['Agua potable', 'Drenaje'],
                'jefe_area_comercial': ['Agua potable', 'Drenaje'],
                'supervisor': ['Agua potable', 'Drenaje']
            }
            
            tipos_a_mostrar = AREA_A_TIPOS.get(rol, AREA_A_TIPOS.get(area, [area]))
            
            mensaje = ""
            titulo = ""
            
            if rol == 'director':
                titulo = f"📊 DIRECTOR DE {area.upper()}"
            elif 'jefe_area' in rol:
                titulo = f"🔧 {rol.replace('_', ' ').upper()} - {area.upper()}"
            elif rol == 'supervisor':
                titulo = f"👁️ SUPERVISOR - {area.upper()}"
            else:
                titulo = f"📋 {rol.replace('_', ' ').upper()}"
            
            mensaje += f"{titulo}\n━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje += f"📅 {hoy.strftime('%d/%m/%Y')} | 🕐 {ahora.strftime('%H:%M')}\n\n"
            
            total_general = 0
            hoy_general = 0
            urgentes_general = 0
            
            for tipo in tipos_a_mostrar:
                total = Report.query.filter(Report.tipo == tipo).count()
                hoy_count = Report.query.filter(
                    Report.tipo == tipo,
                    Report.timestamp >= inicio_hoy
                ).count()
                
                urgentes = 0
                reportes_tipo = Report.query.filter(Report.tipo == tipo).all()
                for rep in reportes_tipo:
                    estado = rep.get_estado_actual()
                    horas = (ahora - rep.timestamp).total_seconds() / 3600
                    if horas > 24 and estado not in ['Finalizado', 'Cancelado', 'Aceptado por usuario']:
                        urgentes += 1
                
                mensaje += f"*{tipo}:*\n"
                mensaje += f"• 📋 Total: {total}\n"
                mensaje += f"• 📥 Hoy: {hoy_count}\n"
                mensaje += f"• ⚠️ Urgentes (>24h): {urgentes}\n\n"
                
                total_general += total
                hoy_general += hoy_count
                urgentes_general += urgentes
            
            if len(tipos_a_mostrar) > 1:
                mensaje += f"📊 *RESUMEN GENERAL:*\n"
                mensaje += f"• 📋 Total: {total_general}\n"
                mensaje += f"• 📥 Hoy: {hoy_general}\n"
                mensaje += f"• ⚠️ Urgentes: {urgentes_general}\n\n"
            
            mensaje += f"👤 *Usuario:* {usuario.nombre}\n"
            mensaje += f"🎯 *Rol:* {rol.replace('_', ' ').title()}\n"
            
            return mensaje
            
    except Exception as e:
        logger.error(f"❌ Error generando dashboard: {e}")
        return f"📊 *DASHBOARD*\n\n⚠️ Error al cargar datos."


async def generar_teclado_por_rol(usuario):
    rol = usuario.rol_especifico or usuario.role
    area = usuario.area
    
    if area == 'agua' or rol in ['jefe_area_tecnica', 'jefe_area_comercial', 'supervisor']:
        keyboard = [
            [
                InlineKeyboardButton("💧 Ver reportes Agua", callback_data=f"dash_ver_agua_{area}"),
                InlineKeyboardButton("🚰 Ver reportes Drenaje", callback_data=f"dash_ver_drenaje_{area}")
            ]
        ]
    elif rol == 'director':
        area_nombres = {
            'alumbrado': '💡 Alumbrado',
            'aseo': '🗑️ Aseo',
            'parques': '🌳 Parques',
            'obra': '🏗️ Obras',
            'seguridad': '👮 Seguridad',
            'bomberos': '🚒 Bomberos',
            'ecologia': '🌍 Ecología'
        }
        nombre_boton = area_nombres.get(area, area.title())
        keyboard = [[
            InlineKeyboardButton(f"{nombre_boton}", callback_data=f"dash_ver_{area}_{area}")
        ]]
    else:
        return None
    
    return keyboard
