"""Encode A/B documents and benchmark question text, without vector search."""
from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from build_chunks import sha256, verify_frozen_inputs  # noqa: E402
from src.embeddings import MyEmbedder  # noqa: E402


def main():
    verify_frozen_inputs()
    import numpy as np

    config_path = ROOT / "configs/embedding.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    strategies = json.loads((ROOT / "configs/strategies.json").read_text(encoding="utf-8"))["strategies"]
    chunk_stats = json.loads((ROOT / "results/chunking_stats.json").read_text(encoding="utf-8"))
    if chunk_stats["config_sha256"] != sha256(ROOT / "configs/strategies.json"):
        raise ValueError("Chunk configuration changed; run build_chunks.py again")
    embedder = MyEmbedder(config["model_name"])
    output = ROOT / "data/processed/embeddings"
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}

    def save_matrix(name, vectors, mapping):
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] != embedder.dimensions:
            raise ValueError("Invalid embedding matrix")
        path = output / f"{name}.npy"
        with path.open("wb") as handle:
            np.save(handle, matrix, allow_pickle=False)
        ids = output / f"{name}_ids.json"
        ids.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"vectors_path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path),
                "ids_path": ids.relative_to(ROOT).as_posix(), "ids_sha256": sha256(ids),
                "shape": list(matrix.shape), "dtype": str(matrix.dtype),
                "all_finite": bool(np.isfinite(matrix).all()),
                "max_norm_error": float(np.max(np.abs(np.linalg.norm(matrix, axis=1) - 1)))}

    for name, spec in strategies.items():
        chunk_file = ROOT / f"data/processed/chunks_{name}.jsonl"
        if sha256(chunk_file) != chunk_stats["strategies"][name]["sha256"]:
            raise ValueError(f"Chunks changed after audit: {name}")
        reuse = spec.get("reuse_document_vectors_from")
        if reuse:
            if sha256(chunk_file) != sha256(ROOT / f"data/processed/chunks_{reuse}.jsonl"):
                raise ValueError("Reusing vectors requires byte-identical chunks and IDs")
            artifacts[name] = {**artifacts[reuse], "reused_from": reuse,
                               "encoding": None, "reference_encoding": artifacts[reuse]["encoding"],
                               "incremental_document_encoding_seconds": 0,
                               "timing_note": "References the already encoded B matrix; not a standalone ingest benchmark"}
            print(f"{name}: reuse {reuse} document vectors", flush=True)
            continue
        chunks = [json.loads(line) for line in chunk_file.read_text(encoding="utf-8").splitlines()]
        print(f"Encoding {name}: {len(chunks)} document chunks", flush=True)
        vectors = embedder.embed_documents([chunk["text"] for chunk in chunks])
        artifacts[name] = {**save_matrix(f"documents_{name}", vectors, [c["chunk_id"] for c in chunks]),
                           "chunks_sha256": sha256(chunk_file), "encoding": dict(embedder.calls[-1])}
        print(f"{name}: shape={artifacts[name]['shape']} seconds={embedder.calls[-1]['seconds']}", flush=True)

    questions, query_sources = [], {}
    for split in ["dev", "test"]:
        source = ROOT / f"benchmark/{split}.json"
        query_sources[split] = sha256(source)
        questions.extend(json.loads(source.read_text(encoding="utf-8")))
    # No expected_answer, evidence, gold source/page, or filter enters the encoder.
    vectors = embedder.embed_queries([q["question"] for q in questions])
    queries = save_matrix("queries", vectors, [{"id": q["id"], "split": q["split"]} for q in questions])
    queries.update({"input_field": "question only", "source_sha256": query_sources,
                    "encoding": dict(embedder.calls[-1]),
                    "note": "Pure query encoding; no retrieval/ranking/evaluation or parameter selection using test results"})
    report = {"status": "pass", "recorded_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
              "python": platform.python_version(), "platform": platform.platform(),
              "config_sha256": sha256(config_path), "corpus_sha256": chunk_stats["corpus_sha256"],
              "chunk_config_sha256": chunk_stats["config_sha256"], "model": embedder.metadata(),
              "documents": artifacts, "queries": queries, "paid_api_cost_usd": 0,
              "cost_scope": config["cost_scope"], "vector_store_created": False,
              "retrieval_executed": False}
    (ROOT / "results/embedding_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_rows = [{"phase": "model_load_and_verify", "strategy": "shared",
                 "inputs": "", "tokens": "", "seconds": report["model"]["load_and_verify_seconds"],
                 "scope": "Shared initialization, file checks and imports; not per-strategy encoding"}]
    for name, artifact in artifacts.items():
        call = artifact.get("encoding")
        log_rows.append({"phase": "document_encoding", "strategy": name,
                         "inputs": artifact["shape"][0], "tokens": call["tokens"] if call else 0,
                         "seconds": call["seconds"] if call else 0,
                         "scope": call["timing_scope"] if call else "Incremental reuse of B vectors; not an independent standalone ingest timing"})
    call = queries["encoding"]
    log_rows.append({"phase": "query_encoding", "strategy": "shared", "inputs": call["inputs"],
                     "tokens": call["tokens"], "seconds": call["seconds"], "scope": call["timing_scope"]})
    log_file = ROOT / "artifacts/embedding_log.csv"
    with log_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["phase", "strategy", "model", "revision",
                                "inputs", "tokens", "seconds", "paid_api_cost_usd", "scope"])
        writer.writeheader()
        for row in log_rows:
            writer.writerow({**row, "model": embedder.model_name, "revision": embedder.revision,
                             "paid_api_cost_usd": 0})
    print(f"PASS: {len(questions)} query vectors, dimensions={embedder.dimensions}; no retrieval executed", flush=True)


if __name__ == "__main__":
    main()
