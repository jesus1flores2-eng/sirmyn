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

def subir_archivo(file_path, folder="reportes"):
    """
    Sube un archivo a Cloudinary y retorna la URL pública.
    
    Args:
        file_path (str): Ruta local del archivo.
        folder (str): Carpeta en Cloudinary (ej: 'reportes', 'cuadrilla', 'materiales').
    
    Returns:
        str: URL pública del archivo, o None si falla.
    """
    try:
        init_cloudinary()
        result = cloudinary.uploader.upload(
            file_path,
            folder=f"sirmyn/{folder}",
            resource_type="auto"  # Detecta si es imagen o video
        )
        return result['secure_url']
    except Exception as e:
        print(f"❌ Error subiendo a Cloudinary: {e}")
        return None
