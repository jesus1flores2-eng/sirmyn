#!/usr/bin/env python3
"""
Carga datos desde un archivo Excel con múltiples hojas.
Uso: python cargar_datos_municipio.py [archivo_excel] [municipio_id]
Si no se especifica municipio_id, usa el que viene en el Excel o 1 por defecto.
"""
import os
import sys
import pandas as pd
import numpy as np
from app import create_app
from app.extensions import db
from app.models.report import Localidad, Calle
from app.models.user import User
from app.models.team import Team
from app.models.status import Status

app = create_app()

def cargar_datos(archivo="datos_municipio.xlsx", municipio_id_default=None):
    """
    Carga datos desde Excel.
    Si municipio_id_default es especificado, sobreescribe el del Excel.
    """
    print("=" * 60)
    print("🚀 CARGANDO DATOS DESDE EXCEL")
    print("=" * 60)
    
    # Verificar que el archivo existe
    print(f"\n📂 ¿Existe '{archivo}'? {os.path.exists(archivo)}")
    
    if not os.path.exists(archivo):
        print(f"❌ El archivo '{archivo}' no existe.")
        return
    
    # Verificar las hojas del Excel
    try:
        xl = pd.ExcelFile(archivo)
        hojas = xl.sheet_names
        print(f"📋 Hojas encontradas: {hojas}")
    except Exception as e:
        print(f"❌ ERROR al leer el Excel: {e}")
        return
    
    with app.app_context():
        print("\n📥 INICIANDO CARGA DE DATOS...")
        if municipio_id_default:
            print(f"   🎯 Usando municipio_id={municipio_id_default} para todos los registros")
        
        # ============================
        # 1. CARGAR LOCALIDADES
        # ============================
        try:
            if 'localidades' in hojas:
                print("\n📥 Cargando localidades...")
                df_loc = pd.read_excel(archivo, sheet_name='localidades')
                count_loc = 0
                for _, row in df_loc.iterrows():
                    if pd.isna(row['nombre']):
                        continue
                    
                    # Obtener municipio_id
                    if municipio_id_default:
                        mun_id = municipio_id_default
                    elif 'municipio_id' in row and pd.notna(row['municipio_id']):
                        mun_id = int(row['municipio_id'])
                    else:
                        mun_id = 1
                    
                    loc = Localidad.query.filter_by(
                        nombre=row['nombre'], 
                        municipio_id=mun_id
                    ).first()
                    
                    if not loc:
                        loc = Localidad(
                            nombre=row['nombre'],
                            latitud_central=row.get('latitud_central') if pd.notna(row.get('latitud_central')) else None,
                            longitud_central=row.get('longitud_central') if pd.notna(row.get('longitud_central')) else None,
                            municipio_id=mun_id
                        )
                        db.session.add(loc)
                        count_loc += 1
                db.session.commit()
                print(f"   ✅ {count_loc} localidades agregadas")
        except Exception as e:
            print(f"   ❌ Error al cargar localidades: {e}")
            db.session.rollback()
        
        # ============================
        # 2. CARGAR CALLES
        # ============================
        try:
            if 'calles' in hojas:
                print("\n📥 Cargando calles...")
                df_calles = pd.read_excel(archivo, sheet_name='calles')
                count_calles = 0
                for _, row in df_calles.iterrows():
                    if pd.isna(row['nombre']) or pd.isna(row['localidad_nombre']):
                        continue
                    
                    # Obtener municipio_id
                    if municipio_id_default:
                        mun_id = municipio_id_default
                    elif 'municipio_id' in row and pd.notna(row['municipio_id']):
                        mun_id = int(row['municipio_id'])
                    else:
                        mun_id = 1
                    
                    loc = Localidad.query.filter_by(
                        nombre=row['localidad_nombre'],
                        municipio_id=mun_id
                    ).first()
                    
                    if not loc:
                        print(f"   ⚠️ Localidad '{row['localidad_nombre']}' no encontrada para municipio {mun_id}")
                        continue
                    
                    calle = Calle.query.filter_by(
                        nombre=row['nombre'], 
                        localidad_id=loc.id,
                        municipio_id=mun_id
                    ).first()
                    
                    if not calle:
                        calle = Calle(
                            nombre=row['nombre'], 
                            localidad_id=loc.id,
                            municipio_id=mun_id
                        )
                        db.session.add(calle)
                        count_calles += 1
                db.session.commit()
                print(f"   ✅ {count_calles} calles agregadas")
        except Exception as e:
            print(f"   ❌ Error al cargar calles: {e}")
            db.session.rollback()
        
        # ============================
        # 3. CARGAR ESTADOS (STATUS)
        # ============================
        try:
            if 'status' in hojas:
                print("\n📥 Cargando estados...")
                df_status = pd.read_excel(archivo, sheet_name='status')
                count_status = 0
                for _, row in df_status.iterrows():
                    if pd.isna(row['descripcion']):
                        continue
                    
                    # Obtener municipio_id
                    if municipio_id_default:
                        mun_id = municipio_id_default
                    elif 'municipio_id' in row and pd.notna(row['municipio_id']):
                        mun_id = int(row['municipio_id'])
                    else:
                        mun_id = 1
                    
                    st = Status.query.filter_by(
                        descripcion=row['descripcion'],
                        municipio_id=mun_id
                    ).first()
                    
                    if not st:
                        color = row.get('color') if pd.notna(row.get('color')) else '#cccccc'
                        st = Status(
                            descripcion=row['descripcion'], 
                            color=color,
                            municipio_id=mun_id
                        )
                        db.session.add(st)
                        count_status += 1
                db.session.commit()
                print(f"   ✅ {count_status} estados agregados")
        except Exception as e:
            print(f"   ❌ Error al cargar estados: {e}")
            db.session.rollback()
        
        # ============================
        # 4. CARGAR EQUIPOS (TEAMS)
        # ============================
        try:
            if 'teams' in hojas:
                print("\n📥 Cargando equipos...")
                df_teams = pd.read_excel(archivo, sheet_name='teams')
                count_teams = 0
                for _, row in df_teams.iterrows():
                    if pd.isna(row['nombre']):
                        continue
                    
                    # Obtener municipio_id
                    if municipio_id_default:
                        mun_id = municipio_id_default
                    elif 'municipio_id' in row and pd.notna(row['municipio_id']):
                        mun_id = int(row['municipio_id'])
                    else:
                        mun_id = 1
                    
                    team = Team.query.filter_by(
                        nombre=row['nombre'],
                        municipio_id=mun_id
                    ).first()
                    
                    if not team:
                        team = Team(
                            nombre=row['nombre'],
                            area=row.get('area') if pd.notna(row.get('area')) else None,
                            descripcion=row.get('descripcion') if pd.notna(row.get('descripcion')) else None,
                            municipio_id=mun_id
                        )
                        db.session.add(team)
                        count_teams += 1
                db.session.commit()
                print(f"   ✅ {count_teams} equipos agregados")
        except Exception as e:
            print(f"   ❌ Error al cargar equipos: {e}")
            db.session.rollback()
        
        # ============================
        # 5. CARGAR USUARIOS
        # ============================
        try:
            if 'users' in hojas:
                print("\n📥 Cargando usuarios...")
                df_users = pd.read_excel(archivo, sheet_name='users')
                count_users = 0
                for _, row in df_users.iterrows():
                    if pd.isna(row['username']) or pd.isna(row['nombre']):
                        continue
                    
                    # Obtener municipio_id
                    if municipio_id_default:
                        mun_id = municipio_id_default
                    elif 'municipio_id' in row and pd.notna(row['municipio_id']):
                        mun_id = int(row['municipio_id'])
                    else:
                        mun_id = 1
                    
                    # Manejar team_nombre
                    team_id = None
                    if pd.notna(row.get('team_nombre')):
                        team = Team.query.filter_by(
                            nombre=row['team_nombre'],
                            municipio_id=mun_id
                        ).first()
                        if team:
                            team_id = team.id
                    
                    # Manejar password_hash
                    password_hash = row.get('password_hash')
                    if pd.isna(password_hash) or password_hash == '':
                        password_hash = ''
                    
                    # Manejar telegram_id
                    telegram_id = row.get('telegram_id')
                    if pd.isna(telegram_id):
                        telegram_id = None
                    else:
                        try:
                            telegram_id = int(telegram_id)
                        except (ValueError, TypeError):
                            telegram_id = None
                    
                    # Campos opcionales
                    nivel = row.get('nivel') if pd.notna(row.get('nivel')) else None
                    rol_especifico = row.get('rol_especifico') if pd.notna(row.get('rol_especifico')) else None
                    area = row.get('area') if pd.notna(row.get('area')) else None
                    subarea = row.get('subarea') if pd.notna(row.get('subarea')) else None
                    role = row.get('role') if pd.notna(row.get('role')) else None
                    
                    # Verificar si existe
                    user = User.query.filter_by(username=row['username']).first()
                    if not user:
                        user = User(
                            nombre=row['nombre'],
                            username=row['username'],
                            password_hash=password_hash,
                            team_id=team_id,
                            telegram_id=telegram_id,
                            nivel=nivel,
                            rol_especifico=rol_especifico,
                            area=area,
                            subarea=subarea,
                            role=role,
                            puede_asignar=int(row.get('puede_asignar', 0)),
                            puede_validar=int(row.get('puede_validar', 0)),
                            puede_ver_todas_areas=int(row.get('puede_ver_todas_areas', 0)),
                            puede_configurar=int(row.get('puede_configurar', 0)),
                            is_active=int(row.get('is_active', 1)),
                            municipio_id=mun_id
                        )
                        db.session.add(user)
                        count_users += 1
                        print(f"   ✅ Usuario '{row['username']}' agregado (municipio {mun_id})")
                    else:
                        print(f"   ⚠️ Usuario '{row['username']}' ya existe, omitiendo")
                
                db.session.commit()
                print(f"   ✅ {count_users} usuarios agregados")
        except Exception as e:
            print(f"   ❌ Error al cargar usuarios: {e}")
            db.session.rollback()
        
        # ============================
        # RESUMEN FINAL
        # ============================
        print("\n" + "=" * 60)
        print("✅ CARGA COMPLETADA")
        print("=" * 60)
        print(f"\n📊 RESUMEN FINAL:")
        print(f"   • Localidades: {Localidad.query.count()}")
        print(f"   • Calles: {Calle.query.count()}")
        print(f"   • Estados: {Status.query.count()}")
        print(f"   • Equipos: {Team.query.count()}")
        print(f"   • Usuarios: {User.query.count()}")

if __name__ == "__main__":
    # Uso: python cargar_datos_municipio.py [archivo] [municipio_id]
    if len(sys.argv) > 2:
        archivo = sys.argv[1]
        try:
            mun_id = int(sys.argv[2])
            cargar_datos(archivo=archivo, municipio_id_default=mun_id)
        except ValueError:
            print("❌ municipio_id debe ser número entero")
    elif len(sys.argv) > 1:
        # Puede ser archivo o municipio_id
        try:
            mun_id = int(sys.argv[1])
            cargar_datos(municipio_id_default=mun_id)
        except ValueError:
            archivo = sys.argv[1]
            cargar_datos(archivo=archivo)
    else:
        cargar_datos()
