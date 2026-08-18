"""
Servicio de respaldo automático de base de datos
Exporta tablas a CSV y las sube al bucket privado de Supabase Storage
"""
import os
import io
import csv
import logging
from datetime import datetime
from flask import current_app
from sqlalchemy import text

logger = logging.getLogger(__name__)


class RespaldoService:
    """Servicio para crear y subir respaldos de la base de datos"""

    TABLAS = [
        'reports',
        'asignaciones',
        'users',
        'teams',
        'status',
        'localidades',
        'calles',
        'encuestas_satisfaccion',
        'rechazos_usuario',
        'gps_dispositivos',
        'emergencies',
        'emergency_notifications'
    ]

    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SECRET_KEY')

    def ejecutar_respaldo(self):
        """Ejecuta el respaldo completo"""
        try:
            logger.info("🔄 Iniciando respaldo de base de datos...")

            from app.extensions import db

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            carpeta_zip = f"respaldo_{timestamp}"
            archivos_subidos = []

            for tabla in self.TABLAS:
                try:
                    csv_data = self._exportar_tabla_csv(tabla, db)
                    if csv_data:
                        ruta_remota = f"{carpeta_zip}/{tabla}.csv"
                        url = self._subir_archivo(
                            bucket='respaldos',
                            ruta_remota=ruta_remota,
                            contenido=csv_data,
                            content_type='text/csv'
                        )
                        if url:
                            archivos_subidos.append(tabla)
                            logger.info(f"✅ {tabla}.csv subido")
                        else:
                            logger.warning(f"⚠️ No se pudo subir {tabla}.csv")
                except Exception as e:
                    logger.error(f"❌ Error con tabla {tabla}: {e}")

            logger.info(f"📦 Respaldo completado: {len(archivos_subidos)} archivos")
            return len(archivos_subidos) > 0

        except Exception as e:
            logger.error(f"❌ Error general en respaldo: {e}", exc_info=True)
            return False

    def _exportar_tabla_csv(self, tabla, db):
        """Exporta una tabla completa a CSV"""
        try:
            resultado = db.session.execute(text(f"SELECT * FROM {tabla}"))
            filas = resultado.fetchall()
            columnas = list(resultado.keys())

            if not columnas:
                logger.warning(f"⚠️ Tabla {tabla} sin columnas")
                return None

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columnas)

            for fila in filas:
                writer.writerow([self._formatear_valor(v) for v in fila])

            return output.getvalue()

        except Exception as e:
            logger.error(f"❌ Error exportando {tabla}: {e}")
            return None

    def _formatear_valor(self, valor):
        """Formatea valores para CSV"""
        if valor is None:
            return ''
        if isinstance(valor, (datetime,)):
            return valor.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(valor, (dict, list)):
            import json
            return json.dumps(valor, ensure_ascii=False)
        return str(valor)

    def _subir_archivo(self, bucket, ruta_remota, contenido, content_type):
        """Sube un archivo al bucket de Supabase Storage"""
        try:
            import requests

            if not self.supabase_url or not self.supabase_key:
                logger.error("❌ Faltan SUPABASE_URL o SUPABASE_SECRET_KEY")
                return None

            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{ruta_remota}"

            headers = {
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": content_type,
                "x-upsert": "true"
            }

            response = requests.post(url, headers=headers, data=contenido.encode('utf-8'))

            if response.status_code in [200, 201]:
                return f"{bucket}/{ruta_remota}"
            else:
                logger.error(f"❌ Error subiendo {ruta_remota}: {response.status_code} - {response.text[:200]}")
                return None

        except Exception as e:
            logger.error(f"❌ Error subiendo archivo: {e}")
            return None


def crear_respaldo_automatico():
    """Función para ejecutar desde el scheduler"""
    try:
        servicio = RespaldoService()
        resultado = servicio.ejecutar_respaldo()
        if resultado:
            logger.info("✅ Respaldo automático completado exitosamente")
        else:
            logger.warning("⚠️ Respaldo automático no se completó")
        return resultado
    except Exception as e:
        logger.error(f"❌ Error en respaldo automático: {e}")
        return False
