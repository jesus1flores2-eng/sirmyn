"""
emergency.py
Modelo para emergencias - Tabla separada de reportes normales
"""
from datetime import datetime
from app.extensions import db

class Emergency(db.Model):
    __tablename__ = 'emergencies'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Identificación municipio (para multi-municipio)
    municipio_id = db.Column(db.Integer, default=1)  # Default: primer municipio
    municipio_nombre = db.Column(db.String(100), default="Municipio SIRMYN")
    
    # Tipo de emergencia
    tipo = db.Column(db.String(50), nullable=False)  # 'policia', 'bomberos', 'ambulancia', 'violeta'
    subtipo = db.Column(db.String(100))  # 'accidente_vial', 'incendio_estructural', etc.
    
    # Ubicación (OBLIGATORIA en emergencias)
    latitud = db.Column(db.Float, nullable=False)
    longitud = db.Column(db.Float, nullable=False)
    direccion_aproximada = db.Column(db.String(200))
    
    # Información del reportante
    reportante = db.Column(db.String(100), nullable=False)
    telegram_user_id = db.Column(db.Integer, nullable=False)
    telegram_username = db.Column(db.String(100))
    
    # Descripción de la emergencia
    descripcion = db.Column(db.String(500))
    
    # Campos específicos de emergencia
    nivel_urgencia = db.Column(db.Integer, default=3)  # 1-5 (5=máximo)
    personas_heridas = db.Column(db.Boolean, default=False)
    personas_atrapadas = db.Column(db.Boolean, default=False)
    peligro_vida = db.Column(db.Boolean, default=False)
    
    # Seguimiento y asignación
    unidades_asignadas = db.Column(db.JSON, default=dict)  # {'patrulla_12': True, 'ambulancia_3': False}
    tiempo_respuesta_estimado = db.Column(db.Integer)  # minutos estimados
    tiempo_respuesta_real = db.Column(db.Integer)  # minutos reales
    
    # Contacto de emergencia adicional
    contacto_adicional = db.Column(db.String(50))
    
    # Estado
    status = db.Column(db.String(50), default='reportada')  
    # reportada, verificando, atendiendo, en_camino, en_sitio, resuelta, cancelada
    
    # Timestamps
    timestamp_reporte = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    timestamp_atencion = db.Column(db.DateTime)
    timestamp_resuelta = db.Column(db.DateTime)
    
    # Metadata
    plataforma = db.Column(db.String(20), default='telegram_emergencias')
    folio_publico = db.Column(db.String(20))  # Ej: E-2024-00123
    
    def __init__(self, **kwargs):
        super(Emergency, self).__init__(**kwargs)
        # Generar folio público automático
        if not self.folio_publico:
            self.folio_publico = self.generar_folio()
    
    def generar_folio(self):
        """Genera folio público tipo E-YYYY-NNNNN"""
        from datetime import datetime
        year = datetime.utcnow().year
        # Esto se completará con el ID después del commit
        return f"E-{year}-{self.id:05d}" if self.id else "E-PENDIENTE"
    
    def to_dict(self):
        """Convierte a diccionario para JSON"""
        return {
            'id': self.id,
            'folio_publico': self.folio_publico,
            'tipo': self.tipo,
            'subtipo': self.subtipo,
            'ubicacion': {
                'latitud': self.latitud,
                'longitud': self.longitud,
                'direccion': self.direccion_aproximada
            },
            'reportante': self.reportante,
            'descripcion': self.descripcion,
            'nivel_urgencia': self.nivel_urgencia,
            'status': self.status,
            'timestamp_reporte': self.timestamp_reporte.isoformat() if self.timestamp_reporte else None,
            'tiempo_respuesta_estimado': self.tiempo_respuesta_estimado
        }
    
    def __repr__(self):
        return f'<Emergency {self.folio_publico} - {self.tipo} - {self.status}>'


# Tabla para registro de notificaciones de emergencia
class EmergencyNotification(db.Model):
    __tablename__ = 'emergency_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    emergency_id = db.Column(db.Integer, db.ForeignKey('emergencies.id'), nullable=False)
    destinatario_tipo = db.Column(db.String(50))  # 'comisario', 'patrulla', 'bomberos', 'ambulancias'
    destinatario_id = db.Column(db.String(100))  # ID de Telegram o grupo
    mensaje = db.Column(db.Text)
    timestamp_envio = db.Column(db.DateTime, default=datetime.utcnow)
    entregado = db.Column(db.Boolean, default=False)
    leido = db.Column(db.Boolean, default=False)
    
    emergency = db.relationship('Emergency', backref=db.backref('notificaciones', lazy=True))
    
    def __repr__(self):
        return f'<EmergencyNotification {self.id} for {self.emergency_id}>'