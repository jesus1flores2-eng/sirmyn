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
        if len(parts) < 3:
            await query.answer("❌ Error en formato", show_alert=True)
            return
        
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
            
            if accion == 'ver':
                await manejar_ver_reportes(query, usuario, tipo_reporte)
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
            reportes = Report.query.filter(
                Report.tipo == tipo_bd
            ).order_by(Report.timestamp.desc()).all()
            
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
                for i, rep in enumerate(reportes[:15], 1):
                    horas = int((ahora - rep.timestamp).total_seconds() / 3600)
                    estado_actual = rep.get_estado_actual()
                    mensaje += f"{i}. *#{rep.id}*\n"
                    mensaje += f"   🔧 {rep.subtipo}\n"
                    if rep.entre_calles:
                        mensaje += f"   📍 {rep.entre_calles}\n"
                    mensaje += f"   ⏰ Hace {horas}h | 📊 {estado_actual}\n"
                    mensaje += f"   👤 {rep.reportante}\n\n"
                
                if len(reportes) > 15:
                    mensaje += f"📊 *Mostrando 15 de {len(reportes)} reportes*\n"
                else:
                    mensaje += f"📊 *Total: {len(reportes)} reportes*\n"
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
