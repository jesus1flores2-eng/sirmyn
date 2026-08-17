import requests
import hashlib
import time
import logging
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)

class TrackSolidService:
    """Servicio para interactuar con la API de TrackSolid Pro"""
    
    def __init__(self):
        self.app_key = current_app.config.get('TRACKSOLID_APP_KEY')
        self.app_secret = current_app.config.get('TRACKSOLID_APP_SECRET')
        self.base_url = "https://hk-open.tracksolidpro.com/route/rest"
        self.access_token = None
        self.token_expiry = None
    
    def _get_sign(self, params):
        """Genera firma MD5 para la API"""
        sorted_keys = sorted(params.keys())
        param_str = ''.join(f"{k}{params[k]}" for k in sorted_keys if k != 'sign')
        sign_str = f"{self.app_secret}{param_str}{self.app_secret}"
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest().upper()
    
    def obtener_token(self):
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
    
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        params = {
            'method': 'jimi.oauth.token.get',
            'app_key': self.app_key,
            'timestamp': timestamp,
            'sign_method': 'md5',
            'v': '1.0',
            'format': 'json',
            'user_pwd_md5': current_app.config.get('TRACKSOLID_USER_PWD_MD5')  # ⭐ NUEVO
        }
        params['sign'] = self._get_sign(params)
        
        try:
            response = requests.post(self.base_url, data=params, timeout=10)
            data = response.json()
            
            if data.get('code') == 0:
                result = data.get('result', {})
                self.access_token = result.get('access_token')
                expires_in = result.get('expires_in', 7200)
                self.token_expiry = datetime.now().timestamp() + expires_in
                logger.info("✅ Token TrackSolid obtenido")
                return self.access_token
            else:
                logger.error(f"❌ Error token TrackSolid: {data.get('message')}")
                return None
        except Exception as e:
            logger.error(f"❌ Error conexión TrackSolid: {e}")
            return None
    
    def obtener_ubicaciones(self):
        """Obtiene la ubicación de todos los dispositivos"""
        token = self.obtener_token()
        if not token:
            return None
        
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        params = {
            'method': 'jimi.user.device.location.list',
            'access_token': token,
            'app_key': self.app_key,
            'timestamp': timestamp,
            'sign_method': 'md5',
            'v': '1.0',
            'format': 'json'
        }
        params['sign'] = self._get_sign(params)
        
        try:
            response = requests.post(self.base_url, data=params, timeout=10)
            data = response.json()
            
            if data.get('code') == 0:
                dispositivos = data.get('result', [])
                logger.info(f"✅ TrackSolid: {len(dispositivos)} dispositivos obtenidos")
                
                ubicaciones = []
                for d in dispositivos:
                    ubicaciones.append({
                        'imei': d.get('imei'),
                        'latitud': float(d.get('lat', 0)),
                        'longitud': float(d.get('lng', 0)),
                        'velocidad': float(d.get('speed', 0)),
                        'fecha': d.get('deviceTime') or d.get('gpsTime')
                    })
                return ubicaciones
            else:
                logger.error(f"❌ Error ubicaciones: {data.get('message')}")
                return []
        except Exception as e:
            logger.error(f"❌ Error TrackSolid ubicaciones: {e}")
            return []
