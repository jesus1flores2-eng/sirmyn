from flask import Flask

from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.teams import teams_bp
from app.routes.supervisor import supervisor_bp
from app.routes.inteligencia import inteligencia_bp
from app.routes.captura import captura_bp
from app.routes.telegram_routes import telegram_bp

def register_blueprints(app):
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(captura_bp, url_prefix='/captura')
    app.register_blueprint(telegram_bp, url_prefix='/telegram')
    app.register_blueprint(teams_bp, url_prefix='/teams')
    app.register_blueprint(supervisor_bp, url_prefix='/supervisor')
    app.register_blueprint(inteligencia_bp, url_prefix='/inteligencia')
    print("✅ Blueprints registrados")
