# app/services/related_request_matcher.py
"""
Servicio para encontrar solicitudes relacionadas usando embeddings + LLM.
Sistema optimizado: embeddings semánticos pre-filtran candidatos antes del LLM.
"""
from typing import Dict, List, Any, Optional
import json
import re
import unicodedata
from pathlib import Path
from datetime import datetime
from functools import lru_cache
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("⚠️ [WARNING] sentence-transformers no disponible. El sistema usará modo fallback sin embeddings.")

# Ya no se importa llm ni guarded_invoke porque eliminamos el LLM del matching

# Constantes para el sistema de embeddings
MAX_SOLICITUDES_RECIENTES = 150    # Tope duro por estudiante para considerar
MAX_SOLICITUDES_CANDIDATAS = 30    # Máximo de candidatas a seleccionar (top-K después de ranking semántico)

@lru_cache(maxsize=1)
def get_solicitudes_embedding_model() -> Optional['SentenceTransformer']:
    """
    Singleton del modelo de embeddings para solicitudes.
    Modelo ligero, multilingüe, ideal para español.
    """
    if not EMBEDDINGS_AVAILABLE:
        return None
    try:
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except Exception as e:
        print(f"⚠️ [WARNING] Error al cargar modelo de embeddings: {e}")
        return None


def _normalize_text(text: str) -> str:
    """
    Normaliza texto para embeddings preservando la semántica.
    Similar a cómo PrivateGPT procesa texto: normaliza pero mantiene significado.
    """
    if not text:
        return ""
    
    # Convertir a minúsculas pero preservar estructura
    text = text.lower()
    
    # Normalizar unicode pero mantener caracteres especiales importantes
    text = unicodedata.normalize("NFKD", text)
    
    # Eliminar diacríticos (acentos) para mejorar matching semántico
    # pero mantener las palabras intactas
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    
    # Limpiar caracteres especiales pero mantener espacios y números
    # Permitir más caracteres para preservar semántica (guiones, etc.)
    text = re.sub(r"[^a-z0-9áéíóúñü\s\-]", " ", text)
    
    # Normalizar espacios múltiples pero mantener estructura
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


def _parse_fecha(fecha_str: Optional[str]) -> datetime:
    """
    Parsea fecha desde string a datetime object.
    """
    if not fecha_str:
        return datetime.min
    try:
        return datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(fecha_str[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return datetime.min


def build_text_for_embedding(solicitud: Dict[str, Any]) -> str:
    """
    Construye un texto rico semánticamente para representar la solicitud en el embedding.
    Similar a cómo PrivateGPT construye textos para embeddings: captura el significado completo
    sin depender de keywords específicas.
    """
    # Priorizar descripción completa (contiene toda la semántica)
    descripcion = solicitud.get("descripcion", "") or ""
    
    # Agregar información del servicio desde diferentes fuentes
    servicio_nombre = ""
    if solicitud.get("servicio"):
        if isinstance(solicitud["servicio"], dict):
            servicio_nombre = solicitud["servicio"].get("nombre", "")
            # También incluir descripción del proceso si está disponible
            proceso = solicitud["servicio"].get("proceso", {})
            if isinstance(proceso, dict):
                proceso_desc = proceso.get("descripcion", "")
                if proceso_desc:
                    servicio_nombre = f"{servicio_nombre} {proceso_desc}".strip()
        else:
            servicio_nombre = str(solicitud["servicio"])
    
    # Agregar información del historial si está disponible (todos los historiales relevantes)
    historial_info = []
    if solicitud.get("historial") and len(solicitud["historial"]) > 0:
        # Tomar los primeros 2 historiales para contexto
        for hist in solicitud["historial"][:2]:
            if isinstance(hist, dict):
                servicio_hist = hist.get("servicio_nombre") or hist.get("servicio", "")
                observacion = hist.get("observacion", "")
                if servicio_hist:
                    historial_info.append(servicio_hist)
                if observacion:
                    historial_info.append(observacion)
    
    # Construir texto rico semánticamente (similar a cómo PrivateGPT construye chunks)
    # El orden importa: más semántico primero
    parts = [
        descripcion,  # Más importante - contiene toda la semántica de la solicitud
        " ".join(historial_info) if historial_info else "",  # Contexto histórico
        servicio_nombre,  # Contexto del servicio
        solicitud.get("tipo_display", "") or solicitud.get("tipo", "") or "",  # Tipo de solicitud
    ]
    
    # Unir y normalizar (el modelo de embeddings capturará la semántica)
    texto_completo = " ".join(filter(None, parts))
    texto_normalizado = _normalize_text(texto_completo)
    
    return texto_normalizado


def select_candidate_requests_with_embeddings(
    solicitudes: List[Dict[str, Any]],
    user_request: str,
    max_recent: int = MAX_SOLICITUDES_RECIENTES,
    max_candidates: int = MAX_SOLICITUDES_CANDIDATAS,
) -> List[Dict[str, Any]]:
    """
    Selecciona las solicitudes candidatas usando embeddings + similitud coseno.
    Sistema industrial: ranking semántico antes de enviar al LLM.
    
    Args:
        solicitudes: Lista de todas las solicitudes del estudiante
        user_request: Texto de la solicitud actual del usuario
        max_recent: Máximo de solicitudes recientes a considerar
        max_candidates: Máximo de candidatas a retornar (top-K)
    
    Returns:
        Lista de solicitudes candidatas ordenadas por similitud semántica
    """
    if not solicitudes:
        return []

    print(f"⚙️ [EMBED] Ordenando solicitudes por fecha para tomar las más recientes...")
    solicitudes_sorted = sorted(
        solicitudes,
        key=lambda s: _parse_fecha(s.get("fecha_creacion")),
        reverse=True,
    )
    recientes = solicitudes_sorted[:max_recent]
    print(f"⚙️ [EMBED] Tomando {len(recientes)} solicitudes recientes (de {len(solicitudes)} totales)")

    # Verificar si embeddings están disponibles
    model = get_solicitudes_embedding_model()
    if not model:
        print("⚠️ [EMBED] Modelo de embeddings no disponible, usando solo recencia")
        return recientes[:max_candidates]

    # Construir texto de consulta normalizado (sin keywords, solo semántica pura)
    query_text = _normalize_text(user_request)
    
    if not query_text or len(query_text.strip()) < 3:
        # Si la consulta es muy vacía, solo devolver las más recientes
        print("⚠️ [EMBED] Consulta sin texto significativo, usando solo recencia.")
        return recientes[:max_candidates]

    try:
        print("⚙️ [EMBED] Calculando embedding de la consulta (búsqueda semántica pura)...")
        print(f"   Consulta original: '{user_request}'")
        print(f"   Consulta normalizada: '{query_text}'")
        query_emb = model.encode([query_text], normalize_embeddings=True, show_progress_bar=False)[0]  # shape (d,)

        # Embeddings de solicitudes
        print(f"⚙️ [EMBED] Calculando embeddings de {len(recientes)} solicitudes...")
        texts = [build_text_for_embedding(s) for s in recientes]
        sols_emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)  # shape (N, d)

        # Similitud coseno: como ya están normalizados, es simplemente el dot product
        sims = np.dot(sols_emb, query_emb)  # (N,)

        # No usar umbral fijo - tomar las top-K más similares sin filtrar
        # El modelo de embeddings multilingüe captura similitudes semánticas naturalmente
        # Similar a cómo PrivateGPT usa top_k sin umbral estricto
        
        # Combinar score + fecha para ordenar
        scored = []
        for solicitud, sim in zip(recientes, sims):
            fecha = _parse_fecha(solicitud.get("fecha_creacion"))
            scored.append((float(sim), fecha, solicitud))

        # Ordenar por similitud desc, luego fecha desc
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Seleccionar top K (las más similares semánticamente)
        candidatos = [item[2] for item in scored[:max_candidates]]
        
        print(f"📊 Top {len(candidatos)} solicitudes seleccionadas por similitud semántica (de {len(recientes)} recientes)")

        print(
            f"✅ [EMBED] Seleccionadas {len(candidatos)} solicitudes candidatas "
            f"para enviar al LLM (de {len(recientes)} recientes, {len(solicitudes)} totales)."
        )
        
        # Log de las top 5 similitudes para debugging
        if len(scored) > 0:
            print(f"   📊 Top 5 similitudes semánticas:")
            for i, (sim, _, sol) in enumerate(scored[:5], 1):
                desc = sol.get("descripcion", "")[:60] or "Sin descripción"
                texto_embedding = build_text_for_embedding(sol)[:80]
                print(f"      {i}. Sim={sim:.3f} | ID={sol.get('id')} | {desc}...")
                print(f"         Texto usado para embedding: {texto_embedding}...")
        else:
            print(f"   ⚠️ No se encontraron solicitudes para comparar")

        return candidatos

    except Exception as e:
        print(f"⚠️ [EMBED] Error al calcular embeddings: {e}")
        print(f"   Usando fallback: solo recencia")
        import traceback
        traceback.print_exc()
        return recientes[:max_candidates]


def load_student_requests(student_data: Dict = None) -> List[Dict]:
    """
    Carga las solicitudes del estudiante desde student_data.
    
    Args:
        student_data: Datos del estudiante que incluyen solicitudes
    
    Returns:
        Lista de solicitudes del estudiante
    """
    if not student_data:
        print(f"⚠️ [load_student_requests] student_data es None")
        return []
    
    # Nuevo esquema principal
    solicitudes = student_data.get("solicitudes", [])
    # Compatibilidad hacia atrás
    if not solicitudes:
        solicitudes = student_data.get("solicitudes_balcon", [])
    
    print(f"🔍 [load_student_requests] Solicitudes encontradas: {len(solicitudes)}")
    if solicitudes:
        print(f"   Primeras 3 solicitudes: {[s.get('id', 'N/A') for s in solicitudes[:3]]}")
    
    return solicitudes if isinstance(solicitudes, list) else []


def format_request_for_llm(solicitud: Dict) -> str:
    """
    Formatea una solicitud para ser enviada al LLM.
    Solo incluye ID, código, fecha y descripción.
    DEPRECADO: Ya no se usa LLM para matching, solo embeddings.
    """
    parts = []

    parts.append(f"ID: {solicitud.get('id', 'N/A')}")
    codigo = solicitud.get('codigo', 'N/A')
    parts.append(f"Código: {codigo}")
    
    if solicitud.get('fecha_creacion'):
        parts.append(f"Fecha: {solicitud.get('fecha_creacion')}")
    if solicitud.get('descripcion'):
        parts.append(f"Descripción: {solicitud.get('descripcion')}")

    return "\n".join(parts)


def _priorize_requests_by_code(solicitudes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prioriza solicitudes por recencia y estado.
    Sin keywords - solo usa información semántica disponible.
    Las solicitudes más recientes y en estados activos tienen prioridad.
    
    Args:
        solicitudes: Lista de solicitudes candidatas (ya ordenadas por similitud)
    
    Returns:
        Lista reordenada por recencia y estado (sin keywords)
    """
    # Estados activos tienen más prioridad (más relevantes para relacionar)
    estados_activos = [1, 3, 6]  # INGRESADO, EN TRÁMITE, CORRECCIÓN
    
    def get_relevance_score(solicitud: Dict) -> float:
        """Score basado en estado y recencia, sin keywords."""
        estado = solicitud.get("estado", 0)
        fecha = _parse_fecha(solicitud.get("fecha_creacion"))
        
        # Priorizar estados activos
        estado_score = 1.0 if estado in estados_activos else 0.5
        
        # Priorizar solicitudes más recientes (normalizado)
        # Las más recientes tienen fecha más alta
        fecha_score = 1.0  # Ya están ordenadas por fecha en el ranking semántico
        
        return estado_score * fecha_score
    
    # Ordenar por relevancia (estado activo + recencia)
    # Mantener el orden semántico pero ajustar por relevancia
    solicitudes_priorizadas = sorted(
        solicitudes,
        key=lambda s: (
            get_relevance_score(s),
            _parse_fecha(s.get("fecha_creacion"))
        ),
        reverse=True
    )
    
    return solicitudes_priorizadas


def build_user_message_from_candidates(
    candidates: List[Dict[str, Any]],
    max_results: int = 3
) -> tuple:
    """
    Construye el mensaje para el usuario y la lista de IDs relacionados
    SIN usar LLM, solo basado en las candidatas seleccionadas por embeddings.
    
    Args:
        candidates: Lista de solicitudes candidatas (ya rankeadas por embeddings)
        max_results: Máximo de solicitudes a mostrar
    
    Returns:
        Tuple: (related_ids, user_message, reasoning, no_related)
    """
    if not candidates or len(candidates) == 0:
        return (
            [],
            "No he encontrado solicitudes relacionadas con tu requerimiento. "
            "¿Deseas continuar sin relacionar tu solicitud con ninguna solicitud previa?",
            "No se encontraron solicitudes relacionadas (filtro por embeddings)",
            True
        )
    
    # Priorizar por tipo de código antes de limitar
    prioritized = _priorize_requests_by_code(candidates)
    
    # Limitar a max_results
    final_candidates = prioritized[:max_results]
    
    # Extraer información y construir mensaje con formato mejorado
    related_ids = []
    lines = ["He encontrado algunas solicitudes previas que podrían estar relacionadas:\n"]
    
    for i, solicitud in enumerate(final_candidates, 1):
        req_id = solicitud.get("id")
        if not req_id:
            continue
            
        related_ids.append(req_id)
        
        codigo = solicitud.get("codigo_generado") or solicitud.get("codigo", "SIN-CODIGO")
        desc = (solicitud.get("descripcion") or "").strip()
        fecha_str = solicitud.get("fecha_creacion", "")
        
        # Formatear fecha
        fecha_display = ""
        if fecha_str:
            try:
                fecha_obj = _parse_fecha(fecha_str)
                if fecha_obj != datetime.min:
                    fecha_display = fecha_obj.strftime("%d/%m/%Y")
            except Exception:
                fecha_display = fecha_str[:10] if len(fecha_str) >= 10 else ""
        
        # Construir formato mejorado visualmente:
        # - Título a la izquierda
        # - Fecha a la derecha  
        # - Descripción abajo
        
        # Descripción truncada
        desc_truncada = desc[:150] if desc else "Sin descripción"
        if desc and len(desc) > 150:
            desc_truncada += "..."
        
        # Formato estructurado mejorado para mejor presentación visual
        # Usar formato que se vea bien en texto plano y markdown
        titulo_codigo = f"**{i}. {codigo}**"
        
        if fecha_display:
            # Crear bloque con título y fecha en líneas separadas pero visualmente alineadas
            # Formato: título arriba, fecha a la derecha (usando espacios para aproximar)
            # Calcular espacios para alinear fecha (aproximado para ~60 caracteres de ancho)
            ancho_aprox = 55
            len_titulo = len(titulo_codigo.replace('**', '').replace('*', ''))  # Longitud sin markdown
            espacios_alineacion = max(1, ancho_aprox - len_titulo - len(fecha_display))
            linea_completa = f"{titulo_codigo}{' ' * espacios_alineacion}*{fecha_display}*"
            lines.append(linea_completa)
        else:
            lines.append(titulo_codigo)
        
        # Descripción en línea separada con indentación y emoji para mejor visualización
        lines.append(f"   📄 {desc_truncada}")
        lines.append("")  # Línea en blanco para separar visualmente
    
    lines.append(
        "¿Deseas relacionar tu solicitud actual con alguna de estas? "
        "Si ninguna es relevante, puedes continuar sin relacionar."
    )
    
    user_message = "\n".join(lines)
    reasoning = (
        f"Selección basada en similitud semántica de embeddings (top-{len(final_candidates)} "
        f"de {len(candidates)} candidatas). Priorización por tipo de solicitud (justificaciones, bienestar)."
    )
    
    return related_ids, user_message, reasoning, False


def find_related_requests(
    user_request: str,
    intent_slots: Optional[Dict[str, Any]] = None,
    student_data: Optional[Dict] = None,
    max_results: int = 3
) -> Dict[str, Any]:
    """
    Encuentra solicitudes relacionadas usando embeddings semánticos (SIN LLM).
    
    Args:
        user_request: Texto de la solicitud del usuario
        intent_slots: Slots de intención extraídos del mensaje
        student_data: Datos del estudiante (incluye solicitudes_balcon)
        max_results: Número máximo de solicitudes relacionadas a retornar
    
    Returns:
        Dict con:
        - related_requests: Lista de solicitudes relacionadas (máximo max_results)
        - no_related: True si no hay solicitudes relacionadas
        - reasoning: Razonamiento de la selección (basado en embeddings)
        - user_message: Mensaje generado para el usuario (sin LLM)
    """
    # Cargar solicitudes del estudiante
    todas_las_solicitudes = load_student_requests(student_data)
    
    print(f"\n{'='*80}")
    print(f"🔍 [RELATED REQUESTS] Iniciando búsqueda de solicitudes relacionadas")
    print(f"{'='*80}")
    print(f"📝 Solicitud del usuario: '{user_request}'")
    print(f"📊 Total de solicitudes previas encontradas: {len(todas_las_solicitudes)}")
    
    if not todas_las_solicitudes:
        print(f"⚠️ No hay solicitudes previas del estudiante")
        return {
            "related_requests": [],
            "no_related": True,
            "reasoning": "No hay solicitudes previas del estudiante"
        }
    
    # Construir consulta mejorada usando intent_slots si está disponible
    # Sin keywords, solo usando la información semántica extraída
    query_mejorada = user_request
    if intent_slots:
        # Usar detalle_libre que contiene la semántica completa del mensaje original
        detalle_libre = intent_slots.get("detalle_libre", "")
        if detalle_libre and detalle_libre != user_request:
            # Combinar mensaje original con detalle libre para contexto semántico más rico
            query_mejorada = f"{user_request} {detalle_libre}".strip()
            print(f"🔍 [RELATED REQUESTS] Consulta enriquecida con detalle_libre: '{query_mejorada[:100]}'")
    
    # 🔥 CAPA INDUSTRIAL: Vector search con embeddings para pre-filtrar
    print(f"\n{'='*80}")
    print(f"⚙️ [OPTIMIZACIÓN] Aplicando ranking semántico (embeddings) para reducir universo...")
    print(f"{'='*80}")
    solicitudes = select_candidate_requests_with_embeddings(
        todas_las_solicitudes,
        user_request=query_mejorada,  # Usar consulta mejorada
        max_recent=MAX_SOLICITUDES_RECIENTES,
        max_candidates=MAX_SOLICITUDES_CANDIDATAS,
    )
    print(
        f"📉 Después del ranking semántico: {len(solicitudes)} solicitudes candidatas "
        f"para análisis (de {len(todas_las_solicitudes)} totales)."
    )
    print(f"{'='*80}\n")
    
    # 🔥 MEJORA NIVEL EMPRESA: No usar LLM, solo embeddings + lógica simple
    print(f"\n{'='*80}")
    print(f"⚙️ [SIN LLM] Generando mensaje y selección basada en embeddings únicamente...")
    print(f"{'='*80}")
    
    print(f"\n📋 Solicitudes candidatas seleccionadas por embeddings:")
    for i, sol in enumerate(solicitudes, 1):
        codigo = sol.get("codigo_generado") or sol.get("codigo", "N/A")
        desc = (sol.get("descripcion") or "")[:60] if sol.get("descripcion") else "Sin descripción"
        print(f"   {i}. ID: {sol.get('id')} | Código: {codigo} | {desc}...")
    
    # Construir mensaje y seleccionar IDs sin LLM
    related_ids, user_message, reasoning, no_related = build_user_message_from_candidates(
        solicitudes,
        max_results=max_results
    )
    
    print(f"\n✅ RESULTADO (sin LLM):")
    print(f"   - IDs de solicitudes relacionadas: {related_ids}")
    print(f"   - Mensaje para el usuario: {user_message[:100]}..." if len(user_message) > 100 else f"   - Mensaje para el usuario: {user_message}")
    print(f"   - Razonamiento: {reasoning}")
    print(f"   - No relacionadas: {no_related}")
    
    # Filtrar y formatear solicitudes relacionadas
    # Buscar en todas_las_solicitudes usando los IDs seleccionados
    related_requests = []
    print(f"\n🔍 Filtrando solicitudes relacionadas seleccionadas...")
    
    # Crear índice rápido de todas las solicitudes por ID
    todas_por_id = {sol.get("id"): sol for sol in todas_las_solicitudes if sol.get("id")}
    
    for req_id in related_ids:
        if req_id in todas_por_id:
            sol_original = todas_por_id[req_id]
            
            # Formatear fecha desde el backend
            fecha_creacion = sol_original.get("fecha_creacion", "")
            fecha_formateada = ""
            if fecha_creacion:
                try:
                    fecha_obj = _parse_fecha(fecha_creacion)
                    if fecha_obj != datetime.min:
                        fecha_formateada = fecha_obj.strftime("%d/%m/%Y")
                except Exception:
                    # Si falla el parseo, intentar formato simple
                    try:
                        fecha_str = str(fecha_creacion)
                        if len(fecha_str) >= 10:
                            fecha_formateada = fecha_str[8:10] + "/" + fecha_str[5:7] + "/" + fecha_str[0:4]
                    except Exception:
                        fecha_formateada = ""
            
            related_requests.append({
                "id": sol_original.get("id"),
                "codigo": sol_original.get("codigo_generado") or sol_original.get("codigo", ""),
                "estado": sol_original.get("estado_display") or sol_original.get("estado", ""),
                "tipo": sol_original.get("tipo_display") or sol_original.get("tipo", ""),
                "fecha_creacion": fecha_creacion,  # Fecha original para referencia
                "fecha_formateada": fecha_formateada,  # Fecha ya formateada dd/mm/yyyy
                "descripcion": sol_original.get("descripcion", ""),
                "display": _generate_request_display(sol_original)
            })
            print(f"   ✅ ID {req_id} agregado: {sol_original.get('tipo', 'N/A')}")
        else:
            print(f"   ⚠️ ID {req_id} no encontrado en todas las solicitudes")
    
    # Limitar a max_results
    related_requests = related_requests[:max_results]
    
    print(f"\n✅ RESULTADO FINAL:")
    print(f"   - Solicitudes relacionadas encontradas: {len(related_requests)}")
    print(f"   - Límite aplicado (max_results={max_results}): {len(related_requests)}")
    print(f"{'='*80}\n")
    
    return {
        "related_requests": related_requests,
        "no_related": no_related,
        "reasoning": reasoning,
        "user_message": user_message  # Mensaje generado sin LLM, solo con embeddings
    }


def _generate_request_display(solicitud: Dict) -> str:
    """
    Genera un texto descriptivo para mostrar la solicitud al usuario.
    
    Args:
        solicitud: Diccionario con la solicitud
    
    Returns:
        String descriptivo de la solicitud
    """
    # Convertir a string si es necesario
    tipo = solicitud.get("tipo", "SOLICITUD")
    if not isinstance(tipo, str):
        tipo = str(tipo) if tipo else "SOLICITUD"
    
    estado = solicitud.get("estado", "PENDIENTE")
    if not isinstance(estado, str):
        estado = str(estado) if estado else "PENDIENTE"
    
    fecha = solicitud.get("fecha_creacion", "")
    codigo = solicitud.get("codigo_generado") or solicitud.get("codigo", "")
    descripcion = solicitud.get("descripcion", "")

    # Formatear fecha si existe (acepta "YYYY-MM-DD HH:MM:SS" o ISO)
    fecha_display = ""
    if fecha:
        try:
            # Intentar formato "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(str(fecha), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Intentar ISO con o sin Z
                fecha_str = str(fecha).replace("Z", "+00:00")
                dt = datetime.fromisoformat(fecha_str)
            fecha_display = dt.strftime("%d/%m/%Y")
        except Exception:
            fecha_str = str(fecha)
            fecha_display = fecha_str[:10] if len(fecha_str) >= 10 else fecha_str

    # Construir base segura
    tipo_display = tipo.title() if isinstance(tipo, str) and tipo else "SOLICITUD"
    estado_display = estado.upper() if isinstance(estado, str) and estado else "PENDIENTE"
    
    base = f"{tipo_display} ({estado_display})"
    if fecha_display:
        base += f" - {fecha_display}"
    if codigo:
        base += f" - {codigo}"
    if descripcion:
        desc_str = str(descripcion)[:120] if descripcion else ""
        if desc_str:
            base += f" - {desc_str}"

    return base

