from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json
import threading

# Ruta base de este módulo: .../app/services
BASE_DIR = Path(__file__).resolve().parent.parent  # /app
CRONOGRAMA_PATH = BASE_DIR / "data" / "cronograma_retiros.json"

_CRONOGRAMA_CACHE: Optional[List[Dict]] = None
_CRONOGRAMA_LOCK = threading.Lock()


def _load_cronograma_raw() -> List[Dict]:
    """
    Lee y cachea el JSON de cronogramas.
    No usa base de datos, solo un archivo JSON.
    """
    global _CRONOGRAMA_CACHE
    with _CRONOGRAMA_LOCK:
        if _CRONOGRAMA_CACHE is not None:
            return _CRONOGRAMA_CACHE

        try:
            with open(CRONOGRAMA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("El JSON de cronogramas debe ser una lista de objetos")
                _CRONOGRAMA_CACHE = data
        except FileNotFoundError:
            print(f"⚠️ [Cronograma] Archivo no encontrado: {CRONOGRAMA_PATH}")
            _CRONOGRAMA_CACHE = []
        except Exception as e:
            print(f"⚠️ [Cronograma] Error al cargar cronograma: {e}")
            _CRONOGRAMA_CACHE = []

        return _CRONOGRAMA_CACHE


def _parse_date(value: str) -> date:
    """Convierte 'YYYY-MM-DD' a date."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def _filtrar_eventos_retiro(periodo_academico: Optional[str], fecha_hoy: Optional[date] = None) -> Dict[str, Dict]:
    """
    Devuelve un dict con las ventanas configuradas para retiro en un periodo:

    {
      "RETIRO_DEFINITIVO": {...},
      "RETIRO_FUERZA_MAYOR": {...}
    }
    
    Prioridad:
    1. Si hay periodo_academico y coincide, usar ese
    2. Si no, buscar el cronograma más cercano a fecha_hoy (o fecha actual)
    3. Si no hay fecha_hoy, usar el más reciente disponible
    """
    if fecha_hoy is None:
        fecha_hoy = date.today()
    
    eventos = _load_cronograma_raw()
    resultado: Dict[str, Dict] = {}
    resultado_fallback: Dict[str, Dict] = {}  # Para cuando no hay periodo específico
    eventos_por_tipo: Dict[str, List[Dict]] = {"RETIRO_DEFINITIVO": [], "RETIRO_FUERZA_MAYOR": []}

    for ev in eventos:
        try:
            tipo = (ev.get("tipo") or "").upper()
            if tipo not in ("RETIRO_DEFINITIVO", "RETIRO_FUERZA_MAYOR"):
                continue

            fi = _parse_date(ev["fecha_inicio"])
            ff = _parse_date(ev["fecha_fin"])
            
            evento_dict = {
                "tipo": tipo,
                "periodo_academico": ev.get("periodo_academico", ""),
                "fecha_inicio": fi,
                "fecha_fin": ff,
            }
            
            # Si hay periodo específico y coincide, agregarlo al resultado
            if periodo_academico and ev.get("periodo_academico") == periodo_academico:
                resultado[tipo] = evento_dict
            else:
                # Guardar todos los eventos de este tipo para seleccionar el mejor
                eventos_por_tipo[tipo].append(evento_dict)
        except Exception as e:
            print(f"⚠️ [Cronograma] Evento inválido en JSON: {ev} -> {e}")
            continue

    # Si no encontramos eventos para el periodo específico, buscar el más cercano a fecha_hoy
    if not resultado:
        for tipo, lista_eventos in eventos_por_tipo.items():
            if not lista_eventos:
                continue
            
            # Buscar el evento más cercano a fecha_hoy
            mejor_evento = None
            menor_distancia = None
            
            for evento in lista_eventos:
                fi = evento["fecha_inicio"]
                ff = evento["fecha_fin"]
                
                # Si fecha_hoy está dentro del rango, ese es el mejor
                if fi <= fecha_hoy <= ff:
                    mejor_evento = evento
                    break
                # Si no, calcular distancia (preferir eventos futuros o recientes)
                elif fecha_hoy < fi:
                    distancia = (fi - fecha_hoy).days
                    if menor_distancia is None or distancia < menor_distancia:
                        menor_distancia = distancia
                        mejor_evento = evento
                elif fecha_hoy > ff:
                    # Eventos pasados: preferir el más reciente
                    distancia = (fecha_hoy - ff).days
                    if mejor_evento is None or (mejor_evento["fecha_fin"] < ff):
                        mejor_evento = evento
            
            # Si no encontramos uno mejor, usar el primero disponible
            if mejor_evento:
                resultado_fallback[tipo] = mejor_evento
            elif lista_eventos:
                resultado_fallback[tipo] = lista_eventos[0]
        
        if resultado_fallback:
            periodo_usado = next(iter(resultado_fallback.values())).get("periodo_academico", "")
            print(f"⚠️ [Cronograma] No se encontró periodo '{periodo_academico}', usando cronograma del periodo '{periodo_usado}' (más cercano a {fecha_hoy})")
            return resultado_fallback
    
    return resultado


def evaluar_cronograma_retiro(
    fecha_hoy: date,
    periodo_actual: Optional[str]
) -> Tuple[str, Dict]:
    """
    Lógica central de negocio para retiro de asignaturas (SIN LLM).

    Retorna:
      estado: uno de
        - "VENTANA_RETIRO_DEFINITIVO_ACTIVA"
        - "VENTANA_RETIRO_FUERZA_MAYOR_ACTIVA"
        - "FUERA_DE_CRONOGRAMA"

      info: dict con fechas listas para mostrar.
    """
    eventos = _filtrar_eventos_retiro(periodo_actual, fecha_hoy)

    def_fmt = eventos.get("RETIRO_DEFINITIVO")
    fm_fmt = eventos.get("RETIRO_FUERZA_MAYOR")

    def fmt(d):
        from datetime import date as _date
        if isinstance(d, _date):
            return d.strftime("%d/%m/%Y")
        return ""

    # Obtener periodo del cronograma (puede ser diferente al periodo_actual si no coincide)
    periodo_cronograma = ""
    if def_fmt:
        periodo_cronograma = def_fmt.get("periodo_academico", periodo_actual or "")
    elif fm_fmt:
        periodo_cronograma = fm_fmt.get("periodo_academico", periodo_actual or "")
    else:
        periodo_cronograma = periodo_actual or ""
    
    info_base = {
        "periodo_academico": periodo_cronograma,
        "retiro_def_inicio": fmt(def_fmt["fecha_inicio"]) if def_fmt else "",
        "retiro_def_fin": fmt(def_fmt["fecha_fin"]) if def_fmt else "",
        "fuerza_mayor_inicio": fmt(fm_fmt["fecha_inicio"]) if fm_fmt else "",
        "fuerza_mayor_fin": fmt(fm_fmt["fecha_fin"]) if fm_fmt else "",
    }

    if def_fmt and def_fmt["fecha_inicio"] <= fecha_hoy <= def_fmt["fecha_fin"]:
        info = {
            **info_base,
            "inicio": fmt(def_fmt["fecha_inicio"]),
            "fin": fmt(def_fmt["fecha_fin"]),
            "tipo": "RETIRO_DEFINITIVO",
        }
        return "VENTANA_RETIRO_DEFINITIVO_ACTIVA", info

    if fm_fmt and fm_fmt["fecha_inicio"] <= fecha_hoy <= fm_fmt["fecha_fin"]:
        info = {
            **info_base,
            "inicio": fmt(fm_fmt["fecha_inicio"]),
            "fin": fmt(fm_fmt["fecha_fin"]),
            "tipo": "RETIRO_FUERZA_MAYOR",
        }
        return "VENTANA_RETIRO_FUERZA_MAYOR_ACTIVA", info

    return "FUERA_DE_CRONOGRAMA", info_base

