#!/usr/bin/env python
"""
Script para eliminar archivos temporales (que empiezan con 'tmp') de PrivateGPT.
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from app.services.privategpt_client import get_privategpt_client


def eliminar_archivos_tmp():
    """Elimina todos los documentos que tienen file_name empezando con 'tmp'."""
    client = get_privategpt_client()
    
    # Obtener lista de documentos ingestionados
    print("📋 Obteniendo lista de documentos ingestionados...")
    response = client.list_documents()
    
    if not response or "data" not in response:
        print("⚠️ No se pudo obtener la lista de documentos")
        return
    
    documents = response.get("data", [])
    print(f"📊 Total de documentos encontrados: {len(documents)}")
    
    # Filtrar documentos que empiezan con "tmp"
    tmp_docs = []
    for doc in documents:
        file_name = doc.get("doc_metadata", {}).get("file_name", "")
        if file_name.lower().startswith("tmp"):
            tmp_docs.append(doc)
    
    if not tmp_docs:
        print("✅ No se encontraron archivos temporales para eliminar")
        return
    
    print(f"🗑️  Encontrados {len(tmp_docs)} archivos temporales:")
    for doc in tmp_docs:
        file_name = doc.get("doc_metadata", {}).get("file_name", "Unknown")
        doc_id = doc.get("doc_id", "Unknown")
        print(f"   - {file_name} (ID: {doc_id})")
    
    # Confirmar eliminación
    print(f"\n⚠️  ¿Eliminar estos {len(tmp_docs)} archivos? (s/n): ", end="")
    confirmacion = input().strip().lower()
    
    if confirmacion != "s":
        print("❌ Operación cancelada")
        return
    
    # Eliminar documentos
    eliminados = 0
    errores = 0
    
    for doc in tmp_docs:
        doc_id = doc.get("doc_id")
        file_name = doc.get("doc_metadata", {}).get("file_name", "Unknown")
        
        try:
            result = client.delete_document(doc_id)
            if result.get("success", False):
                print(f"✅ Eliminado: {file_name}")
                eliminados += 1
            else:
                print(f"❌ Error al eliminar {file_name}: {result.get('error', 'Unknown')}")
                errores += 1
        except Exception as e:
            print(f"❌ Error al eliminar {file_name}: {str(e)}")
            errores += 1
    
    print(f"\n📊 Resumen:")
    print(f"   ✅ Eliminados: {eliminados}")
    print(f"   ❌ Errores: {errores}")
    print(f"   📋 Total procesados: {len(tmp_docs)}")


if __name__ == "__main__":
    eliminar_archivos_tmp()

