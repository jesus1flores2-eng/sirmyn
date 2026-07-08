# app/services/db_manager.py
import threading
from app.extensions import db

class DatabaseManager:
    _app = None
    _lock = threading.RLock()
    
    @classmethod
    def get_app(cls):
        with cls._lock:
            if cls._app is None:
                raise RuntimeError("❌ App Flask no establecida para DatabaseManager")
            return cls._app
    
    @classmethod
    def set_app(cls, app):
        with cls._lock:
            cls._app = app
            print("✅ App establecida para DatabaseManager")
