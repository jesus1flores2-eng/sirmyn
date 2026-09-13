import cloudinary
import cloudinary.uploader
import os

def init_cloudinary():
    """Inicializa Cloudinary con las credenciales de las variables de entorno"""
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET')
    )

def subir_archivo(file_path, folder="reportes", public_id=None):
    """
    Sube un archivo a Cloudinary y retorna la URL pública.
    
    Args:
        file_path (str): Ruta local del archivo.
        folder (str): Carpeta en Cloudinary (ej: 'reportes', 'cuadrilla', 'materiales').
        public_id (str, optional): Nombre personalizado del archivo en Cloudinary.
    
    Returns:
        str: URL pública del archivo, o None si falla.
    """
    try:
        init_cloudinary()
        upload_options = {
            "folder": f"sirmyn/{folder}",
            "resource_type": "auto"
        }
        if public_id:
            upload_options["public_id"] = public_id
        
        result = cloudinary.uploader.upload(file_path, **upload_options)
        return result['secure_url']
    except Exception as e:
        print(f"❌ Error subiendo a Cloudinary: {e}")
        return None


def obtener_carpeta_evidencia(municipio_nombre, tipo_reporte, subcarpeta='reportes'):
    """
    Genera la ruta organizada para Cloudinary/local:
    municipio_ixtlahuacan/agua_potable/reportes
    municipio_ixtlahuacan/agua_potable/reparacion/evidencia_cuadrilla
    municipio_ixtlahuacan/agua_potable/reparacion/materiales_utilizados
    
    Args:
        municipio_nombre: Nombre del municipio (ej: 'Ixtlahuacán')
        tipo_reporte: Tipo de reporte (ej: 'Agua potable', 'Alumbrado público')
        subcarpeta: 'reportes', 'reparacion/evidencia_cuadrilla', 'reparacion/materiales_utilizados'
    
    Returns:
        str: Ruta formateada (ej: 'municipio_ixtlahuacan/agua_potable/reportes')
    """
    # Normalizar nombre del municipio
    municipio_limpio = municipio_nombre.lower().replace(' ', '_').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    municipio_folder = f"municipio_{municipio_limpio}"
    
    # Mapeo de tipos a carpetas
    mapeo_departamentos = {
        'Agua potable': 'agua_potable',
        'Drenaje': 'agua_potable',
        'Aseo público': 'aseo_publico',
        'Alumbrado público': 'alumbrado_publico',
        'Parques y jardines': 'parques_jardines',
        'Ecología': 'ecologia',
        'Seguridad pública': 'seguridad_publica',
        'Obras públicas': 'obras_publicas',
        'Bomberos': 'bomberos',
        'Protección Civil': 'proteccion_civil',
        'Punto Violeta': 'punto_violeta',
        'Ambulancia': 'ambulancia'
    }
    
    departamento_folder = mapeo_departamentos.get(tipo_reporte, 'general')
    
    return f"{municipio_folder}/{departamento_folder}/{subcarpeta}"


def generar_nombre_archivo(folio, extension, sufijo=None):
    """
    Genera el nombre del archivo basado en el folio.
    
    Args:
        folio: Folio del reporte (ej: 'AGUA-1')
        extension: Extensión del archivo (ej: 'jpg')
        sufijo: Sufijo opcional (ej: '1', '2' para múltiples fotos)
    
    Returns:
        str: Nombre del archivo (ej: 'AGUA-1.jpg' o 'AGUA-1-1.jpg')
    """
    folio_limpio = folio.replace('-', '_')
    if sufijo:
        return f"{folio_limpio}-{sufijo}.{extension}"
    return f"{folio_limpio}.{extension}"
