# app/services/emergencias/emergencias_bot.py
"""
Servicio principal del bot de emergencias SIRMYN - VERSIÓN CORREGIDA
"""
import logging
import asyncio
from threading import Thread
from telegram.ext import Application

from .config import EmergenciasConfig
from .handlers.inicio import start_emergencia

logger = logging.getLogger(__name__)


class EmergenciasBotService:
    """
    Servicio del bot de emergencias integrado con Flask
    Versión corregida para asyncio en threads
    """
    
    def __init__(self):
        self.config = EmergenciasConfig()
        self.application = None
        self.flask_app = None
        self._polling_thread = None
        self._running = False
        
    def init_app(self, flask_app):
        """
        Inicializa el bot con la aplicación Flask existente
        """
        self.flask_app = flask_app
        
        # Verificar configuración
        if not self.config.TELEGRAM_TOKEN:
            logger.warning("⚠️ TELEGRAM_EMERGENCIAS_TOKEN no configurado en .env")
            return False
            
        try:
            # Crear aplicación de Telegram
            self.application = Application.builder() \
                .token(self.config.TELEGRAM_TOKEN) \
                .build()
                
            # Configurar handlers
            self._setup_handlers()
            
            logger.info("✅ Servicio de emergencias SIRMYN inicializado")
            logger.info(f"   Municipio: {self.config.MUNICIPIO_NOMBRE}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error inicializando bot de emergencias: {e}")
            return False
    
    def _setup_handlers(self):
        """Configura todos los handlers del bot de emergencias"""
        try:
            # Handler principal de conversación
            setup_emergencia_handlers(self.application)
            
            # Handlers de comandos directos
            from telegram.ext import CommandHandler
            
            async def ayuda_command(update, context):
                await update.message.reply_text(
                    "🚨 *COMANDOS DE EMERGENCIA SIRMYN*\n\n"
                    "/start - Iniciar reporte de emergencia\n"
                    "/cancelar - Cancelar operación actual\n"
                    "/ayuda - Mostrar esta ayuda",
                    parse_mode="Markdown"
                )
            
            self.application.add_handler(CommandHandler("ayuda", ayuda_command))
            self.application.add_handler(CommandHandler("help", ayuda_command))
            
            logger.info("✅ Handlers de emergencias configurados")
            
        except Exception as e:
            logger.error(f"❌ Error configurando handlers: {e}")
    
    def run(self):
        """
        Ejecuta el bot en un hilo separado - VERSIÓN CORREGIDA
        """
        if not self.application:
            logger.warning("⚠️ Bot de emergencias no inicializado, no se ejecutará")
            return
            
        if self._running:
            logger.warning("⚠️ Bot de emergencias ya está ejecutándose")
            return
        
        try:
            self._running = True
            self._polling_thread = Thread(
                target=self._run_polling_safe,
                daemon=True,
                name="EmergenciasBotThread"
            )
            self._polling_thread.start()
            logger.info("🚨 Bot de emergencias SIRMYN iniciado en segundo plano")
            
        except Exception as e:
            logger.error(f"❌ Error iniciando hilo de emergencias: {e}")
            self._running = False
    
    def _run_polling_safe(self):
        """
        Ejecuta polling de forma segura en thread separado
        VERSIÓN CORREGIDA
        """
        try:
            import asyncio
            import sys
        
            # Configurar asyncio para este thread
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                logger.info("🚨 Bot Emergencias: WindowsSelectorEventLoopPolicy")
    
            # Crear event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    
            # Ejecutar dentro del contexto de Flask
            with self.flask_app.app_context():
                logger.info("⏳ Iniciando bot de emergencias...")
        
                # Ejecutar async_polling directamente
                loop.run_until_complete(self._async_polling_simple())
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot de emergencias detenido por usuario")
        except Exception as e:
            logger.error(f"❌ Error en polling de emergencias: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._running = False
            logger.info("🔴 Bot de emergencias detenido")

    async def _async_polling_simple(self):
        """
        VERSIÓN CORREGIDA - Polling manual con offset correcto
        """
        try:
            logger.info("🔄 Iniciando bot de emergencias...")
        
            # Inicializar la aplicación
            await self.application.initialize()
            await self.application.start()
        
            # Obtener el bot
            bot = self.application.bot
        
            # Eliminar webhook y obtener último update ID
            await bot.delete_webhook(drop_pending_updates=True)
        
            # Obtener el último update procesado
            last_update_id = 0
        
            # Obtener updates pendientes para limpiar
            try:
                updates = await bot.get_updates(offset=last_update_id, timeout=1)
                if updates:
                    last_update_id = updates[-1].update_id + 1
            except:
                pass
            
            logger.info("✅ Bot listo - Escuchando mensajes...")
        
            # Mantener el bot corriendo
            while self._running:
                try:
                    # Obtener NUEVOS updates
                    updates = await bot.get_updates(
                        offset=last_update_id,
                        timeout=30,
                        allowed_updates=None,
                        limit=100
                    )
                
                    # Procesar cada update
                    for update in updates:
                        try:
                            # Actualizar el último ID
                            last_update_id = update.update_id + 1
                        
                            # Procesar el update
                            await self.application.process_update(update)
                        
                            # Pequeña pausa entre updates
                            await asyncio.sleep(0.1)
                        
                        except Exception as e:
                            logger.error(f"⚠️ Error procesando update: {e}")
                            continue
                
                    # Pequeña pausa entre ciclos
                    await asyncio.sleep(1.0)
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"⚠️ Error en ciclo polling: {e}")
                    await asyncio.sleep(2.0)
        
        except Exception as e:
            logger.error(f"❌ Error en bot de emergencias: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Limpiar
            try:
                await self.application.stop()
                await self.application.shutdown()
            except:
                pass
            logger.info("🔴 Bot de emergencias finalizado")  
 
    def stop(self):
        """Detiene el bot de emergencias"""
        if self.application and self._running:
            try:
                # Intentar detener de forma segura
                self._running = False
                
                if hasattr(self.application, 'updater'):
                    self.application.updater.stop()
                
                logger.info("🛑 Bot de emergencias detenido")
            except Exception as e:
                logger.error(f"❌ Error deteniendo bot: {e}")
    
    def get_bot_info(self):
        """Obtiene información del bot"""
        if not self.application:
            return {"estado": "no_inicializado"}
        
        return {
            "estado": "activo" if self._running else "inactivo",
            "municipio": self.config.MUNICIPIO_NOMBRE,
            "hilo_activo": self._polling_thread.is_alive() if self._polling_thread else False,
            "ejecutandose": self._running
        }


# Instancia global única del bot de emergencias
emergencias_bot = EmergenciasBotService()
