#!/usr/bin/env python3
"""
Carga calles y localidades desde Excel.
Uso: python cargar_calles.py [archivo_excel] [municipio_id]
"""
import sys
import pandas as pd
from app import create_app
from app.extensions import db
from app.models.report import Localidad, Calle

app = create_app()

def cargar_calles(archivo_excel="calles_localidades.xlsx", municipio_id=1):
    with app.app_context():
        print("📥 CARGANDO CALLES Y LOCALIDADES...")
        print(f"   🎯 Municipio ID: {municipio_id}")
        print(f"   📂 Archivo: {archivo_excel}")
        
        # Leer Excel
        try:
            df = pd.read_excel(archivo_excel)
        except FileNotFoundError:
            print(f"❌ Archivo no encontrado: {archivo_excel}")
            return
        
        # Limpiar y normalizar
        df['Localidad'] = df['Localidad'].str.strip().str.title()
        df['Calle'] = df['Calle'].str.strip().str.title()
        
        # Insertar localidades únicas
        localidades_unicas = df['Localidad'].unique()
        count_loc = 0
        
        for loc_nombre in localidades_unicas:
            loc = Localidad.query.filter_by(
                nombre=loc_nombre,
                municipio_id=municipio_id
            ).first()
            
            if not loc:
                loc = Localidad(
                    nombre=loc_nombre,
                    municipio_id=municipio_id
                )
                db.session.add(loc)
                count_loc += 1
        
        db.session.commit()
        print(f"✅ {count_loc} localidades insertadas")
        
        # Insertar calles
        count_calles = 0
        for index, row in df.iterrows():
            loc = Localidad.query.filter_by(
                nombre=row['Localidad'],
                municipio_id=municipio_id
            ).first()
            
            if loc:
                calle = Calle.query.filter_by(
                    nombre=row['Calle'],
                    localidad_id=loc.id,
                    municipio_id=municipio_id
                ).first()
                
                if not calle:
                    calle = Calle(
                        nombre=row['Calle'],
                        localidad_id=loc.id,
                        municipio_id=municipio_id
                    )
                    db.session.add(calle)
                    count_calles += 1
        
        db.session.commit()
        print(f"✅ {count_calles} calles insertadas")
        print("🎉 Carga completada")

if __name__ == "__main__":
    # Uso: python cargar_calles.py [archivo] [municipio_id]
    if len(sys.argv) > 2:
        archivo = sys.argv[1]
        try:
            mun_id = int(sys.argv[2])
            cargar_calles(archivo_excel=archivo, municipio_id=mun_id)
        except ValueError:
            print("❌ municipio_id debe ser número entero")
    elif len(sys.argv) > 1:
        try:
            mun_id = int(sys.argv[1])
            cargar_calles(municipio_id=mun_id)
        except ValueError:
            archivo = sys.argv[1]
            cargar_calles(archivo_excel=archivo)
    else:
        cargar_calles()
