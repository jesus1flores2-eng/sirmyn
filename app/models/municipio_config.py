"""
Modelo de configuración por municipio
Controla departamentos activos, plan, límite de cuadrillas y funciones
"""
from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class MunicipioConfig(db.Model):
    __tablename__ = 'municipios_config'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    plan = db.Column(db.String(20), default='basico')
    departamentos_activos = db.Column(db.Text, default='agua,drenaje')
    emergencias_activas = db.Column(db.Text, default='')
    limite_cuadrillas = db.Column(db.Integer, default=3)
    activo = db.Column(db.Boolean, default=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    logo_url = db.Column(db.Text, nullable=True)
    aviso_privacidad = db.Column(db.Text, nullable=True)
    bot_token = db.Column(db.Text, nullable=True)

    usuario = db.Column(db.String(50), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)

    ver_cuadrillas = db.Column(db.Boolean, default=True)
    ver_estados = db.Column(db.Boolean, default=True)
    ver_inteligencia = db.Column(db.Boolean, default=False)
    ver_gps = db.Column(db.Boolean, default=False)
    ver_encuestas = db.Column(db.Boolean, default=False)
    ver_exportar = db.Column(db.Boolean, default=True)
    ver_historial = db.Column(db.Boolean, default=True)
    ver_mapa = db.Column(db.Boolean, default=True)
    ver_test = db.Column(db.Boolean, default=False)
    ver_editar_coordenadas = db.Column(db.Boolean, default=False)
    ver_filtros = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_emergencias_lista(self):
        """Devuelve lista de emergencias activas"""
        if not self.emergencias_activas:
            return []
        return [e.strip() for e in self.emergencias_activas.split(',') if e.strip()]

    def set_emergencias_lista(self, lista):
        """Guarda lista de emergencias"""
        self.emergencias_activas = ','.join(lista)

    def get_departamentos_lista(self):
        if not self.departamentos_activos:
            return []
        return [d.strip() for d in self.departamentos_activos.split(',') if d.strip()]

    def set_departamentos_lista(self, lista):
        self.departamentos_activos = ','.join(lista)

    def departamento_activo(self, area):
        return area in self.get_departamentos_lista()

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'plan': self.plan,
            'departamentos_activos': self.get_departamentos_lista(),
            'limite_cuadrillas': self.limite_cuadrillas,
            'activo': self.activo,
            'fecha_vencimiento': self.fecha_vencimiento.isoformat() if self.fecha_vencimiento else None,
            'ver_cuadrillas': self.ver_cuadrillas,
            'ver_estados': self.ver_estados,
            'ver_inteligencia': self.ver_inteligencia,
            'ver_gps': self.ver_gps,
            'ver_encuestas': self.ver_encuestas
        }

    def __repr__(self):
        return f'<MunicipioConfig {self.nombre} - {self.plan}>'
