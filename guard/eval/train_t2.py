"""
T2 Model Training & ONNX Export Script.
Trains multi-head sentence classifiers (main: injection, aux: quoted/meta)
on guard/eval/corpus/train.jsonl and exports to ONNX for CPU execution.
Validates performance on guard/eval/corpus/dev.jsonl (test.jsonl held out).
"""
import json
import hashlib
from pathlib import Path
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from skl2onnx import to_onnx
from skl2onnx.common.data_types import StringTensorType

def load_data(file_path: Path):
    texts, y_main, y_aux = [], [], []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            texts.append(item["text"].lower())  # lowercase outside the graph: ONNX StringNormalizer needs a system locale
            y_main.append(1 if item.get("label") in ("attack", 1, True) else 0)
            is_meta = (item.get("family") in ("quoted_meta", "quoted_attack", "meta") or "quoted" in item.get("family", ""))
            y_aux.append(1 if is_meta else 0)
    return texts, np.array(y_main), np.array(y_aux)

def train_and_export():
    models_dir = Path(__file__).resolve().parents[1] / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    train_file = Path(__file__).resolve().parent / "corpus" / "train.jsonl"
    dev_file = Path(__file__).resolve().parent / "corpus" / "dev.jsonl"

    print(f"Loading training data from {train_file}...")
    X_train, y_train_main, y_train_aux = load_data(train_file)
    print(f"Train samples: {len(X_train)} (Attacks: {sum(y_train_main)}, Meta: {sum(y_train_aux)})")

    # 1. Main Injection Classifier Pipeline
    pipe_main = Pipeline([
        ("vec", TfidfVectorizer(ngram_range=(1, 3), sublinear_tf=True, min_df=1, lowercase=False)),
        ("clf", LogisticRegression(C=5.0, max_iter=1000, random_state=42))
    ])
    pipe_main.fit(X_train, y_train_main)

    # 2. Aux Quoted/Meta Classifier Pipeline
    pipe_aux = Pipeline([
        ("vec", TfidfVectorizer(ngram_range=(1, 3), sublinear_tf=True, min_df=1, lowercase=False)),
        ("clf", LogisticRegression(C=5.0, max_iter=1000, random_state=42))
    ])
    pipe_aux.fit(X_train, y_train_aux)

    # Export to ONNX
    initial_type = [("text", StringTensorType([None, 1]))]
    
    main_onnx = to_onnx(pipe_main, initial_types=initial_type, options={id(pipe_main.steps[-1][1]): {"zipmap": False}})
    main_path = models_dir / "t2_main.onnx"
    with open(main_path, "wb") as f:
        f.write(main_onnx.SerializeToString())

    aux_onnx = to_onnx(pipe_aux, initial_types=initial_type, options={id(pipe_aux.steps[-1][1]): {"zipmap": False}})
    aux_path = models_dir / "t2_aux.onnx"
    with open(aux_path, "wb") as f:
        f.write(aux_onnx.SerializeToString())

    # Compute SHA-256
    hasher = hashlib.sha256()
    with open(main_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    main_sha256 = hasher.hexdigest()

    print(f"Exported {main_path} (SHA-256: {main_sha256})")
    print(f"Exported {aux_path}")

    # Evaluate on dev.jsonl
    print("\n--- Evaluating on DEV split (held-out from training) ---")
    X_dev, y_dev_main, y_dev_aux = load_data(dev_file)
    probs_main = pipe_main.predict_proba(X_dev)[:, 1]
    probs_aux = pipe_aux.predict_proba(X_dev)[:, 1]

    preds = []
    for p_main, p_aux in zip(probs_main, probs_aux):
        if p_main >= 0.70 and p_aux >= 0.65:
            # Quoted meta stays benign
            preds.append(0)
        elif p_main >= 0.50:
            preds.append(1)
        else:
            preds.append(0)

    preds = np.array(preds)
    tp = sum((preds == 1) & (y_dev_main == 1))
    fp = sum((preds == 1) & (y_dev_main == 0))
    tn = sum((preds == 0) & (y_dev_main == 0))
    fn = sum((preds == 0) & (y_dev_main == 1))

    accuracy = (tp + tn) / len(y_dev_main)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    print(f"DEV Total Items : {len(y_dev_main)}")
    print(f"True Positives  : {tp}")
    print(f"False Positives : {fp}")
    print(f"True Negatives  : {tn}")
    print(f"False Negatives : {fn}")
    print(f"Accuracy        : {accuracy * 100:.2f}%")
    print(f"Precision       : {precision * 100:.2f}%")
    print(f"Recall          : {recall * 100:.2f}%")
    print(f"False Pos. Rate : {fpr * 100:.2f}%")

    # Record hash in a config file or pin file
    hash_file = models_dir / "t2.sha256"
    hash_file.write_text(main_sha256, encoding="utf-8")
    print(f"Saved SHA-256 to {hash_file}")

if __name__ == "__main__":
    train_and_export()
