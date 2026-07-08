#!/usr/bin/env python3
"""
Carga datos desde un archivo Excel con múltiples hojas.
Valida que los encabezados sean correctos antes de cargar.
Uso: python cargar_datos_municipio.py
"""
import sys
import os
import pandas as pd
from app import create_app
from app.extensions import db
from app.models.report import Localidad, Calle
from app.models.user import User
from app.models.team import Team
from app.models.status import Status

app = create_app()

# Encabezados esperados para cada hoja
ENCABEZADOS_ESPERADOS = {
    'localidades': ['id', 'nombre', 'latitud_central', 'longitud_central'],
    'calles': ['id', 'nombre', 'localidad_id', 'localidad_nombre'],
    'status': ['id', 'descripcion', 'color'],
    'teams': ['id', 'nombre', 'area', 'descripcion'],
    'users': ['id', 'nombre', 'username', 'password_hash', 'team_id', 'team_nombre', 'telegram_id', 'nivel', 'rol_especifico', 'area', 'subarea', 'role', 'puede_asignar', 'puede_validar', 'puede_ver_todas_areas', 'puede_configurar', 'created_at', 'is_active']
}

def validar_encabezados(df, hoja_nombre):
    """Valida que los encabezados coincidan con los esperados"""
    esperados = ENCABEZADOS_ESPERADOS.get(hoja_nombre, [])
    actuales = list(df.columns)
    
    # Verificar que todas las columnas esperadas estén presentes
    for col in esperados:
        if col not in actuales:
            print(f"❌ Error: Columna '{col}' no encontrada en hoja '{hoja_nombre}'")
            print(f"   Columnas esperadas: {esperados}")
            print(f"   Columnas actuales: {actuales}")
            return False
    return True

def cargar_localidades(df):
    print("\n📥 CARGANDO LOCALIDADES...")
    if not validar_encabezados(df, 'localidades'):
        return 0
    count = 0
    for _, row in df.iterrows():
        nombre = str(row['nombre']).strip()
        if not nombre:
            continue
        loc = Localidad.query.filter_by(nombre=nombre).first()
        if not loc:
            loc = Localidad(
                nombre=nombre,
                latitud_central=float(row['latitud_central']) if pd.notna(row.get('latitud_central')) else None,
                longitud_central=float(row['longitud_central']) if pd.notna(row.get('longitud_central')) else None
            )
            db.session.add(loc)
            count += 1
    db.session.commit()
    print(f"   ✅ {count} localidades agregadas")
    return count

def cargar_calles(df, localidades_dict):
    print("\n📥 CARGANDO CALLES...")
    if not validar_encabezados(df, 'calles'):
        return 0
    count = 0
    for _, row in df.iterrows():
        nombre = str(row['nombre']).strip()
        localidad_nombre = str(row.get('localidad_nombre', '')).strip()
        if not nombre or not localidad_nombre:
            continue
        localidad_id = localidades_dict.get(localidad_nombre)
        if not localidad_id:
            print(f"   ⚠️ Localidad '{localidad_nombre}' no encontrada para calle '{nombre}'")
            continue
        calle = Calle.query.filter_by(nombre=nombre, localidad_id=localidad_id).first()
        if not calle:
            calle = Calle(nombre=nombre, localidad_id=localidad_id)
            db.session.add(calle)
            count += 1
    db.session.commit()
    print(f"   ✅ {count} calles agregadas")
    return count

def cargar_status(df):
    print("\n📥 CARGANDO ESTADOS...")
    if not validar_encabezados(df, 'status'):
        return 0
    count = 0
    for _, row in df.iterrows():
        descripcion = str(row['descripcion']).strip()
        if not descripcion:
            continue
        status = Status.query.filter_by(descripcion=descripcion).first()
        if not status:
            status = Status(
                descripcion=descripcion,
                color=str(row['color']).strip() if pd.notna(row.get('color')) else '#cccccc'
            )
            db.session.add(status)
            count += 1
    db.session.commit()
    print(f"   ✅ {count} estados agregados")
    return count

def cargar_teams(df):
    print("\n📥 CARGANDO EQUIPOS...")
    if not validar_encabezados(df, 'teams'):
        return 0
    count = 0
    for _, row in df.iterrows():
        nombre = str(row['nombre']).strip()
        if not nombre:
            continue
        team = Team.query.filter_by(nombre=nombre).first()
        if not team:
            team = Team(
                nombre=nombre,
                area=str(row['area']).strip() if pd.notna(row.get('area')) else None,
                descripcion=str(row['descripcion']).strip() if pd.notna(row.get('descripcion')) else None
            )
            db.session.add(team)
            count += 1
    db.session.commit()
    print(f"   ✅ {count} equipos agregados")
    return count

def cargar_usuarios(df, teams_dict):
    print("\n📥 CARGANDO USUARIOS...")
    if not validar_encabezados(df, 'users'):
        return 0
    count = 0
    for _, row in df.iterrows():
        username = str(row['username']).strip()
        nombre = str(row['nombre']).strip()
        if not username or not nombre:
            continue
        
        team_nombre = str(row.get('team_nombre', '')).strip()
        team_id = teams_dict.get(team_nombre) if team_nombre else None
        
        if User.query.filter_by(username=username).first():
            print(f"   ⚠️ Usuario {username} ya existe, omitiendo...")
            continue
        
        usuario = User(
            nombre=nombre,
            username=username,
            password_hash=str(row['password_hash']).strip() if pd.notna(row.get('password_hash')) else '',
            team_id=team_id,
            telegram_id=int(row['telegram_id']) if pd.notna(row.get('telegram_id')) and row.get('telegram_id') else None,
            nivel=str(row['nivel']).strip() if pd.notna(row.get('nivel')) else None,
            rol_especifico=str(row['rol_especifico']).strip() if pd.notna(row.get('rol_especifico')) else None,
            area=str(row['area']).strip() if pd.notna(row.get('area')) else None,
            subarea=str(row['subarea']).strip() if pd.notna(row.get('subarea')) else None,
            role=str(row['role']).strip() if pd.notna(row.get('role')) else None,
            puede_asignar=bool(row.get('puede_asignar', 0)),
            puede_validar=bool(row.get('puede_validar', 0)),
            puede_ver_todas_areas=bool(row.get('puede_ver_todas_areas', 0)),
            puede_configurar=bool(row.get('puede_configurar', 0)),
            is_active=bool(row.get('is_active', 1))
        )
        db.session.add(usuario)
        count += 1
        print(f"   ✅ Usuario {username} agregado")
    db.session.commit()
    print(f"   ✅ {count} usuarios agregados")
    return count

def main():
    print("🚀 CARGANDO DATOS DEL MUNICIPIO DESDE EXCEL")
    print("=" * 60)
    
    archivo_excel = "datos_municipio.xlsx"
    
    if not os.path.exists(archivo_excel):
        print(f"❌ Archivo {archivo_excel} no encontrado.")
        print("   Primero ejecuta: python exportar_datos.py para generar la plantilla.")
        sys.exit(1)
    
    with app.app_context():
        try:
            xls = pd.ExcelFile(archivo_excel)
            hojas = xls.sheet_names
            print(f"📊 Hojas encontradas: {', '.join(hojas)}")
            
            if 'localidades' in hojas:
                df = pd.read_excel(archivo_excel, sheet_name='localidades')
                cargar_localidades(df)
            
            if 'calles' in hojas:
                localidades_dict = {loc.nombre: loc.id for loc in Localidad.query.all()}
                df = pd.read_excel(archivo_excel, sheet_name='calles')
                cargar_calles(df, localidades_dict)
            
            if 'status' in hojas:
                df = pd.read_excel(archivo_excel, sheet_name='status')
                cargar_status(df)
            
            if 'teams' in hojas:
                df = pd.read_excel(archivo_excel, sheet_name='teams')
                cargar_teams(df)
            
            if 'users' in hojas:
                teams_dict = {team.nombre: team.id for team in Team.query.all()}
                df = pd.read_excel(archivo_excel, sheet_name='users')
                cargar_usuarios(df, teams_dict)
            
            print("\n" + "=" * 60)
            print("✅ CARGA COMPLETADA")
            print("=" * 60)
            print(f"\n📊 RESUMEN FINAL:")
            print(f"   • Localidades: {Localidad.query.count()}")
            print(f"   • Calles: {Calle.query.count()}")
            print(f"   • Estados: {Status.query.count()}")
            print(f"   • Equipos: {Team.query.count()}")
            print(f"   • Usuarios: {User.query.count()}")
            
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    main()
