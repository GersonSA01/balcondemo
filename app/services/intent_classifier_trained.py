"""
Servicio de clasificación híbrida usando modelo entrenado.
Combina clasificación de intención (categoría/subcategoría/departamento) 
con búsqueda de FAQ en knowledge base.
"""
import os
import joblib
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Any, List
from sklearn.metrics.pairwise import cosine_similarity

# Importación condicional para evitar recargas innecesarias si se usa gunicorn/uvicorn workers
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    EMBEDDINGS_AVAILABLE = False
    print("⚠️ [BrainService] sentence-transformers no disponible. El modelo híbrido requiere esta librería.")

# Singleton global para mantener el modelo en memoria RAM
_BRAIN_ENGINE = None

class BrainEngine:
    """
    Motor híbrido que combina:
    - Clasificación de intención (categoría, subcategoría, departamento)
    - Búsqueda semántica en FAQ/Knowledge Base
    """
    def __init__(self):
        print("🧠 [BrainService] Iniciando carga del cerebro digital híbrido...")
        
        # Ruta al modelo híbrido
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.models_dir = self.base_dir / "models"
        self.model_path = self.models_dir / "brain_hybrid.pkl"

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"❌ No se encontró el modelo híbrido en {self.model_path}\n"
                f"   Asegúrate de que el archivo brain_hybrid.pkl existe en la carpeta models/"
            )
        
        if not EMBEDDINGS_AVAILABLE:
            raise ImportError(
                "❌ sentence-transformers no está instalado.\n"
                "   Instala con: pip install sentence-transformers"
            )
            
        # Cargar el archivo pesado (Embeddings + Clasificadores + FAQ)
        print(f"   📦 Cargando modelo desde: {self.model_path}")
        self.brain = joblib.load(self.model_path)
        
        # Desempaquetar componentes
        self.classifiers = self.brain.get("classifiers", {})
        self.encoders = self.brain.get("encoders", {})
        self.kb = self.brain.get("knowledge_base", {})
        
        # Validar que todos los componentes estén presentes
        if not self.classifiers:
            raise ValueError("❌ El modelo no contiene clasificadores")
        if not self.encoders:
            raise ValueError("❌ El modelo no contiene encoders")
        
        # Validar knowledge base (manejar arrays numpy correctamente)
        kb_vectors = self.kb.get("vectors")
        if not self.kb or kb_vectors is None:
            print("⚠️ [BrainService] Knowledge base vacía o sin vectores. FAQ deshabilitado.")
            self.kb = {"vectors": np.array([]), "questions": [], "answers": []}
        else:
            # Verificar si el array está vacío usando len() en lugar de evaluación booleana directa
            try:
                if isinstance(kb_vectors, np.ndarray):
                    if kb_vectors.size == 0 or len(kb_vectors) == 0:
                        print("⚠️ [BrainService] Knowledge base tiene array vacío. FAQ deshabilitado.")
                        self.kb = {"vectors": np.array([]), "questions": [], "answers": []}
                elif len(kb_vectors) == 0:
                    print("⚠️ [BrainService] Knowledge base tiene lista vacía. FAQ deshabilitado.")
                    self.kb = {"vectors": np.array([]), "questions": [], "answers": []}
            except (TypeError, AttributeError):
                # Si no es array ni lista, asumir que está vacío
                print("⚠️ [BrainService] Knowledge base con formato inesperado. FAQ deshabilitado.")
                self.kb = {"vectors": np.array([]), "questions": [], "answers": []}
        
        # Cargar SentenceTransformer para embeddings
        model_name = self.brain.get("embed_model_name", "paraphrase-multilingual-MiniLM-L12-v2")
        print(f"   🔤 Cargando modelo de embeddings: {model_name}")
        self.embedder = SentenceTransformer(model_name)
        
        # Estadísticas del modelo
        num_faq = len(self.kb.get("questions", []))
        print(f"✅ [BrainService] Cerebro cargado y listo.")
        print(f"   📊 Clasificadores: {len(self.classifiers)}")
        print(f"   📚 FAQ en knowledge base: {num_faq} preguntas/respuestas")

    def _get_embedding(self, text: str) -> np.ndarray:
        """Genera embedding vectorial del texto (uso interno)."""
        if not text or not text.strip():
            return np.array([])
        return self.embedder.encode([text], normalize_embeddings=True, show_progress_bar=False)
    
    def encode_text(self, text: str, normalize: bool = True) -> np.ndarray:
        """
        Método público para generar embeddings de texto.
        Permite que otros servicios (como related_request_matcher) usen el mismo modelo.
        
        Args:
            text: Texto a vectorizar
            normalize: Si True, normaliza los embeddings (default: True)
        
        Returns:
            Array numpy con el embedding del texto
        """
        if not text or not text.strip():
            return np.array([])
        return self.embedder.encode([text], normalize_embeddings=normalize, show_progress_bar=False)
    
    def encode_batch(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """
        Método público para generar embeddings de múltiples textos en batch.
        Más eficiente que llamar encode_text múltiples veces.
        
        Args:
            texts: Lista de textos a vectorizar
            normalize: Si True, normaliza los embeddings (default: True)
        
        Returns:
            Array numpy con los embeddings (shape: [len(texts), embedding_dim])
        """
        if not texts:
            return np.array([])
        # Filtrar textos vacíos
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return np.array([])
        return self.embedder.encode(valid_texts, normalize_embeddings=normalize, show_progress_bar=False)

    def predict(self, user_text: str, threshold: float = 0.65) -> Dict[str, Any]:
        """
        Analiza el texto y devuelve intención Y posible FAQ match.
        
        Args:
            user_text: Texto del usuario a analizar
            threshold: Umbral de confianza para clasificación (default: 0.65)
        
        Returns:
            Dict con:
            - category, subcategory, department: Clasificación de intención
            - confidence: Confianza principal de categoría (0.0 a 1.0)
            - cat_conf, sub_conf, dep_conf: Confianzas individuales por nivel
            - is_confident: True si categoría supera el threshold
            - faq_match: Dict con answer, similarity, original_question si hay match
        """
        if not user_text or not user_text.strip():
            return {
                "category": "OTROS",
                "subcategory": "OTROS",
                "department": "OTROS",
                "confidence": 0.0,
                "is_confident": False,
                "faq_match": None
            }

        # 1. Vectorizar el texto del usuario
        vector = self._get_embedding(user_text)
        if vector.size == 0:
            return {
                "category": "OTROS",
                "subcategory": "OTROS",
                "department": "OTROS",
                "confidence": 0.0,
                "is_confident": False,
                "faq_match": None
            }
        
        # ------------------------------------------
        # A. CLASIFICACIÓN (INTENCIÓN)
        # ------------------------------------------
        result = {
            "category": "OTROS",
            "subcategory": "OTROS",
            "department": "OTROS",
            "confidence": 0.0,
            "is_confident": False,
            "faq_match": None
        }
        
        try:
            # 1) CLASIFICACIÓN DE CATEGORÍA
            cat_conf = 0.0
            if "cat" in self.classifiers and "cat" in self.encoders:
                probs_cat = self.classifiers["cat"].predict_proba(vector)[0]
                max_prob_cat = float(np.max(probs_cat))
                idx_cat = int(np.argmax(probs_cat))
                
                cat_conf = round(max_prob_cat, 2)
                result["confidence"] = cat_conf  # Confianza principal (categoría)
                
                # Decodificar etiqueta de categoría SIEMPRE (incluso si no supera threshold)
                cat_name = self.encoders["cat"].inverse_transform([idx_cat])[0]
                
                print(f"\n{'='*80}")
                print(f"🔍 [BrainService] CLASIFICACIÓN DE CATEGORÍA")
                print(f"{'='*80}")
                print(f"   Texto de entrada: '{user_text[:100]}...'")
                print(f"   Threshold requerido: {threshold}")
                print(f"   Confianza obtenida: {cat_conf:.3f}")
                print(f"   Índice predicho: {idx_cat}")
                print(f"   Categoría predicha: '{cat_name}'")
                print(f"   Supera threshold?: {max_prob_cat >= threshold}")
                # Mostrar qué valor se asignará (puede ser cat_name aunque no supere threshold si no es "OTROS")
                valor_asignado = cat_name if (max_prob_cat >= threshold or (cat_name and cat_name != "OTROS")) else "OTROS"
                print(f"   Valor que se asignará a result['category']: '{valor_asignado}'")
                
                if max_prob_cat >= threshold:
                    result["category"] = cat_name
                    result["is_confident"] = True
                    result["cat_conf"] = cat_conf
                else:
                    # Aunque no supere threshold, usar la categoría predicha si NO es "OTROS"
                    # Esto permite usar clasificaciones parciales válidas
                    if cat_name and cat_name != "OTROS":
                        result["category"] = cat_name
                        print(f"   ⚠️ No supera threshold, pero categoría '{cat_name}' es válida (no 'OTROS'), asignándola igual")
                    else:
                        print(f"   ⚠️ No supera threshold y categoría es 'OTROS', usando 'OTROS' por defecto")
                    result["cat_conf"] = cat_conf  # Guardar confianza aunque no supere threshold
            else:
                print(f"   ⚠️ [BrainService] Modelo de categoría no disponible")
            
            # 2) CLASIFICACIÓN DE SUBCATEGORÍA (solo si existe modelo entrenado)
            sub_conf = 0.0
            if "sub" in self.classifiers and "sub" in self.encoders:
                try:
                    probs_sub = self.classifiers["sub"].predict_proba(vector)[0]
                    idx_sub = int(np.argmax(probs_sub))
                    sub_conf = round(float(np.max(probs_sub)), 2)
                    
                    # Decodificar usando encoder
                    sub_name = self.encoders["sub"].inverse_transform([idx_sub])[0]
                    
                    print(f"\n🔍 [BrainService] CLASIFICACIÓN DE SUBCATEGORÍA")
                    print(f"   Confianza obtenida: {sub_conf:.3f}")
                    print(f"   Índice predicho: {idx_sub}")
                    print(f"   Subcategoría predicha: '{sub_name}'")
                    print(f"   Valor asignado a result['subcategory']: '{sub_name}'")
                    
                    result["subcategory"] = sub_name
                    result["sub_conf"] = sub_conf
                except Exception as e:
                    print(f"⚠️ [BrainService] Error en subcategoría: {e}")
            else:
                print(f"   ⚠️ [BrainService] Modelo de subcategoría no disponible")
            
            # 3) CLASIFICACIÓN DE DEPARTAMENTO (solo si existe modelo entrenado)
            dep_conf = 0.0
            if "dep" in self.classifiers and "dep" in self.encoders:
                try:
                    probs_dep = self.classifiers["dep"].predict_proba(vector)[0]
                    idx_dep = int(np.argmax(probs_dep))
                    dep_conf = round(float(np.max(probs_dep)), 2)
                    
                    # Decodificar usando encoder
                    dep_name = self.encoders["dep"].inverse_transform([idx_dep])[0]
                    
                    print(f"\n🔍 [BrainService] CLASIFICACIÓN DE DEPARTAMENTO")
                    print(f"   Confianza obtenida: {dep_conf:.3f}")
                    print(f"   Índice predicho: {idx_dep}")
                    print(f"   Departamento predicho: '{dep_name}'")
                    print(f"   Valor asignado a result['department']: '{dep_name}'")
                    
                    result["department"] = dep_name
                    result["dep_conf"] = dep_conf
                except Exception as e:
                    print(f"⚠️ [BrainService] Error en departamento: {e}")
            else:
                print(f"   ⚠️ [BrainService] Modelo de departamento no disponible")
            
            print(f"\n✅ [BrainService] RESULTADO FINAL DE CLASIFICACIÓN:")
            print(f"   category: '{result.get('category', 'OTROS')}'")
            print(f"   subcategory: '{result.get('subcategory', 'OTROS')}'")
            print(f"   department: '{result.get('department', 'OTROS')}'")
            print(f"   confidence: {result.get('confidence', 0.0)}")
            print(f"   is_confident: {result.get('is_confident', False)}")
            print(f"{'='*80}\n")
                    
        except Exception as e:
            print(f"⚠️ [BrainService] Error en clasificación: {e}")
            import traceback
            traceback.print_exc()

        # ------------------------------------------
        # B. BUSCADOR DE FAQ (MEMORIA)
        # ------------------------------------------
        kb_vectors = self.kb.get("vectors")
        # Validar que hay vectores disponibles (manejar arrays numpy correctamente)
        has_vectors = False
        if kb_vectors is not None:
            try:
                if isinstance(kb_vectors, np.ndarray):
                    has_vectors = kb_vectors.size > 0 and len(kb_vectors) > 0
                else:
                    has_vectors = len(kb_vectors) > 0
            except (TypeError, AttributeError):
                has_vectors = False
        
        if has_vectors:
            try:
                # Calcular similitud de coseno contra la base de conocimiento
                similarities = cosine_similarity(vector, kb_vectors)[0]
                best_match_idx = np.argmax(similarities)
                best_score = float(similarities[best_match_idx])
                
                # UMBRAL FAQ: Debe ser muy alto para responder automáticamente
                FAQ_THRESHOLD = 0.82
                if best_score > FAQ_THRESHOLD:
                    result["faq_match"] = {
                        "answer": self.kb["answers"][best_match_idx],
                        "similarity": round(best_score, 3),
                        "original_question": self.kb["questions"][best_match_idx]
                    }
                    print(f"💡 [BrainService] FAQ Match encontrado (similitud: {best_score:.3f})")
            except Exception as e:
                print(f"⚠️ [BrainService] Error en búsqueda FAQ: {e}")
            
        return result

def get_brain_engine() -> Optional[BrainEngine]:
    """
    Patrón Singleton para no recargar el modelo en cada petición.
    
    Returns:
        BrainEngine instance o None si hay error en la carga
    """
    global _BRAIN_ENGINE
    if _BRAIN_ENGINE is None:
        try:
            _BRAIN_ENGINE = BrainEngine()
        except Exception as e:
            print(f"❌ [BrainService] Error crítico al cargar el modelo: {e}")
            print(f"   El sistema continuará sin el modelo híbrido (modo fallback)")
            _BRAIN_ENGINE = None
    return _BRAIN_ENGINE

def classify_user_intent_hybrid(text: str, threshold: float = 0.65) -> Dict[str, Any]:
    """
    Función helper para ser consumida por el orquestador.
    Maneja errores para no romper el chat si el modelo falla.
    
    Args:
        text: Texto del usuario a clasificar
        threshold: Umbral de confianza (default: 0.65)
    
    Returns:
        Dict con clasificación y posible FAQ match, o fallback seguro si hay error
    """
    if not text or not text.strip():
        return {
            "category": "OTROS", 
            "subcategory": "OTROS", 
            "department": "OTROS", 
            "confidence": 0.0,
            "is_confident": False,
            "faq_match": None
        }
    
    try:
        engine = get_brain_engine()
        if engine is None:
            # Modelo no disponible, retornar fallback
            return {
                "category": "OTROS", 
                "subcategory": "OTROS", 
                "department": "OTROS", 
                "confidence": 0.0,
                "is_confident": False,
                "faq_match": None
            }
        
        result = engine.predict(text, threshold=threshold)
        
        # Log de resultados si hay clasificación confiable
        if result.get("is_confident"):
            print(f"📊 [BrainService] Clasificación: {result.get('category')} / {result.get('subcategory')} (conf: {result.get('confidence'):.2f})")
        
        return result
        
    except Exception as e:
        print(f"⚠️ [BrainService] Error en predicción: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        # Fallback seguro
        return {
            "category": "OTROS", 
            "subcategory": "OTROS", 
            "department": "OTROS", 
            "confidence": 0.0,
            "is_confident": False,
            "faq_match": None
        }