"""Build and audit A/B/C chunks without running embeddings or retrieval."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from src.chunking import by_paragraph, fixed_size  # noqa: E402
from src.models import DocumentPage  # noqa: E402


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_inputs():
    lock = json.loads((ROOT / "benchmark/lock.json").read_text(encoding="utf-8"))
    for relative, expected in lock["sha256"].items():
        if sha256(ROOT / relative) != expected:
            raise ValueError(f"Frozen input changed: {relative}")


def audit(chunks, pages):
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("Duplicate chunk IDs")
    lookup = {(p.document_id, p.page): p for p in pages}
    coverage = {key: bytearray(len(p.text)) for key, p in lookup.items()}
    for chunk in chunks:
        page = lookup[chunk.document_id, chunk.page]
        start, end = chunk.metadata["page_char_start"], chunk.metadata["page_char_end"]
        if not 0 <= start < end <= len(page.text) or chunk.text != page.text[start:end]:
            raise ValueError(f"Chunk text/offset mismatch: {chunk.chunk_id}")
        if chunk.source != page.source or not chunk.text.strip():
            raise ValueError("Incorrect source or empty chunk")
        if len(chunk.text) > chunk.metadata["chunk_size"]:
            raise ValueError("Chunk exceeds configured maximum")
        if not any(s["start"] <= start and end <= s["end"] and
                   s["section"] == chunk.metadata.get("section")
                   for s in page.metadata["section_spans"]):
            raise ValueError(f"Chunk crosses or mislabels a section: {chunk.chunk_id}")
        coverage[chunk.document_id, chunk.page][start:end] = b"\1" * (end - start)
    missing_chars = missing_content = 0
    for key, page in lookup.items():
        for character, covered in zip(page.text, coverage[key]):
            missing_chars += int(not covered)
            missing_content += int(not covered and not character.isspace())
    if missing_content:
        raise ValueError(f"Lost {missing_content} non-whitespace characters")
    return {"pages_checked": len(pages), "source_characters": sum(len(p.text) for p in pages),
            "missing_characters": missing_chars, "missing_non_whitespace_characters": missing_content,
            "empty_chunks": 0, "duplicate_chunk_ids": 0, "cross_section_chunks": 0}


def main():
    verify_frozen_inputs()
    config_path = ROOT / "configs/strategies.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    page_file = ROOT / "data/processed/pages.jsonl"
    pages = [DocumentPage(**json.loads(line)) for line in page_file.read_text(encoding="utf-8").splitlines()]
    built, stats = {}, {}
    for name, spec in config["strategies"].items():
        started = time.perf_counter()
        reuse = spec.get("reuse_chunks_from")
        if reuse:
            parent = config["strategies"][reuse]
            if any(spec[k] != parent[k] for k in ["chunking", "chunk_size", "overlap"]):
                raise ValueError("Reused strategy has different chunk parameters")
            chunks = built[reuse]
        elif spec["chunking"] == "fixed_size":
            chunks = [chunk for page in pages for chunk in
                      fixed_size(page, spec["chunk_size"], spec["overlap"])]
        elif spec["chunking"] == "by_paragraph":
            if spec["overlap"] != 0:
                raise ValueError("by_paragraph does not use overlap")
            chunks = [chunk for page in pages for chunk in by_paragraph(page, spec["chunk_size"])]
        else:
            raise ValueError(f"Unknown chunking method: {spec['chunking']}")
        elapsed = time.perf_counter() - started
        checks = audit(chunks, pages)
        path = ROOT / f"data/processed/chunks_{name}.jsonl"
        content = "".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks)
        path.write_text(content, encoding="utf-8", newline="\n")
        lengths = sorted(len(c.text) for c in chunks)
        built[name] = chunks
        stats[name] = {
            "chunk_count": len(chunks), "total_chunk_characters": sum(lengths),
            "length_characters": {"min": min(lengths), "max": max(lengths),
                                  "mean": round(statistics.mean(lengths), 3),
                                  "median": statistics.median(lengths),
                                  "p95": lengths[max(0, (95 * len(lengths) + 99) // 100 - 1)]},
            "chunking_seconds": round(elapsed, 6), "timing_scope": "Splitting/reuse only; excludes file IO and audit",
            "chunks_by_document": dict(Counter(c.document_id for c in chunks)),
            "chunks_by_section": dict(Counter(c.metadata["section"] for c in chunks)),
            "split_rule_counts": dict(Counter(rule for c in chunks for rule in c.metadata["split_rules"])),
            "reuse_chunks_from": reuse, "sha256": sha256(path), "audit": checks,
        }
        print(f"{name}: {len(chunks)} chunks; lengths {min(lengths)}-{max(lengths)}; "
              f"missing content={checks['missing_non_whitespace_characters']}; reuse={reuse}")
    if sha256(ROOT / "data/processed/chunks_B.jsonl") != sha256(ROOT / "data/processed/chunks_C.jsonl"):
        raise ValueError("B/C chunks must be byte-identical")
    result = {"status": "pass", "corpus_sha256": sha256(page_file), "config_sha256": sha256(config_path),
              "strategies": stats, "B_C_chunks_identical": True,
              "paragraph_limitations": "Few blank paragraph breaks survive PDF extraction; oversized paragraphs use sentence-boundary heuristics, then hard splits. This does not reconstruct the PDF layout."}
    (ROOT / "results/chunking_stats.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
