"""
Handlers específicos para manejo de ubicación GPS en emergencias
VERSIÓN COMPLETA con integración a BD
"""
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from ..config import EmergenciasConfig
from ..utils.geolocalizacion import obtener_direccion_osm, generar_mapa_url
from ..emergencias_database import (
    buscar_localidad_flexible_emergencia,
    buscar_calle_flexible_emergencia
)

logger = logging.getLogger(__name__)
config = EmergenciasConfig()


async def procesar_ubicacion_gps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Procesa la ubicación GPS recibida del usuario - VERSIÓN COMPLETA
    Combina velocidad de emergencia con integración a BD cuando posible
    """
    location = update.message.location
    
    logger.info(f"📍 [EMERGENCIA] GPS recibido: lat={location.latitude}, lon={location.longitude}")
    
    # Guardar coordenadas exactas (CRÍTICO para emergencias)
    lat, lon = location.latitude, location.longitude
    context.user_data['latitud'] = lat
    context.user_data['longitud'] = lon
    context.user_data['ubicacion_gps'] = True
    
    # OBTENER DIRECCIÓN del GPS (esto es lo más importante)
    direccion_info = obtener_direccion_osm(lat, lon)
    
    # Construir dirección legible para emergencias
    direccion_legible = "Ubicación GPS exacta"
    detalles_extra = []
    localidad_id = None
    calle_id = None
    
    if direccion_info:
        # 1. Obtener calle y localidad del GPS
        calle_detectada = direccion_info.get('road', '')
        localidad_detectada = direccion_info.get('localidad', '')
        
        # 2. Buscar en BD (PERO CON TIMEOUT MENTAL - si no encuentra rápido, seguir)
        if localidad_detectada:
            # Búsqueda RÁPIDA de localidad
            resultado_localidad = buscar_localidad_flexible_emergencia(localidad_detectada)
            if resultado_localidad:
                localidad_id, localidad_nombre = resultado_localidad
                context.user_data['localidad_id'] = localidad_id
                context.user_data['localidad_nombre'] = localidad_nombre
                detalles_extra.append(f"📍 *Zona:* {localidad_nombre}")
            else:
                # Si no encuentra en BD, usar lo del GPS directamente
                context.user_data['localidad_nombre'] = localidad_detectada
                detalles_extra.append(f"📍 *Zona detectada:* {localidad_detectada}")
        
        # 3. Buscar calle (solo si tenemos localidad_id)
        if calle_detectada and localidad_id:
            resultado_calle = buscar_calle_flexible_emergencia(calle_detectada, localidad_id)
            if resultado_calle:
                calle_id, calle_nombre = resultado_calle
                context.user_data['calle_id'] = calle_id
                context.user_data['calle_nombre'] = calle_nombre
                direccion_legible = calle_nombre
            else:
                # Usar nombre del GPS
                direccion_legible = calle_detectada
        elif calle_detectada:
            direccion_legible = calle_detectada
        
        # Agregar número si existe
        if direccion_info.get('house_number'):
            direccion_legible += f" #{direccion_info['house_number']}"
        
        context.user_data['direccion_info'] = direccion_info
    
    # Guardar dirección aproximada
    context.user_data['direccion_aproximada'] = direccion_legible
    
    # Generar enlaces de mapas
    context.user_data['mapa_google'] = generar_mapa_url(lat, lon, "google")
    context.user_data['mapa_osm'] = generar_mapa_url(lat, lon, "osm")
    context.user_data['what3words'] = generar_mapa_url(lat, lon, "what3words")
    
    # Construir mensaje de confirmación
    detalles_texto = "\n".join(detalles_extra) if detalles_extra else "*Ubicación precisa obtenida*"
    
    await update.message.reply_text(
        f"✅ *📍 UBICACIÓN CONFIRMADA*\n\n"
        f"🚨 *Lugar:* {direccion_legible}\n"
        f"{detalles_texto}\n\n"
        f"📝 *Describa BREVEMENTE la emergencia:*\n"
        f"• ¿Qué ocurre?\n"
        f"• ¿Personas involucradas?\n"
        f"• ¿Heridos/atrapados?\n\n"
        f"*Ej: 'Accidente 2 autos, 3 heridos, conductor atrapado'*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Ir al siguiente estado
    from .inicio import EMERG_DESCRIPCION
    return EMERG_DESCRIPCION


async def ubicacion_gps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias para compatibilidad"""
    return await procesar_ubicacion_gps(update, context)