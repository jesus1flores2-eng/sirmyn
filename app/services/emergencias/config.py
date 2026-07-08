"""
Configuración específica para el bot de emergencias SIRMYN
"""
import os
from dotenv import load_dotenv

load_dotenv()


class EmergenciasConfig:
    """
    Configuración del sistema de emergencias SIRMYN
    """
    
    # ===== TOKENS DE TELEGRAM =====
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_EMERGENCIAS_TOKEN", "")
    
    # ===== CONFIGURACIÓN MUNICIPIO =====
    MUNICIPIO_ID = int(os.getenv("MUNICIPIO_ID", "1"))
    MUNICIPIO_NOMBRE = os.getenv("MUNICIPIO_NOMBRE", "Municipio SIRMYN")
    
    # ===== IDs DE DESTINATARIOS DE EMERGENCIA =====
    # Estos pueden variar por municipio
    TELEGRAM_COMISARIO_ID = os.getenv("TELEGRAM_COMISARIO_ID", "")
    TELEGRAM_BOMBEROS_ID = os.getenv("TELEGRAM_BOMBEROS_ID", "")
    TELEGRAM_AMBULANCIAS_ID = os.getenv("TELEGRAM_AMBULANCIAS_ID", "")
    TELEGRAM_VIOLETA_ID = os.getenv("TELEGRAM_VIOLETA_ID", "")  # Unidad especial
    
    # ===== GRUPOS DE TELEGRAM (opcionales) =====
    GRUPO_PATRULLAS = os.getenv("TELEGRAM_GRUPO_PATRULLAS", "")
    GRUPO_BOMBEROS = os.getenv("TELEGRAM_GRUPO_BOMBEROS", "")
    GRUPO_AMBULANCIAS = os.getenv("TELEGRAM_GRUPO_AMBULANCIAS", "")
    GRUPO_COMANDANCIA = os.getenv("TELEGRAM_GRUPO_COMANDANCIA", "")
    
    # ===== CONFIGURACIÓN DE RESPUESTA =====
    TIEMPO_RESPUESTA_ESTIMADO = {
        "policia": 5,      # minutos
        "bomberos": 8,
        "ambulancia": 7,
        "violeta": 4       # Prioridad alta
    }
    
    RADIO_PATRULLAS_CERCANAS = 5  # km
    
    # ===== CONFIGURACIÓN DE MENSAJES =====
    MENSAJE_INICIAL = (
        "🚨 *SISTEMA DE EMERGENCIAS SIRMYN*\n\n"
        "Sistema Integral de Reportes Municipales y Notificaciones\n\n"
        "⚠️ *SOLO PARA EMERGENCIAS REALES*\n"
        "El uso indebido es sancionado por la ley.\n\n"
        "¿Qué tipo de emergencia está reportando?"
    )
    
    # ===== TIPOS DE EMERGENCIA CONFIGURABLES =====
    TIPOS_EMERGENCIA = {
        "policia": {
            "nombre": "👮 POLICÍA / SEGURIDAD PÚBLICA",
            "subtipo": {
                "accidente_vial": "Accidente de tránsito",
                "robo": "Robo en curso",
                "violencia": "Agresión o violencia",
                "persona_sospechosa": "Persona sospechosa",
                "disturbios": "Disturbios públicos",
                "vandalismo": "Vandalismo o daño",
                "otro": "Otro (especificar)"
            }
        },
        "bomberos": {
            "nombre": "🔥 BOMBEROS",
            "subtipo": {
                "incendio_edificio": "Incendio en edificio",
                "incendio_vehiculo": "Incendio vehicular", 
                "incendio_vegetacion": "Incendio forestal/pasto",
                "fuga_gas": "Fuga de gas",
                "residuo_peligroso": "Material peligroso",
                "rescate": "Persona atrapada",
                "otro": "Otro (especificar)"
            }
        },
        "ambulancia": {
            "nombre": "🚑 AMBULANCIA / PROTECCIÓN CIVIL",
            "subtipo": {
                "accidente_heridos": "Accidente con heridos",
                "infarto": "Problema cardiaco",
                "desmayo": "Persona inconsciente",
                "caida": "Caída o trauma",
                "parto": "Parto en curso",
                "intoxicacion": "Intoxicación o sobredosis",
                "otro": "Otro (especificar)"
            }
        },
        "violeta": {
            "nombre": "👮‍♀️ PUNTO VIOLETA",
            "subtipo": {
                "acoso": "Acoso o seguimiento",
                "violencia_domestica": "Violencia doméstica",
                "intento_secuestro": "Intento de secuestro",
                "persona_desaparecida": "Persona desaparecida",
                "violencia_genero": "Violencia de género",
                "otro": "Otro (especificar)"
            }
        }
    }
    
    # ===== CONFIGURACIÓN DE MAPAS =====
    MAPS_PROVIDER = "google"  # google, osm
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
    
    @property
    def esta_configurado(self):
        """Verifica si el bot está mínimamente configurado"""
        return bool(self.TELEGRAM_TOKEN.strip())
    
    @property
    def destinatarios_activos(self):
        """Lista de destinatarios configurados"""
        activos = []
        if self.TELEGRAM_COMISARIO_ID:
            activos.append(("comisario", self.TELEGRAM_COMISARIO_ID))
        if self.TELEGRAM_BOMBEROS_ID:
            activos.append(("bomberos", self.TELEGRAM_BOMBEROS_ID))
        if self.TELEGRAM_AMBULANCIAS_ID:
            activos.append(("ambulancias", self.TELEGRAM_AMBULANCIAS_ID))
        if self.TELEGRAM_VIOLETA_ID:
            activos.append(("violeta", self.TELEGRAM_VIOLETA_ID))
        return activos