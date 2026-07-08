"""
feedback.py
usuario devuelbe informacion de como fue tratado su reporte
"""


from app.extensions import db
from datetime import datetime

class RechazoUsuario(db.Model):
    __tablename__ = 'rechazos_usuario'
    
    id = db.Column(db.Integer, primary_key=True)  # CAMBIADO: Integer no Numeric
    reporte_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False)
    usuario_id = db.Column(db.BigInteger, nullable=False)  # Mantener como está
    motivo = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    evidencia_path = db.Column(db.String(255), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    procesado = db.Column(db.Boolean, default=False)  # Agregar esta columna
    
    # Relación
    reporte = db.relationship('Report', backref=db.backref('rechazos', lazy=True))
    
    def __repr__(self):
        return f'<RechazoUsuario {self.id} reporte:{self.reporte_id}>'


class EncuestaSatisfaccion(db.Model):
    __tablename__ = 'encuestas_satisfaccion'
    
    id = db.Column(db.Integer, primary_key=True)  # CAMBIADO: Integer no Numeric
    reporte_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False)
    usuario_id = db.Column(db.BigInteger, nullable=False)  # Mantener como está
    calificacion = db.Column(db.Integer, nullable=False)
    velocidad = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación
    reporte = db.relationship('Report', backref=db.backref('encuestas', lazy=True))
    
    def __repr__(self):
        return f'<EncuestaSatisfaccion {self.id} reporte:{self.reporte_id}>'


