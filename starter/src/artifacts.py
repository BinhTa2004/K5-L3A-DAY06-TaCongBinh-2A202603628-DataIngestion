"""Validate immutable corpus/benchmark and aligned cached embedding artifacts."""
import hashlib
import json
from pathlib import Path

import numpy as np

from .models import Chunk

ROOT = Path(__file__).resolve().parents[2]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_artifacts():
    lock = read_json(ROOT / "benchmark/lock.json")
    for relative, expected in lock["sha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError(f"Frozen corpus/benchmark changed: {relative}")
    manifest = read_json(ROOT / "data/manifest.json")
    if manifest["content_page_count"] < 30:
        raise ValueError("Corpus has fewer than 30 content pages")
    model = read_json(ROOT / "configs/embedding.json")
    strategies = read_json(ROOT / "configs/strategies.json")["strategies"]
    run = read_json(ROOT / "results/embedding_run.json")
    if digest(ROOT / "configs/embedding.json") != run["config_sha256"]:
        raise ValueError("Embedding configuration changed; rebuild embeddings")
    if digest(ROOT / "configs/strategies.json") != run["chunk_config_sha256"]:
        raise ValueError("Chunk configuration changed; rebuild chunks and embeddings")
    if run["corpus_sha256"] != digest(ROOT / "data/processed/pages.jsonl"):
        raise ValueError("Embedding corpus hash mismatch")

    def matrix(entry):
        for path_key, hash_key in [("vectors_path", "sha256"), ("ids_path", "ids_sha256")]:
            if digest(ROOT / entry[path_key]) != entry[hash_key]:
                raise ValueError(f"Embedding artifact changed: {entry[path_key]}")
        array = np.load(ROOT / entry["vectors_path"], allow_pickle=False)
        if array.ndim != 2 or array.shape[1] != model["dimensions"] or list(array.shape) != entry["shape"]:
            raise ValueError("Embedding array dimensions do not match metadata")
        if not np.isfinite(array).all() or not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-5):
            raise ValueError("Invalid cached embedding values")
        return array

    chunks, vectors, snapshots = {}, {}, {}
    for name in strategies:
        path = ROOT / f"data/processed/chunks_{name}.jsonl"
        entry = run["documents"][name]
        if digest(path) != entry["chunks_sha256"]:
            raise ValueError(f"Chunks/vectors snapshot mismatch: {name}")
        chunks[name] = [Chunk(**row) for row in read_jsonl(path)]
        ids = read_json(ROOT / entry["ids_path"])
        if ids != [chunk.chunk_id for chunk in chunks[name]]:
            raise ValueError("Embedding rows do not align with chunk IDs")
        vectors[name] = matrix(entry)
        snapshots[name] = {"model_name": model["model_name"], "revision": model["revision"],
                           "dimensions": model["dimensions"], "embedding_config_sha256": run["config_sha256"],
                           "chunks_sha256": digest(path), "vectors_sha256": entry["sha256"], "count": len(ids)}
    if chunks["B"] != chunks["C"] or not np.array_equal(vectors["B"], vectors["C"]):
        raise ValueError("B and C must share identical chunks and vectors")
    questions = {split: read_json(ROOT / f"benchmark/{split}.json") for split in ["dev", "test"]}
    query_entry = run["queries"]
    for split in questions:
        if digest(ROOT / f"benchmark/{split}.json") != query_entry["source_sha256"][split]:
            raise ValueError("Questions changed after query encoding")
    all_questions = questions["dev"] + questions["test"]
    expected_ids = [{"id": q["id"], "split": q["split"]} for q in all_questions]
    if read_json(ROOT / query_entry["ids_path"]) != expected_ids:
        raise ValueError("Cached query vectors have different ID/split order")
    queries = matrix(query_entry)
    fingerprint_inputs = {"frozen": lock["sha256"], "chunks": snapshots,
                          "strategies_config": digest(ROOT / "configs/strategies.json"),
                          "queries": query_entry["sha256"],
                          "store_implementation": digest(Path(__file__).with_name("store.py")),
                          "evaluation_implementation": digest(Path(__file__).with_name("evaluation.py")),
                          "orchestration_implementation": digest(Path(__file__).with_name("run.py")),
                          "artifact_validation_implementation": digest(Path(__file__))}
    fingerprint = hashlib.sha256(json.dumps(fingerprint_inputs, sort_keys=True).encode()).hexdigest()
    for snapshot in snapshots.values():
        snapshot["experiment_fingerprint"] = fingerprint
    return {"model": model, "strategies": strategies, "chunks": chunks, "vectors": vectors,
            "snapshots": snapshots, "questions": questions, "embedding_run": run,
            "query_vectors": {q["id"]: row for q, row in zip(all_questions, queries)},
            "fingerprint": fingerprint, "manifest": manifest}
