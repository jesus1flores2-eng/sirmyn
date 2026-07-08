# app/models/team.py - VERSION para cuadrillas

from app.extensions import db

class Team(db.Model):
    __tablename__ = 'teams'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    # SOLO agregar estas dos columnas nuevas, NADA MÁS
    area = db.Column(db.String(50))
    descripcion = db.Column(db.Text, default='')
    
    
    def __repr__(self):
        return f'<Team {self.nombre}>'


