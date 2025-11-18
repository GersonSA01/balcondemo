import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
import joblib

# Ruta relativa al directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "app" / "data" / "solicitudes_entrenamiento_2024_2025.jsonl"
MODELS_DIR = BASE_DIR / "models"

def load_data(path):
    texts = []
    cats = []
    subcats = []
    depts = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            msgs = [m for m in rec.get("messages", []) if m.get("role") == "assistant"]
            if not msgs:
                continue
            last = msgs[-1]
            slots = last.get("intent_slots", {}) or {}
            meta = last.get("response_metadata", {}) or {}

            text = (
                slots.get("original_user_message")
                or rec.get("messages", [{}])[0].get("message")
            )
            if not text:
                continue

            category = meta.get("category") or "OTROS"
            subcategory = meta.get("subcategory") or "OTROS"
            department = meta.get("department") or "OTROS"

            texts.append(text)
            cats.append(category)
            subcats.append(subcategory)
            depts.append(department)

    return texts, cats, subcats, depts


def main():
    # Verificar que existe el archivo de datos
    if not DATA_PATH.exists():
        print(f"❌ Error: No se encontró el archivo de datos: {DATA_PATH}")
        return
    
    # Crear directorio models si no existe
    MODELS_DIR.mkdir(exist_ok=True)
    
    texts, cats, subcats, depts = load_data(DATA_PATH)

    print(f"Total muestras: {len(texts)}")

    # 1) Embeddings con MiniLM (lo que ya usas para clustering)
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    X = model.encode(texts, show_progress_bar=True)

    # 2) LabelEncoders
    le_cat = LabelEncoder().fit(cats)
    le_sub = LabelEncoder().fit(subcats)
    le_dep = LabelEncoder().fit(depts)

    y_cat = le_cat.transform(cats)
    y_sub = le_sub.transform(subcats)
    y_dep = le_dep.transform(depts)

    # 3) Tres clasificadores (uno por salida)
    clf_cat = LogisticRegression(max_iter=1000).fit(X, y_cat)
    clf_sub = LogisticRegression(max_iter=1000).fit(X, y_sub)
    clf_dep = LogisticRegression(max_iter=1000).fit(X, y_dep)

    model_path = MODELS_DIR / "intent_classifier.pkl"
    joblib.dump(
        {
            "embed_model_name": "paraphrase-multilingual-MiniLM-L12-v2",
            "le_cat": le_cat,
            "le_sub": le_sub,
            "le_dep": le_dep,
            "clf_cat": clf_cat,
            "clf_sub": clf_sub,
            "clf_dep": clf_dep,
        },
        model_path,
    )

    print(f"✅ Modelo guardado en {model_path}")
    print(f"   Categorías únicas: {len(le_cat.classes_)}")
    print(f"   Subcategorías únicas: {len(le_sub.classes_)}")
    print(f"   Departamentos únicos: {len(le_dep.classes_)}")


if __name__ == "__main__":
    main()
