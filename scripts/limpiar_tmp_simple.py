#!/usr/bin/env python
"""
Script simple para eliminar archivos temporales de PrivateGPT.
No requiere Django, solo requests.
"""
import requests
import os

# Configuración
PRIVATEGPT_URL = os.getenv("PRIVATEGPT_API_URL", "http://localhost:8001")
PRIVATEGPT_URL = PRIVATEGPT_URL.rstrip("/")


def limpiar_archivos_tmp():
    """Elimina todos los documentos que tienen file_name empezando con 'tmp'."""
    print(f"🔗 Conectando a PrivateGPT en: {PRIVATEGPT_URL}")
    
    # Obtener lista de documentos
    print("📋 Obteniendo lista de documentos...")
    try:
        response = requests.get(
            f"{PRIVATEGPT_URL}/v1/ingest/list",
            timeout=30,
            headers={"Connection": "close"}
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"❌ Error al obtener lista de documentos: {str(e)}")
        return
    
    if "data" not in data:
        print("⚠️ No se encontró 'data' en la respuesta")
        return
    
    documents = data.get("data", [])
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
    
    print(f"\n🗑️  Encontrados {len(tmp_docs)} archivos temporales:")
    for doc in tmp_docs:
        file_name = doc.get("doc_metadata", {}).get("file_name", "Unknown")
        doc_id = doc.get("doc_id", "Unknown")
        print(f"   - {file_name} (ID: {doc_id[:8]}...)")
    
    # Confirmar eliminación
    print(f"\n⚠️  ¿Eliminar estos {len(tmp_docs)} archivos? (s/n): ", end="")
    confirmacion = input().strip().lower()
    
    if confirmacion != "s":
        print("❌ Operación cancelada")
        return
    
    # Eliminar documentos
    eliminados = 0
    errores = 0
    
    print("\n🗑️  Eliminando archivos...")
    for doc in tmp_docs:
        doc_id = doc.get("doc_id")
        file_name = doc.get("doc_metadata", {}).get("file_name", "Unknown")
        
        try:
            response = requests.delete(
                f"{PRIVATEGPT_URL}/v1/ingest/{doc_id}",
                timeout=30,
                headers={"Connection": "close"}
            )
            response.raise_for_status()
            print(f"   ✅ Eliminado: {file_name}")
            eliminados += 1
        except Exception as e:
            print(f"   ❌ Error al eliminar {file_name}: {str(e)}")
            errores += 1
    
    print(f"\n📊 Resumen:")
    print(f"   ✅ Eliminados: {eliminados}")
    print(f"   ❌ Errores: {errores}")
    print(f"   📋 Total procesados: {len(tmp_docs)}")


if __name__ == "__main__":
    limpiar_archivos_tmp()

