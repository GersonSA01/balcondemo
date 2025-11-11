import os, re, csv, math, argparse, random, json, unicodedata
from pathlib import Path
from typing import List, Iterable, Dict, Tuple
import numpy as np
import pandas as pd

from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score
from sklearn.feature_extraction.text import CountVectorizer

from sentence_transformers import SentenceTransformer

# ---------- Utils ----------
def strip_accents(s: str) -> str:
    s = s.replace("ñ", "__n_tilde__").replace("Ñ", "__N_tilde__")
    nf = unicodedata.normalize("NFD", s)
    s2 = "".join(ch for ch in nf if not unicodedata.combining(ch))
    s2 = unicodedata.normalize("NFC", s2)
    s2 = s2.replace("__n_tilde__", "ñ").replace("__N_tilde__", "Ñ")
    return s2

KEY_RULES = [
    ("ingles_modulos_notas", r"\b(m[oó]dulo.*ingl[eé]s|ingl[eé]s.*m[oó]dulo|migrar.*nota|nota.*ingl[eé]s|buckcenter|modulo \d+.*ingles|ingles.*modulo \d+|no puedo acceder.*modulo|siguiente modulo)\b"),
    ("homologacion_cambio_ies", r"\b(homolog|convalid|movilidad externa|cambio de universidad)\b"),
    ("admision_ingreso", r"\b(admisi[oó]n|ingresar|postulaci[oó]n|postular|cupo|inscribirme|inscripci[oó]n)\b"),
    ("soporte_sga_credenciales", r"\b(SGA|contrase[nñ]a|clave.*correo|correo.*institucional|no puedo ingresar|plataforma|aula virtual|credenciales)\b"),
    ("titulacion", r"\b(titulaci[oó]n|proyecto de titulaci[oó]n|examen complexivo)\b"),
    ("practicas_vinculacion", r"\b(pr[aá]cticas|preprofesional|pre-profesional|vinculaci[oó]n)\b"),
    ("educacion_continua", r"\b(educaci[oó]n continua|curso gratuito|link del curso|curso en l[ií]nea)\b"),
    ("becas_maestrias_pagos", r"\b(beca|maestr[ií]a|valor|pago|arancel|semestre|cu[oó]ta|cost[o|e]s?|nivel socioeconomico|estado socioeconomico)\b"),
    ("carreras_modalidades", r"\b(carrera|oferta acad[eé]mica|modalidad en l[ií]nea|derecho|psicolog[ií]a|educaci[oó]n b[aá]sica|trabajo social|turismo|enfermer[ií]a|sistemas|tecnolog[ií]a de la informaci[oó]n)\b"),
    ("examen_sede_evaluacion", r"\b(ex[aá]men(?:es)?|parcial|bimestre|sede|ciudad.*ex[aá]men|evaluaci[oó]n)\b"),
    ("certificados", r"\b(certificado.*sanci[oó]n|certificado.*no.*sancio|certificado.*disciplinario)\b"),
]
COMPILED_RULES = [(lab, re.compile(rx, re.IGNORECASE)) for lab, rx in KEY_RULES]

def assign_rule_category(text) -> str:
    # Manejar casos donde text puede ser NaN, None, float, etc.
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "otros"
    
    # Convertir a string y limpiar
    text_str = str(text).strip() if text else ""
    if not text_str:
        return "otros"
    
    try:
        t = strip_accents(text_str.lower())
        for lab, rx in COMPILED_RULES:
            if rx.search(t):
                return lab
    except Exception as e:
        # Si hay algún error en el procesamiento, retornar "otros"
        return "otros"
    return "otros"

def iter_rows(input_path: str, text_col: str, id_col: str = None, chunksize: int = 10000) -> Iterable[pd.DataFrame]:
    """
    Generator that yields DataFrames with columns: ['_id','_text'] (+ any others kept).
    Supports CSV and JSONL efficiently. JSON (array) tries pandas fallback (may need RAM).
    """
    p = Path(input_path)
    suf = p.suffix.lower()

    if suf in [".csv"]:
        for chunk in pd.read_csv(input_path, chunksize=chunksize):
            chunk["_text"] = chunk[text_col].astype(str).fillna("").str.strip()
            if id_col and id_col in chunk.columns:
                chunk["_id"] = chunk[id_col]
            else:
                # build sequential id within chunk; we'll offset later
                chunk["_id"] = chunk.index.astype(str)
            yield chunk[["_id","_text"]].copy()

    elif suf in [".jsonl", ".ndjson"]:
        # Stream line by line
        batch_ids, batch_text = [], []
        with open(input_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if not line.strip():
                    continue
                obj = json.loads(line)
                txt = str(obj.get(text_col,"")).strip()
                if not txt:
                    continue
                _id = str(obj.get(id_col, i)) if id_col else str(i)
                batch_ids.append(_id); batch_text.append(txt)
                if len(batch_text) >= chunksize:
                    yield pd.DataFrame({"_id": batch_ids, "_text": batch_text})
                    batch_ids, batch_text = [], []
        if batch_text:
            yield pd.DataFrame({"_id": batch_ids, "_text": batch_text})

    elif suf in [".json"]:
        # Para JSON grande, intentar leer de forma eficiente
        # Primero verificar si es un array JSON (requiere cargar completo)
        # Si es muy grande, considerar convertir a JSONL primero
        import json
        try:
            # Intentar leer el archivo completo (puede ser lento pero necesario para arrays JSON)
            print(f"   Leyendo JSON completo... (esto puede tardar para archivos grandes)")
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Procesar en chunks para no sobrecargar memoria después
            total_items = len(data)
            print(f"   Total de items en JSON: {total_items}")
            for i in range(0, total_items, chunksize):
                chunk_data = data[i:i+chunksize]
                df = pd.DataFrame(chunk_data)
                df["_text"] = df[text_col].astype(str).fillna("").str.strip()
                if id_col and id_col in df.columns:
                    df["_id"] = df[id_col].astype(str)
                else:
                    df["_id"] = df.index.astype(str)
                yield df[["_id","_text"]].copy()
                # Liberar memoria del chunk
                del chunk_data, df
        except MemoryError:
            raise MemoryError(
                f"El archivo JSON es demasiado grande para cargar en memoria. "
                f"Recomendación: Convierte el archivo a JSONL (una línea por objeto JSON) "
                f"usando un script separado, o reduce el tamaño del archivo."
            )
    else:
        raise ValueError(f"Unsupported file type: {suf}")

def choose_k_on_sample(emb_sample: np.ndarray, k_min=6, k_max=30, step=2) -> int:
    best_k, best_s = None, -1
    for k in range(k_min, k_max+1, step):
        km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init="auto", batch_size=4096)
        labels = km.fit_predict(emb_sample)
        if len(set(labels)) < 2:
            continue
        s = silhouette_score(emb_sample, labels, metric="euclidean")
        if s > best_s:
            best_k, best_s = k, s
    return best_k or 10

def build_ctfidf_labels(docs_by_cluster: Dict[int, List[str]], top_n=10) -> Dict[int, List[str]]:
    clusters = sorted(docs_by_cluster.keys())
    joined = [" . ".join(docs_by_cluster[c]) for c in clusters]
    vect = CountVectorizer(ngram_range=(1,2), min_df=2)
    X = vect.fit_transform(joined)  # (n_clusters, vocab)
    tf = X.astype(float)
    doc_len = np.maximum(tf.sum(axis=1), 1)
    tf_norm = tf.multiply(1/doc_len)
    df_term = np.maximum((tf>0).sum(axis=0), 1)
    idf = np.log(len(clusters) / df_term).A1
    ctfidf = tf_norm.multiply(idf)
    terms = np.array(vect.get_feature_names_out())
    labels = {}
    for i, c in enumerate(clusters):
        row = ctfidf.getrow(i).toarray().ravel()
        idx = row.argsort()[::-1][:top_n]
        labels[c] = terms[idx].tolist()
    return labels

def guess_cluster_name(top_terms: List[str]) -> str:
    txt = " ".join(top_terms)
    t = strip_accents(txt.lower())
    # simple mapping using rules
    for lab, rx in COMPILED_RULES:
        if re.search(rx, t):
            return lab
    return "cluster_" + "_".join(top_terms[:2])

# ---------- Main pipeline ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Ruta del archivo grande (CSV/JSON/JSONL)")
    ap.add_argument("--text-col", default="pregunta_inicial", help="Nombre de la columna con texto")
    ap.add_argument("--id-col", default="solicitud_id", help="Columna id (si no existe, se auto genera)")
    ap.add_argument("--outdir", default="out_balcon", help="Salida")
    ap.add_argument("--model", default="intfloat/multilingual-e5-small", help="Modelo de embeddings (small=faster, base=better)")
    ap.add_argument("--batch", type=int, default=128, help="Tamaño de batch de embeddings (reducir si hay problemas de RAM)")
    ap.add_argument("--chunksize", type=int, default=5000, help="Tamaño de chunk para leer archivos (reducir para menos RAM)")
    ap.add_argument("--sample-for-k", type=int, default=10000, help="Muestras para elegir K (reducir para más velocidad)")
    ap.add_argument("--kmin", type=int, default=8)
    ap.add_argument("--kmax", type=int, default=25)
    ap.add_argument("--kstep", type=int, default=3)
    ap.add_argument("--max_docs_label", type=int, default=50000, help="Máx docs usados para c-TF-IDF (reducir para menos RAM)")
    ap.add_argument("--use-float16", action="store_true", help="Usar float16 en lugar de float32 (ahorra memoria pero menos precisión)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    # 1) Embeddings por chunks
    print(">> Cargando modelo:", args.model)
    model = SentenceTransformer(args.model)

    chunk_files = []
    index_rows = []
    n_total = 0
    print(">> Generando embeddings por lotes...")
    print(f"   Configuración: chunksize={args.chunksize}, batch={args.batch}, modelo={args.model}")
    dtype = np.float16 if args.use_float16 else np.float32
    if args.use_float16:
        print("   ⚠️  Usando float16 (menos precisión pero menos memoria)")
    
    import gc
    for chunk_idx, df in enumerate(iter_rows(args.input, args.text_col, args.id_col, chunksize=args.chunksize)):
        texts = df["_text"].tolist()
        if not texts or all(not t.strip() for t in texts):
            print(f"   chunk {chunk_idx} -> 0 filas (vacío, saltando)")
            continue
        
        # Limpiar memoria antes de procesar
        if chunk_idx > 0 and chunk_idx % 10 == 0:
            gc.collect()
        
        # e5: prefijo "passage: " (solo si el modelo lo requiere)
        if "e5" in args.model.lower():
            corpus = ["passage: " + t for t in texts]
        else:
            corpus = texts
        
        emb = model.encode(corpus, batch_size=args.batch, normalize_embeddings=True, 
                          show_progress_bar=True, convert_to_numpy=True)
        emb = np.asarray(emb, dtype=dtype)
        fpath = os.path.join(args.outdir, f"emb_chunk_{chunk_idx:05d}.npy")
        np.save(fpath, emb)
        chunk_files.append(fpath)
        
        # Liberar memoria del embedding inmediatamente después de guardar
        del emb
        gc.collect()
        
        # index
        idx_chunk = pd.DataFrame({
            "row_global": range(n_total, n_total + len(df)),
            "id": df["_id"].astype(str).values,
            "text": df["_text"].values
        })
        index_rows.append(idx_chunk)
        n_total += len(df)
        print(f"   chunk {chunk_idx} -> {len(df)} filas procesadas (Total acumulado: {n_total})")
        
        # Liberar memoria del DataFrame
        del df, texts, corpus
        gc.collect()

    index_df = pd.concat(index_rows, ignore_index=True)
    index_path = os.path.join(args.outdir, "row_index.csv")
    index_df.to_csv(index_path, index=False)
    print(">> Total filas:", n_total)

    # 2) Elegir K en una muestra
    print(">> Eligiendo K por silhouette...")
    # Sample embeddings
    sample_vecs = []
    want = min(args.sample_for_k, n_total)
    remain = want
    # muestreo simple: toma secuencias de chunks hasta cubrir 'want'
    for f in chunk_files:
        E = np.load(f)
        take = min(remain, len(E))
        if take > 0:
            sample_vecs.append(E[:take])
            remain -= take
        if remain <= 0:
            break
    emb_sample = np.vstack(sample_vecs) if sample_vecs else np.load(chunk_files[0])
    K = choose_k_on_sample(emb_sample, args.kmin, args.kmax, args.kstep)
    print(">> K elegido:", K)

    # 3) Entrenar MiniBatchKMeans parcial
    print(">> Entrenando MiniBatchKMeans...")
    km = MiniBatchKMeans(n_clusters=K, random_state=42, n_init="auto", batch_size=4096)
    # partial_fit passes
    for f in chunk_files:
        E = np.load(f)
        km.partial_fit(E)

    # 4) Predecir labels por chunk
    print(">> Etiquetando clusters...")
    label_chunk_files = []
    for chunk_idx, f in enumerate(chunk_files):
        E = np.load(f)
        y = km.predict(E)
        out = os.path.join(args.outdir, f"labels_chunk_{chunk_idx:05d}.npy")
        np.save(out, y)
        label_chunk_files.append(out)

    # 5) c-TF-IDF para nombrar clusters (muestra hasta max_docs_label)
    print(">> Construyendo etiquetas por cluster con c-TF-IDF...")
    docs_by_cluster = {}
    used = 0
    max_per_cluster = max(50, args.max_docs_label // K)  # mínimo 50 docs por cluster
    chunk_iter = pd.read_csv(index_path, chunksize=args.chunksize)
    for chunk_idx, df_rows in enumerate(chunk_iter):
        if chunk_idx >= len(label_chunk_files):
            break
        y = np.load(label_chunk_files[chunk_idx])
        texts = df_rows["text"].tolist()
        # Asegurar que textos y labels tengan la misma longitud
        min_len = min(len(texts), len(y))
        for t, c in zip(texts[:min_len], y[:min_len]):
            c_int = int(c)
            docs_by_cluster.setdefault(c_int, [])
            if len(docs_by_cluster[c_int]) < max_per_cluster:
                docs_by_cluster[c_int].append(t)
                used += 1
        if used >= args.max_docs_label:
            break
        # Liberar memoria periódicamente
        if chunk_idx % 20 == 0:
            gc.collect()

    top_terms = build_ctfidf_labels(docs_by_cluster, top_n=10)
    cluster_names = {c: guess_cluster_name(terms) for c, terms in top_terms.items()}

    # 6) Exportar etiquetas de cluster
    cl_rows = []
    for c in range(K):
        terms = top_terms.get(c, [])
        name = cluster_names.get(c, "cluster_misc")
        cl_rows.append({"cluster": c, "label": name, "top_terms": ", ".join(terms)})
    cl_df = pd.DataFrame(cl_rows).sort_values("cluster")
    cl_df.to_csv(os.path.join(args.outdir, "cluster_labels.csv"), index=False)

    # 7) Componer categoría final: regla de alta precisión > nombre_cluster
    print(">> Componiendo categoría final y exportando asignaciones...")
    assign_rows = []
    # volver a recorrer index + labels por chunks
    chunk_iter = pd.read_csv(index_path, chunksize=args.chunksize)
    for chunk_idx, df_rows in enumerate(chunk_iter):
        if chunk_idx >= len(label_chunk_files):
            break
        y = np.load(label_chunk_files[chunk_idx])
        # Asegurar que los textos sean strings y manejar NaN
        texts = df_rows["text"].fillna("").astype(str).tolist()
        ids = df_rows["id"].astype(str).values
        # Asegurar que todos los arrays tengan la misma longitud
        min_len = min(len(texts), len(y), len(ids))
        cats = []
        clusters_list = []
        ids_list = []
        for i in range(min_len):
            t = texts[i] if texts[i] and texts[i] != "nan" else ""
            c = int(y[i])
            rule = assign_rule_category(t)
            if rule != "otros":
                cats.append(rule)
            else:
                cats.append(cluster_names.get(c, "otros"))
            clusters_list.append(c)
            ids_list.append(ids[i])
        out_chunk = pd.DataFrame({
            "id": ids_list,
            "cluster": clusters_list,
            "categoria_final": cats
        })
        assign_rows.append(out_chunk)
        
        # Liberar memoria periódicamente
        if chunk_idx % 20 == 0:
            gc.collect()
            print(f"   Procesado chunk {chunk_idx}/{len(label_chunk_files)}")

    assign_df = pd.concat(assign_rows, ignore_index=True)
    # Export Parquet/CSV
    out_parquet = os.path.join(args.outdir, "assignments.parquet")
    try:
        assign_df.to_parquet(out_parquet, index=False)
        out_assign = out_parquet
    except Exception:
        out_csv = os.path.join(args.outdir, "assignments.csv")
        assign_df.to_csv(out_csv, index=False)
        out_assign = out_csv

    # 8) Top categorías
    top = assign_df["categoria_final"].value_counts().rename_axis("categoria").reset_index(name="conteo")
    top.to_csv(os.path.join(args.outdir, "top_categorias.csv"), index=False)

    print(">> Listo.")
    print("Salidas:")
    print(" -", index_path)
    print(" -", os.path.join(args.outdir, "cluster_labels.csv"))
    print(" -", out_assign)
    print(" -", os.path.join(args.outdir, "top_categorias.csv"))

if __name__ == "__main__":
    main()

"""
EJEMPLO DE USO:
===============

# OPCIÓN 1: Rápida y eficiente en memoria (RECOMENDADO para 16GB RAM)
python analizar_solicitudes.py \
  --input solicitudes_todas_preguntas.json \
  --text-col pregunta_inicial \
  --id-col solicitud_id \
  --outdir resultados_balcon \
  --model intfloat/multilingual-e5-small \
  --batch 128 \
  --chunksize 5000 \
  --sample-for-k 10000 \
  --kmin 8 \
  --kmax 25 \
  --kstep 3 \
  --use-float16

# OPCIÓN 2: Más preciso pero más lento (si tienes más RAM disponible)
python analizar_solicitudes.py \
  --input solicitudes_todas_preguntas.json \
  --text-col pregunta_inicial \
  --id-col solicitud_id \
  --outdir resultados_balcon \
  --model intfloat/multilingual-e5-base \
  --batch 256 \
  --chunksize 10000 \
  --sample-for-k 15000 \
  --kmin 10 \
  --kmax 30 \
  --kstep 2

# Para archivo CSV:
python analizar_solicitudes.py \
  --input solicitudes.csv \
  --text-col pregunta_inicial \
  --id-col solicitud_id \
  --outdir resultados_balcon

# Para archivo JSONL (más eficiente para datasets grandes):
python analizar_solicitudes.py \
  --input solicitudes.jsonl \
  --text-col pregunta_inicial \
  --id-col solicitud_id \
  --outdir resultados_balcon

ARCHIVOS GENERADOS:
===================
- out_balcon/row_index.csv: Índice de todas las filas procesadas
- out_balcon/cluster_labels.csv: Etiquetas y términos clave de cada cluster
- out_balcon/assignments.csv (o .parquet): Asignaciones de cluster y categoría final
- out_balcon/top_categorias.csv: Conteo de solicitudes por categoría

NOTAS PARA SISTEMAS CON POCA RAM (16GB):
========================================
- Usa --model intfloat/multilingual-e5-small (más rápido, menos memoria)
- Usa --batch 64-128 (reducción de memoria)
- Usa --chunksize 3000-5000 (chunks más pequeños)
- Usa --use-float16 (ahorra ~50% de memoria en embeddings)
- Reduce --sample-for-k a 5000-10000
- Reduce --max_docs_label a 30000-50000

OPTIMIZACIONES APLICADAS:
=========================
- Chunks pequeños para no sobrecargar RAM
- Limpieza automática de memoria (gc.collect)
- Modelo pequeño por defecto
- Batch size reducido
- Opción de float16 para ahorrar memoria

TIEMPO ESTIMADO (Ryzen 7 5700U, 16GB RAM):
==========================================
- Con e5-small + float16: 2-4 horas para 234K solicitudes
- Con e5-base: 4-8 horas para 234K solicitudes

Los embeddings se guardan en .npy para poder reutilizarlos
"""
