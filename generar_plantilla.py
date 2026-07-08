# generar_plantilla.py
import pandas as pd
from datetime import datetime

def crear_plantilla():
    # Definir columnas para cada hoja
    hojas = {
        'localidades': ['id', 'nombre', 'latitud_central', 'longitud_central'],
        'calles': ['id', 'nombre', 'localidad_id', 'localidad_nombre'],
        'status': ['id', 'descripcion', 'color'],
        'teams': ['id', 'nombre', 'area', 'descripcion'],
        'users': [
            'id', 'nombre', 'username', 'password_hash', 'team_id', 'team_nombre',
            'telegram_id', 'nivel', 'rol_especifico', 'area', 'subarea', 'role',
            'puede_asignar', 'puede_validar', 'puede_ver_todas_areas',
            'puede_configurar', 'created_at', 'is_active'
        ]
    }

    nombre_archivo = f"plantilla_municipio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
        for sheet, columns in hojas.items():
            df = pd.DataFrame(columns=columns)
            df.to_excel(writer, sheet_name=sheet, index=False)

    print(f"✅ Plantilla creada: {nombre_archivo}")
    print("   Abre el archivo y llena los datos respetando los encabezados.")

if __name__ == "__main__":
    crear_plantilla()
