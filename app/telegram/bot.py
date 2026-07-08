from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from app.telegram.states import *
from app.telegram.handlers.start import start, manejar_aceptacion, menu_principal_handler
from app.telegram.handlers.tipo import tipo_handler, cuenta_handler
from app.telegram.handlers.subtipo import *
from app.telegram.handlers.ubicacion import *
from app.telegram.handlers.numero import numero_handler, duplicado_confirmacion_handler, consulta_id_handler, verificar_reportante_handler
from app.telegram.handlers.descripcion import entre_calles_handler, descripcion_handler
from app.telegram.handlers.evidencia import evidencia_handler, manejar_texto_evidencia, manejar_multimedia_evidencia, mostrar_resumen
from app.telegram.handlers.confirmacion import confirmacion_handler
from app.telegram.commands.cancelar import cancelar_command
from app.telegram.commands.registrar import registrar_command, registro_confirmacion_handler
from app.telegram.commands.estado import estado_command
from app.telegram.commands.ayuda import ayuda_command
from app.telegram.commands.nombre import nombre_command
from app.telegram.commands.miestado import miestado_command
from app.telegram.commands.dashboard import dashboard_command
from app.telegram.callbacks.aceptacion import aceptar_privacidad_callback
from app.telegram.callbacks.presidente import presidencia_command, presidente_callback_handler_simple
from app.telegram.callbacks.dashboard import dashboard_callback_handler
from app.telegram.callbacks.general import button_callback_handler
import logging

logger = logging.getLogger(__name__)

def build_telegram_app(token):
    """Construye la aplicación de Telegram para webhooks"""
    app = Application.builder().token(token).build()
    
    # ============================================================
    # CONVERSATIONHANDLER PARA REGISTRO
    # ============================================================
    conv_handler_registro = ConversationHandler(
        entry_points=[CommandHandler('registrar', registrar_command)],
        states={
            REGISTRO_CONFIRMACION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registro_confirmacion_handler)
            ],
        },
        fallbacks=[
            CommandHandler('cancelar', cancelar_command),
            CommandHandler('registrar', registrar_command),
            CommandHandler('start', start)
        ],
        name="registro_profesional",
        persistent=False,
        per_user=True,
        per_chat=True,
    )
    
    # ============================================================
    # CONVERSATIONHANDLER PRINCIPAL PARA REPORTES
    # ============================================================
    conv_handler_main = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ESPERAR_ACEPTACION: [CallbackQueryHandler(manejar_aceptacion, pattern="^(aceptar|rechazar)_privacidad$")],
            MENU_PRINCIPAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_principal_handler)],
            TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tipo_handler)],
            CUENTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, cuenta_handler)],
            SUBTIPO_AGUA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_agua_handler)],
            SUBTIPO_DRENAJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_drenaje_handler)],
            SUBTIPO_ASEO_PUBLICO: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_aseo_publico_handler)],
            SUBTIPO_ALUMBRADO_PUBLICO: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_alumbrado_handler)],
            SUBTIPO_PARQUES_JARDINES: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_parques_handler)],
            SUBTIPO_ECOLOGIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_ecologia_handler)],
            SUBTIPO_SEGURIDAD_PUBLICA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_seguridad_handler)],
            SUBTIPO_OBRA_PUBLICA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_obra_handler)],
            SUBTIPO_BOMBEROS: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_bomberos_handler)],
            ELEGIR_UBICACION: [
                MessageHandler(filters.LOCATION, ubicacion_gps_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_ubicacion_handler),
            ],
            LOCALIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, localidad_handler)],
            LOCALIDAD_SUGERENCIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, localidad_sugerencias_handler)],
            CALLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, calle_handler)],
            CALLE_SUGERENCIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, calle_sugerencias_handler)],
            NUMERO: [MessageHandler(filters.TEXT & ~filters.COMMAND, numero_handler)],
            DUPLICADO_CONFIRMACION: [MessageHandler(filters.TEXT & ~filters.COMMAND, duplicado_confirmacion_handler)],
            ENTRE_CALLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, entre_calles_handler)],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, descripcion_handler)],
            EVIDENCIA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, evidencia_handler),
                MessageHandler(filters.PHOTO | filters.VIDEO, evidencia_handler)
            ],
            CONFIRMACION: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmacion_handler)],
            CONSULTA_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, consulta_id_handler)],
            VERIFICAR_REPORTANTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, verificar_reportante_handler)],
        },
        fallbacks=[
            CommandHandler('cancelar', cancelar_command),
            CommandHandler('start', start)
        ],
        name="reporte_principal",
        persistent=False,
        per_user=True,
        per_chat=True,
    )
    
    # ============================================================
    # AGREGAR HANDLERS
    # ============================================================
    
    app.add_handler(conv_handler_registro)
    app.add_handler(conv_handler_main)
    
    # Comandos básicos
    app.add_handler(CommandHandler('estado', estado_command))
    app.add_handler(CommandHandler('ayuda', ayuda_command))
    app.add_handler(CommandHandler('cancelar', cancelar_command))
    app.add_handler(CommandHandler('nombre', nombre_command))
    app.add_handler(CommandHandler('miestado', miestado_command))
    
    # Comandos para roles
    app.add_handler(CommandHandler('presidencia', presidencia_command))
    app.add_handler(CommandHandler('dashboard', dashboard_command))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(aceptar_privacidad_callback, pattern="^(aceptar|rechazar)_privacidad$"))
    app.add_handler(CallbackQueryHandler(presidente_callback_handler_simple, pattern="^pres_"))
    app.add_handler(CallbackQueryHandler(dashboard_callback_handler, pattern="^dash_"))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("✅ Bot de Telegram configurado correctamente con todos los handlers")
    
    return app
