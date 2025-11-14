from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'
    
    def ready(self):
        """Se ejecuta cuando Django está listo."""
        # Limpiar archivos temporales al inicio de la aplicación
        try:
            from app.services.privategpt_client import get_privategpt_client
            client = get_privategpt_client()
            # Usar cleanup_all_tmp_files para limpieza más agresiva al inicio
            result = client.cleanup_all_tmp_files()
            if result.get("success"):
                eliminados = result.get("eliminados", 0)
                if eliminados > 0:
                    logger.info(f"✅ Limpieza automática: {eliminados} archivos temporales eliminados al inicio")
                else:
                    logger.info("✅ No se encontraron archivos temporales al inicio")
            else:
                logger.warning(f"⚠️ Error en limpieza automática: {result.get('error', 'Unknown')}")
        except Exception as e:
            # No fallar si PrivateGPT no está disponible al inicio
            logger.warning(f"⚠️ No se pudo limpiar archivos temporales al inicio: {str(e)}")
