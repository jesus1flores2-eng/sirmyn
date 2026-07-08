# app/utils/notificaciones.py
import os
from flask import current_app
from twilio.rest import Client

def get_twilio_client():
    """
    Crea y devuelve un cliente Twilio usando las variables de entorno cargadas en config.py
    """
    account_sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    auth_token = current_app.config.get("TWILIO_AUTH_TOKEN")

    if not account_sid or not auth_token:
        raise ValueError("⚠️ Configuración de Twilio incompleta. Verifica tu archivo .env")

    return Client(account_sid, auth_token)


def enviar_notificacion(numero_destino: str, mensaje: str) -> str:
    """
    Envía un mensaje de WhatsApp usando Twilio.
    Devuelve el SID del mensaje si fue exitoso.
    """
    try:
        client = get_twilio_client()

        # Remitente configurado en .env
        from_num = current_app.config.get("TWILIO_PHONE_NUMBER")
        if not from_num:
            raise ValueError("⚠️ TWILIO_PHONE_NUMBER no está configurado en .env")

        # Asegurar prefijo de WhatsApp
        if not numero_destino.startswith("whatsapp:"):
            numero_destino = f"whatsapp:{numero_destino}"

        message = client.messages.create(
            from_=from_num,
            to=numero_destino,
            body=mensaje
        )

        current_app.logger.info(f"✅ Mensaje enviado a {numero_destino}. SID: {message.sid}")
        return message.sid

    except Exception as e:
        current_app.logger.error(f"❌ Error al enviar notificación: {str(e)}")
        return None
