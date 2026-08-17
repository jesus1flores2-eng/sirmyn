"""
Servicio de Cloudinary exclusivo para Comunicación Social
Cuenta separada: no afecta evidencias de reportes
"""
import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.utils import cloudinary_url
from moviepy.video.fx import Resize
import os
import logging

logger = logging.getLogger(__name__)


def _get_config():
    """Obtiene configuración SIN sobrescribir la global"""
    from flask import current_app
    return {
        'cloud_name': current_app.config.get('CLOUDINARY_COMUNICACION_CLOUD_NAME'),
        'api_key': current_app.config.get('CLOUDINARY_COMUNICACION_API_KEY'),
        'api_secret': current_app.config.get('CLOUDINARY_COMUNICACION_API_SECRET'),
        'secure': True
    }


def subir_foto_comunicacion(filepath, public_id=None):
    """Sube una foto a la carpeta temporal de comunicación"""
    try:
        config = _get_config()
        result = cloudinary.uploader.upload(
            filepath,
            folder="comunicacion/temp",
            public_id=public_id,
            resource_type="image",
            **config  # Pasar credenciales directamente
        )
        return result['secure_url']
    except Exception as e:
        logger.error(f"❌ Error subiendo foto a Cloudinary Com: {e}")
        return None


def crear_video_slideshow(imagenes_urls, titulo="Comunicado Municipal", musica_path=None):
    """
    Crea un video slideshow de 1 segundo por foto con música opcional
    """
    try:
        import requests
        from moviepy import ImageSequenceClip, AudioFileClip
        import os
        import uuid
        
        config = _get_config()
        
        urls = imagenes_urls[:50]  # Máximo 50 imágenes
        temp_dir = "uploads/comunicacion/temp_slideshow"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Descargar imágenes
        image_paths = []
        for i, url in enumerate(urls):
            try:
                local_path = f"{temp_dir}/img_{i:03d}.jpg"
                response = requests.get(url, timeout=10)
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                image_paths.append(local_path)
            except Exception as e:
                logger.warning(f"No se pudo descargar {url}: {e}")
        
        if len(image_paths) < 2:
            return None
        
        # 1 segundo por foto
        duracion_por_foto = 1.0
        clip = ImageSequenceClip(image_paths, fps=1/duracion_por_foto)
        clip = clip.resized((1280, 720))
        
        # Agregar música si se proporciona
        if musica_path and os.path.exists(musica_path):
            try:
                audio = AudioFileClip(musica_path)
                if audio.duration > clip.duration:
                    audio = audio.subclipped(0, clip.duration)
                elif audio.duration < clip.duration:
                    audio = audio.looped(duration=clip.duration)
                clip = clip.with_audio(audio)
            except Exception as e:
                logger.warning(f"No se pudo agregar música: {e}")
        
        output_path = f"uploads/comunicacion/video_{uuid.uuid4().hex[:8]}.mp4"
        clip.write_videofile(output_path, fps=24, codec='libx264', audio=(musica_path is not None))
        clip.close()
        
        # Subir a Cloudinary
        result = cloudinary.uploader.upload(
            output_path,
            folder="comunicacion/videos",
            resource_type="video",
            public_id=f"video_{uuid.uuid4().hex[:8]}",
            **config
        )
        
        video_url = result['secure_url']
        
        # Limpiar archivos temporales
        for path in image_paths:
            try: os.remove(path)
            except: pass
        try: os.remove(output_path)
        except: pass
        if musica_path:
            try: os.remove(musica_path)
            except: pass
        try: os.rmdir(temp_dir)
        except: pass
        
        logger.info(f"✅ Video slideshow creado: {video_url[:80]}...")
        return video_url
        
    except Exception as e:
        logger.error(f"❌ Error creando video slideshow: {e}")
        return None


def borrar_fotos_temporales(imagenes_urls):
    """Borra las fotos temporales después de crear el video"""
    try:
        config = _get_config()
        for url in imagenes_urls:
            public_id = url.split('/')[-1].split('.')[0]
            cloudinary.uploader.destroy(
                f"comunicacion/temp/{public_id}",
                resource_type="image",
                **config
            )
        logger.info(f"✅ {len(imagenes_urls)} fotos temporales borradas")
        return True
    except Exception as e:
        logger.error(f"❌ Error borrando fotos: {e}")
        return False
