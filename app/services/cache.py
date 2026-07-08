import threading
import time

class SmartCache:
    def __init__(self, default_ttl=300):
        self._cache = {}
        self._timestamps = {}
        self._ttl = default_ttl
        self._lock = threading.RLock()
        
    def get(self, key):
        with self._lock:
            if key in self._cache:
                timestamp = self._timestamps.get(key, 0)
                if time.time() - timestamp < self._ttl:
                    return self._cache[key]
                else:
                    self._cache.pop(key, None)
                    self._timestamps.pop(key, None)
            return None
    
    def set(self, key, value):
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    def clear(self, key=None):
        with self._lock:
            if key:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
            else:
                self._cache.clear()
                self._timestamps.clear()
