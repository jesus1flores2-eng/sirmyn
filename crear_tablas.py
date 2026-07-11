#!/usr/bin/env python3
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.report import Report, Localidad, Calle, Assignment
from app.models.team import Team
from app.models.status import Status
from app.models.feedback import RechazoUsuario, EncuestaSatisfaccion
import os

def crear_tablas():
    app = create_app()
    with app.app_context():
        print("🚀 Creando tablas en la base de datos...")
        db.create_all()
        print("✅ Tablas creadas correctamente")

if __name__ == "__main__":
    crear_tablas()
