#!/usr/bin/env python3
"""
Carga datos desde un archivo Excel con múltiples hojas.
Maneja valores nulos en password_hash y otros campos.
Uso: python cargar_datos_municipio.py
"""
import pandas as pd
import numpy as np
from app import create_app
from app.extensions import db
from app.models.report import Localidad, Calle
from app.models.user import User
from app.models.team import Team
from app.models.status import Status

app = create_app()

def cargar_datos():
    archivo = "datos_municipio.xlsx"  # Cambia por el nombre de tu archivo
    
    with app.app_context():
        print("🚀 CARGANDO DATOS DESDE EXCEL...")
        print("=" * 60)
        
        # ============================
        # 1. CARGAR LOCALIDADES
        # ============================
        print("\n📥 Cargando localidades...")
        df_loc = pd.read_excel(archivo, sheet_name='localidades')
        count_loc = 0
        for _, row in df_loc.iterrows():
            if pd.isna(row['nombre']):
                continue
            loc = Localidad.query.filter_by(nombre=row['nombre']).first()
            if not loc:
                loc = Localidad(
                    nombre=row['nombre'],
                    latitud_central=row.get('latitud_central') if pd.notna(row.get('latitud_central')) else None,
                    longitud_central=row.get('longitud_central') if pd.notna(row.get('longitud_central')) else None
                )
                db.session.add(loc)
                count_loc += 1
        db.session.commit()
        print(f"   ✅ {count_loc} localidades agregadas")

        # ============================
        # 2. CARGAR CALLES
        # ============================
        print("\n📥 Cargando calles...")
        df_calles = pd.read_excel(archivo, sheet_name='calles')
        count_calles = 0
        for _, row in df_calles.iterrows():
            if pd.isna(row['nombre']) or pd.isna(row['localidad_nombre']):
                continue
            loc = Localidad.query.filter_by(nombre=row['localidad_nombre']).first()
            if not loc:
                print(f"   ⚠️ Localidad '{row['localidad_nombre']}' no encontrada para calle '{row['nombre']}'")
                continue
            calle = Calle.query.filter_by(nombre=row['nombre'], localidad_id=loc.id).first()
            if not calle:
                calle = Calle(nombre=row['nombre'], localidad_id=loc.id)
                db.session.add(calle)
                count_calles += 1
        db.session.commit()
        print(f"   ✅ {count_calles} calles agregadas")

        # ============================
        # 3. CARGAR ESTADOS (STATUS)
        # ============================
        print("\n📥 Cargando estados...")
        df_status = pd.read_excel(archivo, sheet_name='status')
        count_status = 0
        for _, row in df_status.iterrows():
            if pd.isna(row['descripcion']):
                continue
            st = Status.query.filter_by(descripcion=row['descripcion']).first()
            if not st:
                color = row.get('color') if pd.notna(row.get('color')) else '#cccccc'
                st = Status(descripcion=row['descripcion'], color=color)
                db.session.add(st)
                count_status += 1
        db.session.commit()
        print(f"   ✅ {count_status} estados agregados")

        # ============================
        # 4. CARGAR EQUIPOS (TEAMS)
        # ============================
        print("\n📥 Cargando equipos...")
        df_teams = pd.read_excel(archivo, sheet_name='teams')
        count_teams = 0
        for _, row in df_teams.iterrows():
            if pd.isna(row['nombre']):
                continue
            team = Team.query.filter_by(nombre=row['nombre']).first()
            if not team:
                team = Team(
                    nombre=row['nombre'],
                    area=row.get('area') if pd.notna(row.get('area')) else None,
                    descripcion=row.get('descripcion') if pd.notna(row.get('descripcion')) else None
                )
                db.session.add(team)
                count_teams += 1
        db.session.commit()
        print(f"   ✅ {count_teams} equipos agregados")

        # ============================
        # 5. CARGAR USUARIOS (CON MANEJO DE NULLS)
        # ============================
        print("\n📥 Cargando usuarios...")
        df_users = pd.read_excel(archivo, sheet_name='users')
        count_users = 0
        for _, row in df_users.iterrows():
            if pd.isna(row['username']) or pd.isna(row['nombre']):
                continue

            # --- Manejar team_nombre ---
            team_id = None
            if pd.notna(row.get('team_nombre')):
                team = Team.query.filter_by(nombre=row['team_nombre']).first()
                if team:
                    team_id = team.id
                else:
                    print(f"   ⚠️ Equipo '{row['team_nombre']}' no encontrado para usuario '{row['username']}'")

            # --- Manejar password_hash (¡CRÍTICO!) ---
            password_hash = row.get('password_hash')
            if pd.isna(password_hash) or password_hash == '':
                password_hash = ''  # Asigna cadena vacía para evitar error NOT NULL
                print(f"   ⚠️ Usuario '{row['username']}' sin password_hash, se asignó cadena vacía (debes actualizarlo)")

            # --- Manejar telegram_id ---
            telegram_id = row.get('telegram_id')
            if pd.isna(telegram_id):
                telegram_id = None
            else:
                try:
                    telegram_id = int(telegram_id)
                except (ValueError, TypeError):
                    telegram_id = None
                    print(f"   ⚠️ telegram_id inválido para '{row['username']}', se asignó None")

            # --- Manejar campos opcionales ---
            nivel = row.get('nivel') if pd.notna(row.get('nivel')) else None
            rol_especifico = row.get('rol_especifico') if pd.notna(row.get('rol_especifico')) else None
            area = row.get('area') if pd.notna(row.get('area')) else None
            subarea = row.get('subarea') if pd.notna(row.get('subarea')) else None
            role = row.get('role') if pd.notna(row.get('role')) else None

            # --- Verificar si el usuario ya existe ---
            user = User.query.filter_by(username=row['username']).first()
            if not user:
                user = User(
                    nombre=row['nombre'],
                    username=row['username'],
                    password_hash=password_hash,  # Ya aseguramos que no es NaN
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
                    is_active=int(row.get('is_active', 1))
                )
                db.session.add(user)
                count_users += 1
                print(f"   ✅ Usuario '{row['username']}' agregado")
            else:
                print(f"   ⚠️ Usuario '{row['username']}' ya existe, omitiendo")

        db.session.commit()
        print(f"   ✅ {count_users} usuarios agregados")

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
    cargar_datos()
