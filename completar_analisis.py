"""
Script para completar el análisis usando los archivos ya procesados.
Solo genera el archivo final de assignments sin reprocesar embeddings.
"""
import os
import pandas as pd
import numpy as np
import gc
from analizar_solicitudes import assign_rule_category, COMPILED_RULES, strip_accents
import re
from collections import Counter

def guess_cluster_name(top_terms):
    """Función auxiliar para nombrar clusters"""
    txt = " ".join(top_terms)
    t = strip_accents(txt.lower())
    for lab, rx in COMPILED_RULES:
        if re.search(rx, t):
            return lab
    return "cluster_" + "_".join(top_terms[:2])

def main():
    outdir = "resultados_balcon"
    index_path = os.path.join(outdir, "row_index.csv")
    cluster_labels_path = os.path.join(outdir, "cluster_labels.csv")
    
    if not os.path.exists(index_path):
        print(f"❌ No se encuentra {index_path}")
        return
    
    if not os.path.exists(cluster_labels_path):
        print(f"❌ No se encuentra {cluster_labels_path}")
        return
    
    # Cargar las etiquetas de cluster
    print(">> Cargando etiquetas de cluster...")
    cluster_df = pd.read_csv(cluster_labels_path)
    cluster_names = {}
    for _, row in cluster_df.iterrows():
        cluster_names[row['cluster']] = row['label']
    
    print(f">> Clusters encontrados: {len(cluster_names)}")
    
    # Encontrar todos los archivos de labels
    label_files = sorted([f for f in os.listdir(outdir) if f.startswith("labels_chunk_") and f.endswith(".npy")])
    print(f">> Archivos de labels encontrados: {len(label_files)}")
    
    # Leer el índice
    print(">> Leyendo índice...")
    chunk_iter = pd.read_csv(index_path, chunksize=5000)
    
    # Procesar por chunks
    print(">> Generando asignaciones finales...")
    assign_rows = []
    chunk_idx = 0
    
    for df_rows in chunk_iter:
        if chunk_idx >= len(label_files):
            break
        
        label_file = os.path.join(outdir, label_files[chunk_idx])
        y = np.load(label_file)
        
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
        
        if (chunk_idx + 1) % 10 == 0:
            gc.collect()
            print(f"   Procesado chunk {chunk_idx + 1}/{len(label_files)}")
        
        chunk_idx += 1
    
    # Combinar todos los chunks
    print(">> Combinando resultados...")
    assign_df = pd.concat(assign_rows, ignore_index=True)
    
    # Exportar
    print(">> Guardando resultados...")
    out_csv = os.path.join(outdir, "assignments.csv")
    assign_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"✅ Guardado en: {out_csv}")
    
    # Generar resumen de categorías
    print(">> Generando resumen de categorías...")
    top = assign_df["categoria_final"].value_counts().rename_axis("categoria").reset_index(name="conteo")
    top_path = os.path.join(outdir, "top_categorias.csv")
    top.to_csv(top_path, index=False, encoding="utf-8-sig")
    print(f"✅ Guardado en: {top_path}")
    
    print("\n" + "="*60)
    print("✅ PROCESO COMPLETADO")
    print("="*60)
    print(f"Total de solicitudes procesadas: {len(assign_df)}")
    print(f"\nTop 10 categorías:")
    print(top.head(10).to_string(index=False))
    print(f"\nArchivos generados:")
    print(f" - {out_csv}")
    print(f" - {top_path}")

if __name__ == "__main__":
    main()

