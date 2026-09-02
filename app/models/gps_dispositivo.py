from app.extensions import db
from datetime import datetime

class GpsDispositivo(db.Model):
    __tablename__ = 'gps_dispositivos'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    imei = db.Column(db.String(50), unique=True, nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    telefono_chip = db.Column(db.String(20), nullable=True)  # NUEVO
    compania = db.Column(db.String(20), nullable=True)  # NUEVO: Telcel, Movistar
    plan_datos = db.Column(db.String(50), nullable=True)  # NUEVO
    fecha_vencimiento = db.Column(db.Date, nullable=True)  # NUEVO
    ultima_latitud = db.Column(db.Float, nullable=True)
    ultima_longitud = db.Column(db.Float, nullable=True)
    ultima_velocidad = db.Column(db.Float, nullable=True)
    ultima_actualizacion = db.Column(db.DateTime, nullable=True)
    
    team = db.relationship('Team', backref='dispositivos_gps')
    
    def __repr__(self):
        return f'<GpsDispositivo {self.nombre}>'
