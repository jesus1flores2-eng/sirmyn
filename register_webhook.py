#!/usr/bin/env python3
"""
Registra el webhook en Telegram
Uso: python register_webhook.py
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
SERVER_URL = os.getenv("SERVER_URL")  # Ej: https://xxxx.ngrok.io o https://tu-app.onrender.com

if not TOKEN:
    print("❌ Error: TELEGRAM_TOKEN no configurado en .env")
    sys.exit(1)

if not SERVER_URL:
    print("❌ Error: SERVER_URL no configurado en .env")
    print("   Ejemplo: SERVER_URL=https://tu-app.onrender.com")
    sys.exit(1)

# Construir URL del webhook
webhook_url = f"{SERVER_URL}/telegram/webhook"
print(f"📝 Registrando webhook en: {webhook_url}")

# Eliminar webhook existente
print("🧹 Eliminando webhook anterior...")
r = requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
if r.status_code == 200:
    print("✅ Webhook eliminado")
else:
    print(f"⚠️ No se pudo eliminar: {r.text}")

# Registrar nuevo webhook
print(f"📤 Registrando webhook en {webhook_url}...")
r = requests.get(
    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
    params={
        "url": webhook_url,
        "drop_pending_updates": True
    }
)

if r.status_code == 200:
    data = r.json()
    if data.get("ok"):
        print("✅ Webhook registrado correctamente")
        print(f"📋 Info: {data}")
    else:
        print(f"❌ Error registrando webhook: {data}")
else:
    print(f"❌ Error HTTP: {r.status_code}")

# Verificar estado
print("\n🔍 Verificando estado del webhook...")
r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
if r.status_code == 200:
    data = r.json()
    print(f"📋 Estado: {data}")
else:
    print(f"❌ Error verificando: {r.status_code}")

print("\n✅ Proceso completado")
