# app/models/status.py
# estado de un reporte
from app.extensions import db

class Status(db.Model):
    __tablename__ = 'status'
    
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(100))
    color = db.Column(db.String(10), default='#ccc')

    def __repr__(self):
        return f'<Status {self.descripcion}>'


