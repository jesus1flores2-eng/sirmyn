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
    municipio_id = db.Column(db.Integer, default=1)


    calles = db.relationship("Calle", back_populates="localidad")

    def __repr__(self):
        return f"<Localidad {self.nombre}>"


class Calle(db.Model):
    __tablename__ = 'calles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    localidad_id = db.Column(db.Integer, db.ForeignKey('localidades.id'), nullable=False)
    municipio_id = db.Column(db.Integer, default=1)

    localidad = db.relationship("Localidad", back_populates="calles")

    def __repr__(self):
        return f"<Calle {self.nombre} - {self.localidad.nombre}>"


class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    municipio_id = db.Column(db.Integer, default=1)
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
    plataforma = db.Column(db.String(20), default='telegram')
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    # ⭐ NUEVO CAMPO PARA EVITAR NOTIFICACIONES DUPLICADAS AL PRESIDENTE
    notificado_presidente = db.Column(db.Boolean, default=False)
        # ⭐ NUEVO CAMPO PARA FOLIO POR MUNICIPIO Y DEPARTAMENTO
    folio = db.Column(db.String(20), nullable=True)

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
            'localidad': self.localidad.nombre if self.localidad else None,
            'notificado_presidente': self.notificado_presidente
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
        
    @classmethod
    def generar_folio(cls, municipio_id, tipo):
        """
        Genera folio con prefijo por departamento y secuencia por municipio.
        Ejemplo: AGUA-001, DREN-001, ASEO-001, etc.
        """
        # Mapa de prefijos por tipo de reporte
        prefijos = {
            "Agua potable": "AGUA",
            "Drenaje": "DREN",
            "Aseo público": "ASEO",
            "Alumbrado público": "ALUM",
            "Parques y jardines": "PARQ",
            "Ecología": "ECOL",
            "Seguridad pública": "SEG",
            "Bomberos": "BOMB",
            "Obra pública": "OBRA",
            "Obras públicas": "OBRA",
            "Comunicación social": "COM",
            "Protección civil": "PROC",
            "Ambulancia": "AMB",
            "Desarrollo urbano": "DURB",
        }
        
        # Obtener prefijo según tipo (default: GEN)
        prefijo = prefijos.get(tipo, "GEN")
        
        # Contar reportes del municipio con ese prefijo
        total = cls.query.filter(
            cls.municipio_id == municipio_id,
            cls.folio.like(f"{prefijo}-%")
        ).count()
        
        # Generar folio simple
        return f"{prefijo}-{total + 1}"
    
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
    
    @property
    def folio_display(self):
        """Devuelve el folio si existe, o el ID como fallback"""
        return self.folio if self.folio else f"#{self.id}"


class Assignment(db.Model):
    __tablename__ = 'asignaciones'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    materiales_utilizados = db.Column(db.String(255))
    observaciones = db.Column(db.Text)
    evidencia_cuadrilla = db.Column(db.String(1000))
    motivo_reasignacion = db.Column(db.String(255), nullable=True)

    team = db.relationship("Team", backref="asignaciones")
    status = db.relationship("Status", backref="asignaciones")
    
    def to_dict(self):
        """Convertir a diccionario para JSON"""
        return {
            'id': self.id,
            'folio': self.folio,
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

    @property
    def folio_display(self):
        """Devuelve el folio si existe, o el ID como fallback"""
        return self.folio if self.folio else f"#{self.id}"
