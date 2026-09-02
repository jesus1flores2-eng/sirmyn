#!/usr/bin/env python3
"""
Exporta datos de la base de datos a un archivo Excel.
Uso: python exportar_datos_municipio.py [municipio_id]
Si no se especifica municipio_id, exporta todos.
"""
import sys
import pandas as pd
from datetime import datetime
from app import create_app
from app.extensions import db
from app.models.report import Localidad, Calle
from app.models.user import User
from app.models.team import Team
from app.models.status import Status

app = create_app()

def exportar_datos(municipio_id=None):
    """
    Exporta datos a Excel.
    Si municipio_id es None, exporta todos los municipios.
    Si municipio_id es un número, filtra por ese municipio.
    """
    filtro = f"_municipio_{municipio_id}" if municipio_id else "_todos"
    nombre_archivo = f"datos_municipio{filtro}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    with app.app_context():
        print("📤 EXPORTANDO DATOS DESDE LA BASE DE DATOS...")
        if municipio_id:
            print(f"   🎯 Filtrando por municipio_id={municipio_id}")
        
        # 1. Localidades
        if municipio_id:
            localidades = Localidad.query.filter_by(municipio_id=municipio_id).all()
        else:
            localidades = Localidad.query.all()
        
        df_loc = pd.DataFrame([{
            'id': l.id,
            'nombre': l.nombre,
            'latitud_central': l.latitud_central,
            'longitud_central': l.longitud_central,
            'municipio_id': l.municipio_id or 1
        } for l in localidades])
        
        # 2. Calles
        if municipio_id:
            calles = Calle.query.filter_by(municipio_id=municipio_id).all()
        else:
            calles = Calle.query.all()
        
        df_calles = pd.DataFrame([{
            'id': c.id,
            'nombre': c.nombre,
            'localidad_id': c.localidad_id,
            'localidad_nombre': c.localidad.nombre if c.localidad else '',
            'municipio_id': c.municipio_id or 1
        } for c in calles])
        
        # 3. Estados
        if municipio_id:
            statuses = Status.query.filter_by(municipio_id=municipio_id).all()
        else:
            statuses = Status.query.all()
        
        df_status = pd.DataFrame([{
            'id': s.id,
            'descripcion': s.descripcion,
            'color': s.color,
            'municipio_id': s.municipio_id or 1
        } for s in statuses])
        
        # 4. Equipos
        if municipio_id:
            teams = Team.query.filter_by(municipio_id=municipio_id).all()
        else:
            teams = Team.query.all()
        
        df_teams = pd.DataFrame([{
            'id': t.id,
            'nombre': t.nombre,
            'area': t.area,
            'descripcion': t.descripcion,
            'municipio_id': t.municipio_id or 1
        } for t in teams])
        
        # 5. Usuarios
        if municipio_id:
            users = User.query.filter_by(municipio_id=municipio_id).all()
        else:
            users = User.query.all()
        
        df_users = pd.DataFrame([{
            'id': u.id,
            'nombre': u.nombre,
            'username': u.username,
            'password_hash': u.password_hash,
            'team_id': u.team_id,
            'team_nombre': u.team.nombre if u.team else '',
            'telegram_id': u.telegram_id,
            'nivel': u.nivel,
            'rol_especifico': u.rol_especifico,
            'area': u.area,
            'subarea': u.subarea,
            'role': u.role,
            'puede_asignar': u.puede_asignar,
            'puede_validar': u.puede_validar,
            'puede_ver_todas_areas': u.puede_ver_todas_areas,
            'puede_configurar': u.puede_configurar,
            'created_at': u.created_at,
            'is_active': u.is_active,
            'municipio_id': u.municipio_id or 1
        } for u in users])
        
        # Guardar en Excel
        with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
            df_loc.to_excel(writer, sheet_name='localidades', index=False)
            df_calles.to_excel(writer, sheet_name='calles', index=False)
            df_status.to_excel(writer, sheet_name='status', index=False)
            df_teams.to_excel(writer, sheet_name='teams', index=False)
            df_users.to_excel(writer, sheet_name='users', index=False)
        
        print(f"✅ Datos exportados a: {nombre_archivo}")
        print(f"   • Localidades: {len(df_loc)}")
        print(f"   • Calles: {len(df_calles)}")
        print(f"   • Estados: {len(df_status)}")
        print(f"   • Equipos: {len(df_teams)}")
        print(f"   • Usuarios: {len(df_users)}")

if __name__ == "__main__":
    # Uso: python exportar_datos_municipio.py [municipio_id]
    if len(sys.argv) > 1:
        try:
            mun_id = int(sys.argv[1])
            exportar_datos(municipio_id=mun_id)
        except ValueError:
            print("❌ El municipio_id debe ser un número entero")
            print("Uso: python exportar_datos_municipio.py [municipio_id]")
            print("Ejemplo: python exportar_datos_municipio.py 1")
    else:
        exportar_datos()
