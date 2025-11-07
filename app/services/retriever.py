# app/services/retriever.py
import os
import hashlib
import json
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

# Compatibilidad de imports
try:
    from langchain_community.retrievers import MultiQueryRetriever, EnsembleRetriever
except ImportError:
    try:
        from langchain.retrievers.multi_query import MultiQueryRetriever
        from langchain.retrievers import EnsembleRetriever
    except ImportError:
        MultiQueryRetriever = None
        EnsembleRetriever = None

try:
    from langchain_community.cross_encoders import HuggingFaceCrossEncoder
except Exception:
    try:
        from langchain_community.cross_encoders.huggingface import HuggingFaceCrossEncoder
    except Exception:
        HuggingFaceCrossEncoder = None

try:
    from langchain_community.retrievers.document_compressors import CrossEncoderReranker
    from langchain_community.retrievers import ContextualCompressionRetriever
except ImportError:
    try:
        from langchain.retrievers.document_compressors import CrossEncoderReranker
        from langchain.retrievers import ContextualCompressionRetriever
    except ImportError:
        CrossEncoderReranker = None
        ContextualCompressionRetriever = None

from .config import llm, DATA_DIR


def _get_pdf_paths(files_hint: list[str] = None, folders_hint: list[str] = None) -> list[Path]:
    """
    Obtiene rutas a PDFs, opcionalmente filtrados por files o folders.
    
    Args:
        files_hint: Lista de file paths específicos (ej: ["app/data/LOES.pdf", ...])
        folders_hint: Lista de carpetas (ej: ["unemi/estudiantes", "legal_nacional/codigos"])
    
    Returns:
        Lista de Path objects
    """
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"No se encontró el directorio app/data en: {DATA_DIR}")
    
    # Escanear TODOS los PDFs recursivamente
    all_pdf_paths = []
    for pdf_path in DATA_DIR.rglob("*.pdf"):
        if pdf_path.is_file():
            all_pdf_paths.append(pdf_path)
    
    if not all_pdf_paths:
        raise FileNotFoundError(f"No se encontraron PDFs en app/data: {DATA_DIR}")
    
    # Aplicar filtros si se especifican
    filtered_paths = set()
    
    # Filtro por files específicos
    if files_hint:
        for file_hint in files_hint:
            # Normalizar path
            if file_hint.startswith("app/data/"):
                file_hint = file_hint[len("app/data/"):]
            
            target_path = DATA_DIR / file_hint
            if target_path.exists() and target_path in all_pdf_paths:
                filtered_paths.add(target_path)
            else:
                # Buscar por nombre de archivo
                for pdf_path in all_pdf_paths:
                    if pdf_path.name == Path(file_hint).name:
                        filtered_paths.add(pdf_path)
    
    # Filtro por carpetas
    if folders_hint:
        for folder_hint in folders_hint:
            folder_path = DATA_DIR / folder_hint
            if folder_path.exists() and folder_path.is_dir():
                for pdf_path in folder_path.rglob("*.pdf"):
                    if pdf_path.is_file():
                        filtered_paths.add(pdf_path)
    
    # Si no hay filtros o no se encontraron matches, usar todos
    if files_hint or folders_hint:
        if filtered_paths:
            result = sorted(filtered_paths)
        else:
            # Fallback: usar PDFs en raíz si no hay matches en subcarpetas
            result = sorted([p for p in DATA_DIR.glob("*.pdf") if p.is_file()])
    else:
        result = sorted(all_pdf_paths)
    
    if not result:
        print(f"⚠️ Filtros no produjeron resultados. Usando todos los PDFs.")
        result = sorted(all_pdf_paths)
    
    print(f"📁 _get_pdf_paths: {len(result)} PDFs seleccionados (de {len(all_pdf_paths)} totales)")
    return result


def _limpiar_indices_viejos(data_dir: Path, index_key_actual: str):
    """Elimina índices viejos que no correspondan a los PDFs actuales."""
    import shutil
    
    for item in data_dir.iterdir():
        # Limpiar directorios de índices viejos
        if item.is_dir() and item.name.startswith("combined_index_"):
            # Si no es el índice actual, eliminarlo
            if item.name != f"combined_index_{index_key_actual}":
                try:
                    print(f"🗑️ Eliminando índice viejo: {item.name}")
                    shutil.rmtree(item)
                except Exception as e:
                    print(f"⚠️ No se pudo eliminar {item.name}: {e}")
        
        # Limpiar archivos de metadata viejos
        if item.is_file() and item.name.startswith(".index_metadata_"):
            if item.name != f".index_metadata_{index_key_actual}.json":
                try:
                    item.unlink()
                    print(f"🗑️ Eliminando metadata vieja: {item.name}")
                except Exception as e:
                    print(f"⚠️ No se pudo eliminar {item.name}: {e}")


def _cargar_docs_y_index(pdf_paths: list[Path]):
    """Carga múltiples PDFs, trocea y crea índice FAISS combinado.
    
    Si el índice no existe o no corresponde a los PDFs actuales, lo reconstruye automáticamente.
    """
    pdf_names = sorted([p.name for p in pdf_paths])
    
    # Usar hash MD5 para nombres de índice cortos (evitar límite de 260 caracteres en Windows)
    pdf_list_str = json.dumps(pdf_names, sort_keys=True)
    hash_obj = hashlib.md5(pdf_list_str.encode('utf-8'))
    index_key = hash_obj.hexdigest()[:16]  # Usar solo los primeros 16 caracteres del hash
    
    data_dir = pdf_paths[0].parent if pdf_paths else DATA_DIR
    ruta_indice = data_dir / f"combined_index_{index_key}"
    
    # Guardar metadata del índice para saber qué PDFs contiene
    metadata_file = ruta_indice.parent / f".index_metadata_{index_key}.json"
    
    # Limpiar índices viejos
    _limpiar_indices_viejos(data_dir, index_key)
    
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    # Verificar si necesitamos reconstruir el índice
    index_existe = os.path.exists(ruta_indice) and os.path.isdir(ruta_indice)
    
    if not index_existe:
        print(f"📚 Construyendo índice para {len(pdf_paths)} PDFs...")
        print(f"   Archivos: {', '.join([p.name for p in pdf_paths])}")
    
    # Chunks más grandes para capturar artículos completos
    splitter = CharacterTextSplitter(chunk_size=1500, chunk_overlap=300, separator="\n")
    all_docs = []
    pdf_map = {}
    
    for pdf_path in pdf_paths:
        pdf_path_str = str(pdf_path)
        pdf_name = pdf_path.name
        
        # Calcular ruta relativa desde DATA_DIR para enlaces correctos
        try:
            pdf_relative = pdf_path.relative_to(DATA_DIR).as_posix()
        except ValueError:
            # Si el PDF no está en DATA_DIR, usar solo el nombre
            pdf_relative = pdf_name
        
        loader = PyPDFLoader(file_path=pdf_path_str)
        documents = loader.load()
        docs = splitter.split_documents(documents=documents)
        
        for doc in docs:
            if not hasattr(doc, 'metadata'):
                doc.metadata = {}
            doc.metadata['source_pdf'] = pdf_relative  # Guardar path relativo completo
        
        start_idx = len(all_docs)
        all_docs.extend(docs)
        end_idx = len(all_docs)
        
        pdf_map[pdf_name] = (start_idx, end_idx)

    if index_existe:
        try:
            vectorstore = FAISS.load_local(str(ruta_indice), embeddings, allow_dangerous_deserialization=True)
            print(f"✅ Índice cargado desde caché ({len(all_docs)} documentos)")
        except Exception as e:
            print(f"⚠️ Error al cargar índice, reconstruyendo: {e}")
            vectorstore = FAISS.from_documents(all_docs, embeddings)
            vectorstore.save_local(str(ruta_indice))
            # Guardar metadata
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump({'pdfs': pdf_names, 'num_docs': len(all_docs)}, f, indent=2)
            print(f"✅ Índice reconstruido y guardado ({len(all_docs)} documentos)")
    else:
        vectorstore = FAISS.from_documents(all_docs, embeddings)
        vectorstore.save_local(str(ruta_indice))
        # Guardar metadata
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump({'pdfs': pdf_names, 'num_docs': len(all_docs)}, f, indent=2)
        print(f"✅ Índice creado y guardado ({len(all_docs)} documentos)")
        print(f"   📁 PDFs incluidos: {', '.join(pdf_names)}")
    
    return vectorstore, all_docs, pdf_map


def _build_retriever(pdf_paths: list[Path], _model_id: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """Dense (MMR) + Sparse (BM25) + MultiQuery + Cross-Encoder Reranker."""
    vectorstore, docs, pdf_map = _cargar_docs_y_index(pdf_paths)
    
    print(f"🔧 Building retriever para {len(pdf_paths)} PDFs")

    # Dense retriever - OPTIMIZADO para velocidad y precisión
    dense = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 8, "fetch_k": 40, "lambda_mult": 0.7}  # Menos docs, más relevantes
    )

    # Sparse retriever
    bm25 = BM25Retriever.from_documents(docs)
    bm25.k = 8  # Reducido para mayor precisión

    # MultiQuery + Ensemble si están disponibles
    if MultiQueryRetriever is not None and EnsembleRetriever is not None:
        mq_dense = MultiQueryRetriever.from_llm(
            retriever=dense,
            llm=llm,
            prompt=ChatPromptTemplate.from_template(
                "Genera 2 reformulaciones específicas para buscar en el reglamento:\n{question}\n"
                "Enfócate en procedimientos y términos clave del SGA/UNEMI."
            )
        )
        ensemble = EnsembleRetriever(retrievers=[mq_dense, bm25], weights=[0.6, 0.4])
    else:
        ensemble = dense

    # Cross-encoder reranker
    if (HuggingFaceCrossEncoder is not None and 
        CrossEncoderReranker is not None and 
        ContextualCompressionRetriever is not None):
        try:
            cross_encoder = HuggingFaceCrossEncoder(model_name=_model_id)
            reranker = None
            try:
                reranker = CrossEncoderReranker(model=cross_encoder, top_n=12)
            except (TypeError, ValidationError):
                try:
                    reranker = CrossEncoderReranker(encoder=cross_encoder, top_n=12)
                except Exception:
                    reranker = None

            if reranker is not None:
                try:
                    compressed = ContextualCompressionRetriever(
                        base_retriever=ensemble,
                        base_compressor=reranker
                    )
                    return compressed
                except Exception:
                    pass
        except Exception:
            pass
    return ensemble


# Cache global del retriever
_retriever_cache = {}  # key: pdf_paths_key -> retriever


def get_retriever(files_hint: list[str] = None, folders_hint: list[str] = None):
    """
    Obtiene el retriever (con caché), opcionalmente filtrado por files o folders.
    
    Args:
        files_hint: Lista de file paths específicos
        folders_hint: Lista de carpetas
    
    Returns:
        Retriever configurado
    """
    global _retriever_cache
    
    # Obtener PDFs con filtros
    pdf_paths = _get_pdf_paths(files_hint, folders_hint)
    
    # Crear key para caché
    pdf_paths_key = "_".join(sorted([p.name for p in pdf_paths]))
    
    # Buscar en caché
    if pdf_paths_key not in _retriever_cache:
        print(f"🆕 Construyendo nuevo retriever para {len(pdf_paths)} PDFs")
        _retriever_cache[pdf_paths_key] = _build_retriever(pdf_paths)
    else:
        print(f"♻️ Usando retriever en caché para {len(pdf_paths)} PDFs")
    
    return _retriever_cache[pdf_paths_key]

