import os
from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from app.extensions import db, login_manager
from config import config_dict
from app.routes import register_blueprints
import pytz
from app.utils import permisos

csrf = CSRFProtect()
LOCAL_TZ = pytz.timezone('America/Mexico_City')

def datetime_local(value, formato='%d/%m/%Y %H:%M'):
    if value is None:
        return ''
    if value.tzinfo is None:
        value = value.replace(tzinfo=pytz.utc)
    return value.astimezone(LOCAL_TZ).strftime(formato)

def create_app():
    config_name = os.getenv('FLASK_CONFIG', 'default')
    Config = config_dict.get(config_name, config_dict['default'])
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # ⭐⭐⭐ CONFIGURAR DatabaseManager AQUÍ ⭐⭐⭐
    from app.services.db_manager import DatabaseManager
    DatabaseManager.set_app(app)
    print("✅ DatabaseManager configurado con la app")

    # Crear carpetas
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    evidencias_dir = os.path.join(app.root_path, 'static', 'evidencias')
    os.makedirs(evidencias_dir, exist_ok=True)
    app.config['CUADRILLA_UPLOAD_FOLDER'] = evidencias_dir

    # Inicializar extensiones
    csrf.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Context processor para permisos
    @app.context_processor
    def inject_permisos():
        return dict(
            calcular_permisos=permisos.calcular_permisos_usuario,
            obtener_roles_por_area=permisos.obtener_roles_por_area,
            puede_asignar_reporte=permisos.puede_asignar_reporte
        )

    # Registrar blueprints
    register_blueprints(app)

    # WhatsApp (solo inicialización)
    try:
        from app.services.whatsapp_bot import init_bot
        init_bot(app)
        print("✅ WhatsApp Bot configurado")
    except Exception as e:
        print(f"⚠️ WhatsApp Bot: {e}")

    # Configuración Jinja2
    app.jinja_env.filters['localtime'] = datetime_local

    with app.app_context():
        from app.models.user import User
        @login_manager.user_loader
        def load_user(user_id):
            return User.query.get(int(user_id))
        db.create_all()
        print("✅ Base de datos lista")
        
    # Iniciar scheduler para tareas programadas
    from app.scheduler import iniciar_scheduler
    scheduler = iniciar_scheduler()
    if scheduler:
       app.scheduler = scheduler

    print("\n" + "="*60)
    print("🚀 SISTEMA SIRMYN INICIADO")
    print("="*60)
    print(f"📁 Uploads: {app.config['UPLOAD_FOLDER']}")
    print(f"🌐 URL: http://localhost:5000")
    print("🤖 Modo: Webhook (producción)")
    print("="*60)

    return app
