from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from app.telegram.common.states import *
from app.telegram.common.handlers import entre_calles_handler, descripcion_handler, confirmacion_handler
from app.telegram.handlers.start import start, manejar_aceptacion, menu_principal_handler
from app.telegram.handlers.tipo import tipo_handler
from app.telegram.handlers.ubicacion import *
from app.telegram.handlers.numero import numero_handler, duplicado_confirmacion_handler, consulta_id_handler, verificar_reportante_handler
from app.telegram.handlers.evidencia import evidencia_handler
from app.telegram.handlers.mensajes_generales import router_texto_completo
from app.telegram.agua.handlers import cuenta_handler, subtipo_agua_handler, subtipo_drenaje_handler
from app.telegram.commands.cancelar import cancelar_command
from app.telegram.commands.estado import estado_command
from app.telegram.commands.ayuda import ayuda_command
from app.telegram.commands.registrar import registrar_command, registro_confirmacion_handler
from app.telegram.commands.desvincular import desvincular_command
from app.telegram.commands.miestado import miestado_command
from app.telegram.commands.dashboard import dashboard_command
from app.telegram.callbacks.aceptacion import aceptar_privacidad_callback
from app.telegram.callbacks.general import button_callback_handler
from app.telegram.callbacks.director import director_callback_handler
from app.telegram.comunicacion.handlers import (
    comunicado_start, seleccionar_localidad, escribir_mensaje,
    manejar_imagen, confirmar_envio,
    COM_LOCALIDAD, COM_MENSAJE, COM_IMAGEN, COM_CONFIRMAR
)
from app.telegram.callbacks.supervisor import (
    supervisor_callback_handler,
    rechazo_opciones_handler,
    apoyo_confirmar_handler,
    manejar_motivo_rechazo_supervisor
)
from app.telegram.callbacks.usuario import usuario_validacion_callback_handler
from app.telegram.callbacks.encuesta import encuesta_calificacion_handler, encuesta_velocidad_handler, encuesta_comentario_handler
from app.telegram.callbacks.rechazo import (
    rechazo_motivo_handler,
    rechazo_volver_handler,
    rechazo_otro_motivo_handler
)
from app.telegram.callbacks.presidente import presidencia_command, presidente_callback_handler_simple
from app.telegram.callbacks.dashboard import dashboard_callback_handler
from app.telegram.handlers.reparacion_conversation import (
    reparacion_start, reparacion_evidencia, reparacion_materiales,
    reparacion_comentario, reparacion_confirmar,
    REP_EVIDENCIA, REP_MATERIALES, REP_COMENTARIO, REP_CONFIRMAR
)

# Aseo
from app.telegram.aseo.handlers import subtipo_aseo_handler
from app.telegram.aseo.callbacks import jefe_aseo_callback_handler, manejar_motivo_rechazo_jefe_aseo

# Alumbrado
from app.telegram.alumbrado.handlers import subtipo_alumbrado_handler
from app.telegram.alumbrado.callbacks import jefe_alumbrado_callback_handler, manejar_motivo_rechazo_jefe_alumbrado

# Parques
from app.telegram.parques.handlers import subtipo_parques_handler
from app.telegram.parques.callbacks import jefe_parques_callback_handler, manejar_motivo_rechazo_jefe_parques

# Ecología
from app.telegram.ecologia.handlers import subtipo_ecologia_handler
from app.telegram.ecologia.callbacks import jefe_ecologia_callback_handler, manejar_motivo_rechazo_jefe_ecologia

# Seguridad
from app.telegram.seguridad.handlers import subtipo_seguridad_handler
from app.telegram.seguridad.callbacks import jefe_seguridad_callback_handler, manejar_motivo_rechazo_jefe_seguridad

# Obras
from app.telegram.obras.handlers import subtipo_obras_handler
from app.telegram.obras.callbacks import jefe_obras_callback_handler, manejar_motivo_rechazo_jefe_obras

# Bomberos
from app.telegram.bomberos.handlers import subtipo_bomberos_handler
from app.telegram.bomberos.callbacks import jefe_bomberos_callback_handler, manejar_motivo_rechazo_jefe_bomberos

from app.telegram.emergencias.handlers import (
    emergencia_start, emergencia_departamento, emergencia_advertencia,
    emergencia_telefono, emergencia_ubicacion, emergencia_subtipo,
    emergencia_evidencia, emergencia_confirmar,
    EMERGENCIA_DEPARTAMENTO, EMERGENCIA_TELEFONO, EMERGENCIA_ADVERTENCIA,
    EMERGENCIA_SUBTIPO, EMERGENCIA_UBICACION, EMERGENCIA_COMENTARIO,
    EMERGENCIA_EVIDENCIA, EMERGENCIA_CONFIRMAR
)

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
    # CONVERSATIONHANDLER DE EMERGENCIA
    # ============================================================
    conv_handler_emergencia = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🚨 EMERGENCIA$'), emergencia_start)],
        states={
            EMERGENCIA_DEPARTAMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_departamento)],
            EMERGENCIA_ADVERTENCIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_advertencia)],
            EMERGENCIA_TELEFONO: [MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_telefono)],
            EMERGENCIA_UBICACION: [
                MessageHandler(filters.LOCATION, emergencia_ubicacion),
                MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_ubicacion)
            ],
            EMERGENCIA_SUBTIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_subtipo)],
            EMERGENCIA_EVIDENCIA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_evidencia),
                MessageHandler(filters.PHOTO | filters.VIDEO, emergencia_evidencia)
            ],
            EMERGENCIA_CONFIRMAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, emergencia_confirmar)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_command), CommandHandler('start', start)],
        name="emergencia",
        persistent=False,
        per_user=True,
        per_chat=True,
    )
    app.add_handler(conv_handler_emergencia)

    # ============================================================
    # CONVERSATIONHANDLER COMUNICACION
    # ============================================================

    conv_handler_comunicado = ConversationHandler(
        entry_points=[CommandHandler('comunicado', comunicado_start)],
        states={
            COM_LOCALIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, seleccionar_localidad)],
            COM_MENSAJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, escribir_mensaje)],
            COM_IMAGEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_imagen),
                MessageHandler(filters.PHOTO, manejar_imagen)
            ],
            COM_CONFIRMAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_envio)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_command)],
        name="comunicado_social",
        persistent=False,
        per_user=True,
        per_chat=True,
    )
    app.add_handler(conv_handler_comunicado)

    # ============================================================
    # CONVERSATIONHANDLER PRINCIPAL PARA REPARACIÓN
    # ============================================================

    # Después de conv_handler_comunicado, agregar:
    conv_handler_reparacion = ConversationHandler(
        entry_points=[CallbackQueryHandler(reparacion_start, pattern="^reparacion_")],
        states={
            REP_EVIDENCIA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reparacion_evidencia),
                MessageHandler(filters.PHOTO | filters.VIDEO, reparacion_evidencia)
            ],
            REP_MATERIALES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reparacion_materiales),
                MessageHandler(filters.PHOTO, reparacion_materiales)
            ],
            REP_COMENTARIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, reparacion_comentario)],
            REP_CONFIRMAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, reparacion_confirmar)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_command)],
        name="reparacion_cuadrilla",
        persistent=False,
        per_user=True,
        per_chat=True,
    )
    app.add_handler(conv_handler_reparacion)


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
            SUBTIPO_ASEO_PUBLICO: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_aseo_handler)],
            SUBTIPO_ALUMBRADO_PUBLICO: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_alumbrado_handler)],
            SUBTIPO_PARQUES_JARDINES: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_parques_handler)],
            SUBTIPO_ECOLOGIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_ecologia_handler)],
            SUBTIPO_SEGURIDAD_PUBLICA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_seguridad_handler)],
            SUBTIPO_OBRA_PUBLICA: [MessageHandler(filters.TEXT & ~filters.COMMAND, subtipo_obras_handler)],
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
    # ConversationHandler para ENCUESTA
    # ============================================================
    conv_handler_encuesta = ConversationHandler(
        entry_points=[CallbackQueryHandler(encuesta_calificacion_handler, pattern="^enc_calif_")],
        states={
            ENCUESTA_VELOCIDAD: [
                CallbackQueryHandler(encuesta_velocidad_handler, pattern="^enc_vel_")
            ],
            ENCUESTA_COMENTARIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, encuesta_comentario_handler)
            ]
        },
        fallbacks=[
            CommandHandler('cancelar', cancelar_command),
            CommandHandler('start', start)
        ],
        name="encuesta_satisfaccion",
        persistent=False,
        per_user=True,
        per_chat=True
    )
    app.add_handler(conv_handler_encuesta)

    # ============================================================
    # AGREGAR HANDLERS
    # ============================================================
    app.add_handler(conv_handler_registro)
    app.add_handler(conv_handler_main)

    # Comandos básicos
    app.add_handler(CommandHandler('estado', estado_command))
    app.add_handler(CommandHandler('ayuda', ayuda_command))
    app.add_handler(CommandHandler('cancelar', cancelar_command))
    app.add_handler(CommandHandler('miestado', miestado_command))
    app.add_handler(CommandHandler('desvincular', desvincular_command))


    # Comandos para roles
    app.add_handler(CommandHandler('presidencia', presidencia_command))
    app.add_handler(CommandHandler('dashboard', dashboard_command))

    # ============================================================
    # CALLBACKS (ORDEN IMPORTANTE)
    # ============================================================
    app.add_handler(CallbackQueryHandler(presidente_callback_handler_simple, pattern="^pres_"))
    app.add_handler(CallbackQueryHandler(dashboard_callback_handler, pattern="^dash_"))
    app.add_handler(CallbackQueryHandler(director_callback_handler, pattern="^dir_"))
    app.add_handler(CallbackQueryHandler(supervisor_callback_handler, pattern="^super_"))
    app.add_handler(CallbackQueryHandler(rechazo_opciones_handler, pattern="^rechazar_"))
    app.add_handler(CallbackQueryHandler(apoyo_confirmar_handler, pattern="^apoyo_confirmar_"))
    # Callbacks departamentales
    app.add_handler(CallbackQueryHandler(jefe_aseo_callback_handler, pattern="^aseo_"))
    app.add_handler(CallbackQueryHandler(jefe_alumbrado_callback_handler, pattern="^alumbrado_"))
    app.add_handler(CallbackQueryHandler(jefe_parques_callback_handler, pattern="^parques_"))
    app.add_handler(CallbackQueryHandler(jefe_ecologia_callback_handler, pattern="^ecologia_"))
    app.add_handler(CallbackQueryHandler(jefe_seguridad_callback_handler, pattern="^seguridad_"))
    app.add_handler(CallbackQueryHandler(jefe_obras_callback_handler, pattern="^obras_"))
    app.add_handler(CallbackQueryHandler(jefe_bomberos_callback_handler, pattern="^bomberos_"))
    # Usuario y encuesta
    app.add_handler(CallbackQueryHandler(usuario_validacion_callback_handler, pattern="^usuario_(aceptar|rechazar)"))
    app.add_handler(CallbackQueryHandler(encuesta_calificacion_handler, pattern="^enc_calif_"))
    app.add_handler(CallbackQueryHandler(encuesta_velocidad_handler, pattern="^enc_vel_"))
    app.add_handler(CallbackQueryHandler(rechazo_motivo_handler, pattern="^usuario_rechazo_motivo_"))
    app.add_handler(CallbackQueryHandler(rechazo_volver_handler, pattern="^rech_volver_"))
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    # ============================================================
    # HANDLERS DE UBICACIÓN
    # ============================================================
    app.add_handler(
        MessageHandler(
            filters.LOCATION,
            manejar_ubicacion_problema_gps
        )
    )

    # Handler central para mensajes de texto
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router_texto_completo)
    )

    logger.info("✅ Bot de Telegram configurado correctamente con TODOS los departamentos")

    return app
