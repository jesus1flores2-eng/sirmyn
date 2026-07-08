"""
Handlers para el bot de emergencias SIRMYN
"""
from .inicio import (
    start_emergencia,
    tipo_emergencia_handler,
    descripcion_emergencia_handler,
    confirmar_emergencia_handler,
    enviar_emergencia_handler,
    cancelar_emergencia,
    EMERG_START,
    EMERG_TIPO, 
    EMERG_UBICACION,
    EMERG_DESCRIPCION,
    EMERG_CONFIRMAR,
    conv_handler_emergencias
)

from .ubicacion import (
    procesar_ubicacion_gps,
    ubicacion_gps_handler
)

__all__ = [
    # Estados
    'EMERG_START', 'EMERG_TIPO', 'EMERG_UBICACION', 
    'EMERG_DESCRIPCION', 'EMERG_CONFIRMAR',
    
    # Handlers
    'start_emergencia',
    'tipo_emergencia_handler', 
    'procesar_ubicacion_gps',
    'ubicacion_gps_handler',
    'descripcion_emergencia_handler',
    'confirmar_emergencia_handler',
    'enviar_emergencia_handler',
    'cancelar_emergencia',
    
    # Conversation Handler completo
    'conv_handler_emergencias'
]