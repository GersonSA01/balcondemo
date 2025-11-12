# app/management/commands/check_privategpt.py
"""
Comando de Django para verificar el estado de PrivateGPT.
"""
from django.core.management.base import BaseCommand
from app.services.privategpt_client import get_privategpt_client


class Command(BaseCommand):
    help = "Verifica el estado y disponibilidad de PrivateGPT"

    def handle(self, *args, **options):
        client = get_privategpt_client()
        
        self.stdout.write("🔍 Verificando PrivateGPT...")
        self.stdout.write(f"📍 URL: {client.base_url}")
        self.stdout.write("")
        
        # Health check
        health = client.health_check()
        
        if health.get("status") == "ok" or health.get("available", False):
            self.stdout.write(
                self.style.SUCCESS("✅ PrivateGPT está disponible y funcionando")
            )
        else:
            self.stdout.write(
                self.style.ERROR("❌ PrivateGPT no está disponible")
            )
            if "error" in health:
                self.stdout.write(
                    self.style.ERROR(f"   Error: {health['error']}")
                )
            return
        
        # Listar documentos
        self.stdout.write("")
        self.stdout.write("📚 Documentos ingestionados:")
        try:
            docs_result = client.list_documents()
            if "data" in docs_result:
                docs = docs_result["data"]
                if docs:
                    self.stdout.write(
                        self.style.SUCCESS(f"   Total: {len(docs)} documentos")
                    )
                    for doc in docs[:5]:  # Mostrar solo los primeros 5
                        doc_name = doc.get("doc_metadata", {}).get("file_name", "N/A")
                        doc_id = doc.get("doc_id", "N/A")
                        self.stdout.write(f"   - {doc_name} (ID: {doc_id[:8]}...)")
                    if len(docs) > 5:
                        self.stdout.write(f"   ... y {len(docs) - 5} más")
                else:
                    self.stdout.write(
                        self.style.WARNING("   ⚠️ No hay documentos ingestionados")
                    )
                    self.stdout.write(
                        self.style.WARNING("   Ejecuta: python manage.py ingest_to_privategpt")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("   ⚠️ No se pudieron listar los documentos")
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Error al listar documentos: {str(e)}")
            )
        
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("✅ Verificación completada")
        )

