# app/management/commands/ingest_to_privategpt.py
"""
Comando de Django para ingestionar documentos PDF en PrivateGPT.
"""
from django.core.management.base import BaseCommand
from pathlib import Path
from app.services.privategpt_client import get_privategpt_client
from app.services.config import DATA_DIR
import os


class Command(BaseCommand):
    help = "Ingestiona documentos PDF desde app/data/ a PrivateGPT"

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            help='Ruta específica a un archivo o carpeta para ingestionar (relativa a app/data/)',
            default=None
        )
        parser.add_argument(
            '--recursive',
            action='store_true',
            help='Ingestionar recursivamente todas las carpetas',
            default=False
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Solo verificar que PrivateGPT esté disponible, sin ingestionar',
            default=False
        )

    def handle(self, *args, **options):
        client = get_privategpt_client()
        
        # Verificar que PrivateGPT esté disponible
        self.stdout.write("🔍 Verificando conexión con PrivateGPT...")
        if not client.is_available():
            self.stdout.write(
                self.style.ERROR(
                    "❌ PrivateGPT no está disponible. "
                    "Asegúrate de que esté ejecutándose en: " + client.base_url
                )
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ PrivateGPT está disponible en {client.base_url}")
        )
        
        if options['check_only']:
            return
        
        # Determinar qué archivos ingestionar
        if options['path']:
            # Ruta específica
            target_path = DATA_DIR / options['path']
            if target_path.is_file() and target_path.suffix.lower() == '.pdf':
                files_to_ingest = [target_path]
            elif target_path.is_dir():
                files_to_ingest = list(target_path.rglob('*.pdf'))
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ Ruta no encontrada: {target_path}")
                )
                return
        else:
            # Ingestionar todos los PDFs en app/data/
            if options['recursive']:
                files_to_ingest = list(DATA_DIR.rglob('*.pdf'))
            else:
                # Solo PDFs en el nivel raíz de cada subcarpeta
                files_to_ingest = []
                for subdir in DATA_DIR.iterdir():
                    if subdir.is_dir():
                        files_to_ingest.extend(subdir.glob('*.pdf'))
        
        if not files_to_ingest:
            self.stdout.write(
                self.style.WARNING("⚠️ No se encontraron archivos PDF para ingestionar")
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f"📄 Encontrados {len(files_to_ingest)} archivos PDF")
        )
        
        # Ingestionar cada archivo
        success_count = 0
        error_count = 0
        
        for pdf_path in files_to_ingest:
            try:
                # Obtener ruta relativa para mostrar
                rel_path = pdf_path.relative_to(DATA_DIR)
                self.stdout.write(f"📤 Ingestionando: {rel_path}...", ending=' ')
                
                result = client.ingest_file(str(pdf_path))
                
                if result.get("success", False) or "data" in result:
                    self.stdout.write(self.style.SUCCESS("✅"))
                    success_count += 1
                else:
                    error_msg = result.get("error", "Error desconocido")
                    self.stdout.write(
                        self.style.ERROR(f"❌ {error_msg}")
                    )
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Error: {str(e)}")
                )
                error_count += 1
        
        # Resumen
        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"✅ Ingestionados exitosamente: {success_count}")
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f"❌ Errores: {error_count}")
            )
        self.stdout.write("=" * 50)
        
        # Listar documentos ingestionados
        self.stdout.write("")
        self.stdout.write("📋 Listando documentos en PrivateGPT...")
        try:
            docs_result = client.list_documents()
            if "data" in docs_result:
                docs = docs_result["data"]
                self.stdout.write(f"📚 Total de documentos en PrivateGPT: {len(docs)}")
                for doc in docs[:10]:  # Mostrar solo los primeros 10
                    doc_name = doc.get("doc_metadata", {}).get("file_name", "N/A")
                    self.stdout.write(f"   - {doc_name}")
                if len(docs) > 10:
                    self.stdout.write(f"   ... y {len(docs) - 10} más")
            else:
                self.stdout.write(
                    self.style.WARNING("⚠️ No se pudieron listar los documentos")
                )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Error al listar documentos: {str(e)}")
            )

