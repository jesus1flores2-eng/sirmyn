#!/usr/bin/env python3
"""
Actualiza la contraseña del usuario administrador (id=2) en la base de datos.
Uso: python actualizar_password_admin.py
"""
import hashlib
import binascii
from app import create_app
from app.extensions import db
from app.models.user import User

def make_password_hash(password):
    """Genera hash compatible con el sistema"""
    salt = 's4l7s3cr370'
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f'pbkdf2:sha256:100000${salt}${binascii.hexlify(dk).decode()}'

def actualizar_password_admin():
    """Actualiza la contraseña del admin"""
    app = create_app()
    with app.app_context():
        # Buscar admin por id=2 o username='admin'
        admin = User.query.filter_by(id=2).first()
        if not admin:
            admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("❌ No se encontró el usuario administrador")
            return
        
        # Contraseña deseada
        nueva_password = "S1rMyn@Adm1n2026"
        nuevo_hash = make_password_hash(nueva_password)
        
        # Actualizar
        admin.password_hash = nuevo_hash
        db.session.commit()
        
        print(f"✅ Contraseña actualizada para el usuario: {admin.username}")
        print(f"   • Nombre: {admin.nombre}")
        print(f"   • Nueva contraseña: {nueva_password}")
        print(f"   • Hash: {nuevo_hash[:50]}...")

if __name__ == "__main__":
    actualizar_password_admin()
