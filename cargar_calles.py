import pandas as pd
from app import create_app
from app.extensions import db
from app.models.report import Localidad, Calle

# Inicializa Flask
app = create_app()
with app.app_context():
    # Ruta del Excel (dentro del proyecto)
    archivo_excel = "calles_localidades.xlsx"  # o ruta absoluta
    
    # Lee el Excel
    try:
        df = pd.read_excel(archivo_excel)
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {archivo_excel}")
        print("   Asegúrate de que el archivo esté en la carpeta del proyecto.")
        exit(1)
    
    # Limpia espacios y normaliza
    df['Localidad'] = df['Localidad'].str.strip().str.title()
    df['Calle'] = df['Calle'].str.strip().str.title()
    
    # Insertar localidades únicas
    localidades_unicas = df['Localidad'].unique()
    for loc_nombre in localidades_unicas:
        loc = Localidad.query.filter_by(nombre=loc_nombre).first()
        if not loc:
            loc = Localidad(nombre=loc_nombre)
            db.session.add(loc)
    db.session.commit()
    print(f"✅ {len(localidades_unicas)} localidades insertadas")
    
    # Insertar calles
    count = 0
    for index, row in df.iterrows():
        loc = Localidad.query.filter_by(nombre=row['Localidad']).first()
        if loc:
            calle = Calle.query.filter_by(nombre=row['Calle'], localidad_id=loc.id).first()
            if not calle:
                calle = Calle(nombre=row['Calle'], localidad_id=loc.id)
                db.session.add(calle)
                count += 1
    db.session.commit()
    print(f"✅ {count} calles insertadas")
    print("🎉 Carga completada")
