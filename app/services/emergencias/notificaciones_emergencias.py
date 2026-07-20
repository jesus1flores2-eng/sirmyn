# app/services/emergencias/notificaciones_emergencias.py
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

async def notificar_emergencia_a_directores(bot, db_session, report_id, datos_emergencia):
    """
    Notifica a los directores del área correspondiente sobre una nueva emergencia.
    """
    try:
        # Determinar área basada en el tipo de emergencia
        tipo_emergencia = datos_emergencia.get('tipo', '').lower()
        area = determinar_area_por_tipo(tipo_emergencia)
        
        # Obtener directores del área (COMISARIO + BASE)
        query = text("""
            SELECT telegram_id, nombre, role 
            FROM users 
            WHERE area = :area 
            AND role IN ('director', 'jefe_area')
            AND telegram_id IS NOT NULL
            AND is_active = 1
            ORDER BY role DESC
        """)
        
        result = await db_session.execute(query, {'area': area})
        directores = result.fetchall()
        
        if not directores:
            logger.warning(f"No se encontraron directores para el área: {area}")
            return 0
        
        # Construir mensaje personalizado
        mensaje = construir_mensaje_emergencia(datos_emergencia, report_id)
        
        # Contador de notificaciones enviadas
        notificaciones_enviadas = 0
        
        # Enviar notificación a cada director
        for director in directores:
            telegram_id, nombre, role = director
            
            # Personalizar mensaje según rol
            if role == 'director':
                mensaje_personalizado = f"👔 *COMISARIO {nombre}*\n\n{mensaje}"
            else:
                mensaje_personalizado = f"👨‍💼 *BASE/OPERADOR {nombre}*\n\n{mensaje}"
            
            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=mensaje_personalizado,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                notificaciones_enviadas += 1
                logger.info(f"✅ Notificación enviada a {nombre} ({role}): {telegram_id}")
                
            except Exception as e:
                logger.error(f"❌ Error enviando notificación a {telegram_id}: {e}")
        
        return notificaciones_enviadas
        
    except Exception as e:
        logger.error(f"❌ Error en notificaciones_emergencia_a_directores: {e}")
        return 0

def determinar_area_por_tipo(tipo_emergencia):
    """Determina el área basada en el tipo de emergencia."""
    tipo = tipo_emergencia.lower()
    
    if 'policia' in tipo or 'seguridad' in tipo or 'asalto' in tipo:
        return 'seguridad'
    elif 'bomberos' in tipo or 'incendio' in tipo or 'fuego' in tipo:
        return 'bomberos'
    elif 'ambulancia' in tipo or 'medic' in tipo or 'herido' in tipo:
        return 'bomberos'  # O 'salud' si tienes esa área
    elif 'rescate' in tipo or 'atrapado' in tipo:
        return 'bomberos'
    elif 'punto violeta' in tipo or 'violencia' in tipo:
        return 'seguridad'
    else:
        return 'seguridad'  # Por defecto

def construir_mensaje_emergencia(datos_emergencia, report_id):
    """Construye el mensaje de notificación de emergencia."""
    folio = datos_emergencia.get('folio_publico', 'N/A')
    tipo = datos_emergencia.get('tipo', 'N/A').title()
    reportante = datos_emergencia.get('reportante', 'N/A')
    ubicacion = datos_emergencia.get('direccion_aproximada', 'N/A')
    descripcion = datos_emergencia.get('descripcion', 'N/A')
    
    # Información inferida
    personas_heridas = "✅ SÍ" if datos_emergencia.get('personas_heridas') else "❌ NO"
    peligro_vida = "⚠️ POSIBLE" if datos_emergencia.get('peligro_vida') else "✅ NO"
    
    mensaje = f"""
🚨 *EMERGENCIA REPORTADA - ACCIÓN REQUERIDA*
───────────────────────────────
📋 *FOLIO:* `{folio}`
📍 *TIPO:* {tipo}
👤 *REPORTANTE:* {reportante}
🗺️ *UBICACIÓN:* {ubicacion}
📝 *DESCRIPCIÓN:* {descripcion}
───────────────────────────────
⚡ *INFORMACIÓN CRÍTICA:*
• 🚑 *Personas heridas:* {personas_heridas}
• ⚠️ *Peligro de vida:* {peligro_vida}
• 🕒 *Hora reporte:* {datos_emergencia.get('timestamp_reporte', 'AHORA')}
───────────────────────────────
🎯 *ACCIONES REQUERIDAS:*
1️⃣ *VERIFICAR* ubicación exacta
2️⃣ *ASIGNAR* patrulla disponible
3️⃣ *DESPACHAR* unidad más cercana
4️⃣ *MONITOREAR* tiempo de respuesta
───────────────────────────────
🆔 *ID REPORTE:* `{report_id}`
🔗 *DASHBOARD:* [Ver en sistema](http://tu-dominio.com/admin/dashboard)
📞 *CONTACTO ADICIONAL:* {datos_emergencia.get('contacto_adicional', 'N/A')}
───────────────────────────────
*RESPONDA CON:*
• ✅ `Asignado` - Cuando asigne patrulla
• 📍 `En camino` - Cuando patrulla salga
• 🏁 `En sitio` - Cuando llegue al lugar
"""
    
    return mensaje
