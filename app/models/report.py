"""
report.py
datos de un reporte
"""


from app.extensions import db
from datetime import datetime


class Localidad(db.Model):
    __tablename__ = 'localidades'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    latitud_central = db.Column(db.Float, nullable=True)
    longitud_central = db.Column(db.Float, nullable=True)


    calles = db.relationship("Calle", back_populates="localidad")

    def __repr__(self):
        return f"<Localidad {self.nombre}>"


class Calle(db.Model):
    __tablename__ = 'calles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    localidad_id = db.Column(db.Integer, db.ForeignKey('localidades.id'), nullable=False)

    localidad = db.relationship("Localidad", back_populates="calles")

    def __repr__(self):
        return f"<Calle {self.nombre} - {self.localidad.nombre}>"


class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    telefono = db.Column(db.String(20))
    reportante = db.Column(db.String(100))
    tipo = db.Column(db.String(50))
    subtipo = db.Column(db.String(100))
    numero = db.Column(db.String(20))
    entre_calles = db.Column(db.String(200))
    descripcion_problema = db.Column(db.Text)
    evidencia = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    numero_cuenta = db.Column(db.String(50))
    plataforma = db.Column(db.String(20), default='telegram')  # NUEVO: telegram, whatsapp, ventanilla
    latitud = db.Column(db.Float, nullable=True)      # ← NUEVO
    longitud = db.Column(db.Float, nullable=True)     # ← NUEVO

    # Relaciones a tablas maestras
    calle_id = db.Column(db.Integer, db.ForeignKey('calles.id'), nullable=False)
    localidad_id = db.Column(db.Integer, db.ForeignKey('localidades.id'), nullable=False)

    calle = db.relationship("Calle")
    localidad = db.relationship("Localidad")

    # Relación con asignaciones
    asignaciones = db.relationship("Assignment", backref="report")

    def to_dict(self):
        """Convertir a diccionario para JSON"""
        return {
            'id': self.id,
            'telefono': self.telefono,
            'reportante': self.reportante,
            'tipo': self.tipo,
            'subtipo': self.subtipo,
            'numero': self.numero,
            'entre_calles': self.entre_calles,
            'descripcion_problema': self.descripcion_problema,
            'evidencia': self.evidencia,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'numero_cuenta': self.numero_cuenta,
            'plataforma': self.plataforma,
            'calle_id': self.calle_id,
            'localidad_id': self.localidad_id,
            'calle': self.calle.nombre if self.calle else None,
            'localidad': self.localidad.nombre if self.localidad else None
        }

    @classmethod
    def existe_reporte(cls, calle_id, numero, localidad_id):
        """
        Busca si ya existe un reporte en la misma calle, número y localidad.
        """
        return cls.query.filter(
            cls.calle_id == calle_id,
            cls.numero == numero.strip(),
            cls.localidad_id == localidad_id
        ).first()
    
    def get_ultima_asignacion(self):
        """Obtiene la última asignación del reporte"""
        if self.asignaciones:
            return sorted(self.asignaciones, key=lambda x: x.timestamp, reverse=True)[0]
        return None
    
    def get_estado_actual(self):
        """Obtiene el estado actual del reporte"""
        asignacion = self.get_ultima_asignacion()
        if asignacion and asignacion.status:
            return asignacion.status.descripcion
        return "Sin asignar"
    
    def get_cuadrilla_actual(self):
        """Obtiene la cuadrilla actual asignada"""
        asignacion = self.get_ultima_asignacion()
        if asignacion and asignacion.team:
            return asignacion.team.nombre
        return "Sin cuadrilla"


class Assignment(db.Model):
    __tablename__ = 'asignaciones'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    materiales_utilizados = db.Column(db.String(255))
    observaciones = db.Column(db.Text)
    evidencia_cuadrilla = db.Column(db.String(200))
    motivo_reasignacion = db.Column(db.String(255), nullable=True)

    team = db.relationship("Team", backref="asignaciones")
    status = db.relationship("Status", backref="asignaciones")
    
    def to_dict(self):
        """Convertir a diccionario para JSON"""
        return {
            'id': self.id,
            'report_id': self.report_id,
            'team_id': self.team_id,
            'status_id': self.status_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'materiales_utilizados': self.materiales_utilizados,
            'observaciones': self.observaciones,
            'evidencia_cuadrilla': self.evidencia_cuadrilla,
            'motivo_reasignacion': self.motivo_reasignacion,
            'team': self.team.nombre if self.team else None,
            'status': self.status.descripcion if self.status else None
        }


