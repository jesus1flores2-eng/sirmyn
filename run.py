#!/usr/bin/env python3
"""
Punto de entrada para producción (Webhook)
Ejecuta SOLO Flask, el bot se activa mediante webhooks
"""
from app import create_app
from app.services.db_manager import DatabaseManager
import os

app = create_app()

# Configurar DatabaseManager para que el bot pueda acceder a la BD
DatabaseManager.set_app(app)

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 SIRMYN - MODO WEBHOOK")
    print("=" * 60)
    print("🌐 Servidor corriendo en http://localhost:5000")
    print("📱 Webhook esperando mensajes en /telegram/webhook")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
