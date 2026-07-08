# app/models/user.py - VERSIÓN ACTUALIZADA CON ESTRUCTURA MUNICIPAL


from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.models.team import Team
from datetime import datetime
from app.utils.permisos import calcular_permisos_usuario

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)  # Cambiado de 64 a 100
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    telegram_id = db.Column(db.BigInteger, nullable=True, unique=True)
    
    # ✅ CAMPOS NUEVOS PARA ESTRUCTURA MUNICIPAL
    nivel = db.Column(db.String(30), default='cuadrilla')  
    # Valores: presidente, administrador, director, jefe, supervisor, cuadrilla, especialista
    
    rol_especifico = db.Column(db.String(50), nullable=True)
    # Valores según área (ver permisos.py):
    # - Agua: director, jefe_area_tecnica, jefe_area_comercial, supervisor, vactor, pipa, cuadrilla
    # - Drenaje: director, supervisor, vactor, cuadrilla
    # - Bomberos: director, camion_bombero, cuadrilla
    # - Otros: director, cuadrilla
    
    area = db.Column(db.String(50), nullable=True)
    # Valores: agua, drenaje, aseo, parques, ecologia, alumbrado, obra, seguridad, bomberos, presidencia
    
    subarea = db.Column(db.String(50), nullable=True)
    # Solo para agua: tecnica, comercial, drenaje
    
    # 🔧 Mantener este campo por compatibilidad
    role = db.Column(db.String(20), default='cuadrilla')
    # Valores: admin, director, supervisor, cuadrilla (compatibilidad con código existente)
    
    # Campos de permisos (se calcularán automáticamente)
    puede_asignar = db.Column(db.Boolean, default=False)
    puede_validar = db.Column(db.Boolean, default=False)
    puede_ver_todas_areas = db.Column(db.Boolean, default=False)
    puede_configurar = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    team = db.relationship('Team', backref='users')
    
    # Métodos de verificación (ACTUALIZADOS)
    def is_admin(self):
        return self.role == 'admin' or self.nivel == 'administrador'
    
    def es_presidente(self):
        return self.nivel == 'presidente' or self.area == 'presidencia'
    
    def es_director(self):
        return self.nivel == 'director' or self.role == 'director'
    
    def es_jefe_area(self):
        return 'jefe_area' in str(self.rol_especifico) if self.rol_especifico else False
    
    def es_supervisor(self):
        return self.nivel == 'supervisor' or self.role == 'supervisor'
    
    def es_cuadrilla(self):
        return self.nivel == 'cuadrilla' or self.role == 'cuadrilla'
    
    def es_especialista(self):
        return self.nivel == 'especialista'
    
    def get_area_responsable(self):
        """Obtiene el área que dirige"""
        if self.es_director() or self.es_jefe_area():
            return self.area
        return None
    
    def actualizar_permisos(self):
        """Calcula y actualiza permisos automáticamente usando app.utils.permisos"""
        try:
            from app.utils.permisos import calcular_permisos_usuario
            
            permisos = calcular_permisos_usuario(self)
            
            # Actualizar campos en base de datos
            self.puede_asignar = permisos.get('puede_asignar', False)
            self.puede_validar = permisos.get('puede_validar', False)
            self.puede_ver_todas_areas = permisos.get('puede_ver_todas_areas', False)
            self.puede_configurar = permisos.get('puede_configurar', False)
        except ImportError:
            # Si no existe el módulo de permisos, usar valores por defecto
            print("⚠️ Módulo de permisos no encontrado, usando valores por defecto")
            self.puede_asignar = False
            self.puede_validar = False
            self.puede_ver_todas_areas = False
            self.puede_configurar = False
    
    def to_dict(self):
        """Convertir a diccionario para JSON"""
        try:
            from app.utils.permisos import calcular_permisos_usuario
            permisos = calcular_permisos_usuario(self)
        except ImportError:
            permisos = {}
        
        return {
            'id': self.id,
            'nombre': self.nombre,
            'username': self.username,
            'team_id': self.team_id,
            'telegram_id': self.telegram_id,
            'nivel': self.nivel,
            'rol_especifico': self.rol_especifico,
            'area': self.area,
            'subarea': self.subarea,
            'role': self.role,  # Compatibilidad
            'team': self.team.nombre if self.team else None,
            'permisos': permisos,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active
        }
    
    def __repr__(self):
        area_display = f"({self.area}" + (f"/{self.subarea}" if self.subarea else "") + ")" if self.area else ""
        return f'<User {self.username} - {self.nivel} {area_display}>'

# AL FINAL de app/models/user.py, agregar:
from sqlalchemy import event

@event.listens_for(User, 'after_insert')
@event.listens_for(User, 'after_update')
def actualizar_permisos_automaticamente(mapper, connection, target):
    """
    Actualiza permisos automáticamente cuando se crea o modifica un usuario
    """
    # Solo si el usuario tiene los atributos necesarios
    if hasattr(target, 'actualizar_permisos'):
        target.actualizar_permisos()
    
    # También actualizar campos de permisos en la base de datos
    permisos = calcular_permisos_usuario(target)
    
    if hasattr(target, 'puede_asignar'):
        target.puede_asignar = permisos.get('puede_asignar', False)
    if hasattr(target, 'puede_validar'):
        target.puede_validar = permisos.get('puede_validar', False)
    if hasattr(target, 'puede_ver_todas_areas'):
        target.puede_ver_todas_areas = permisos.get('puede_ver_todas_areas', False)
    if hasattr(target, 'puede_configurar'):
        target.puede_configurar = permisos.get('puede_configurar', False)




