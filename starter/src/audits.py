"""Prepare source-based review samples and aggregate only explicitly entered labels."""
from collections import Counter
import csv

from .artifacts import ROOT, read_json, read_jsonl, write_json

AUDIT_DIR = ROOT / "results/audit"


def ensure_anchors(context):
    pages = read_jsonl(ROOT / "data/processed/pages.jsonl")
    anchors = []
    for document_id in sorted({page["document_id"] for page in pages}):
        for page in sorted([p for p in pages if p["document_id"] == document_id], key=lambda p: p["page"])[:5]:
            anchors.append({"document_id": document_id, "page": page["page"],
                            "page_char_offset": len(page["text"]) // 2})
    value = {"selection_rule": "First five physical pages per document, sorted; midpoint character. Chosen before retrieval scores.",
             "anchors": anchors}
    path = AUDIT_DIR / "anchors.json"
    if path.exists() and read_json(path) != value:
        raise ValueError("Existing coherence sample differs; retain review provenance")
    write_json(path, value)
    return anchors


def _template(path, rows):
    if path.exists():
        return  # Preserve entered labels/reviewer notes on repeated runs.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare_audits(context, test_traces):
    anchors = ensure_anchors(context)
    state_path = AUDIT_DIR / "snapshot.json"
    if state_path.exists() and read_json(state_path)["fingerprint"] != context["fingerprint"]:
        raise ValueError("Audit samples belong to a different experiment; archive them before creating new samples")
    coherence, metadata, grounding = [], [], []
    for strategy, chunks in context["chunks"].items():
        for i, anchor in enumerate(anchors, 1):
            matches = [c for c in chunks if c.document_id == anchor["document_id"] and c.page == anchor["page"]
                       and c.metadata["page_char_start"] <= anchor["page_char_offset"] < c.metadata["page_char_end"]]
            if not matches:
                raise ValueError("No chunk covers a coherence anchor")
            for chunk in matches:
                coherence.append({"strategy": strategy, "anchor_id": i, **anchor,
                                  "chunk_id": chunk.chunk_id, "section": chunk.metadata["section"],
                                  "chunk_text": chunk.text, "score_0_1_2": "", "reason": "", "reviewer": ""})
    for trace in test_traces:
        grounding.append({"strategy": trace["strategy"], "question_id": trace["id"],
                          "question": trace["question"], "expected_answer": trace["expected_answer"],
                          "top3_chunk_ids": " | ".join(hit["chunk_id"] for hit in trace["hits"]),
                          "top3_text": "\n\n---\n\n".join(hit["text"] for hit in trace["hits"]),
                          "score_0_1_2": "", "reason": "", "reviewer": ""})
        for hit in trace["hits"]:
            metadata.append({"strategy": trace["strategy"], "question_id": trace["id"],
                             "rank": hit["rank"], "chunk_id": hit["chunk_id"],
                             "document_id": hit["document_id"], "source": hit["source"], "page": hit["page"],
                             "section": hit["metadata"].get("section", ""),
                             "page_char_start": hit["metadata"].get("page_char_start", ""),
                             "page_char_end": hit["metadata"].get("page_char_end", ""),
                             "metadata_complete_and_correct_0_1": "", "reason": "", "reviewer": ""})
    for name, rows in [("coherence.csv", coherence), ("metadata.csv", metadata), ("grounding.csv", grounding)]:
        _template(AUDIT_DIR / name, rows)
    write_json(state_path, {"fingerprint": context["fingerprint"], "expected_rows": {
        "coherence": len(coherence), "metadata": len(metadata), "grounding": len(grounding)}})
    return summarize_audits(context)


def summarize_audits(context):
    state = read_json(AUDIT_DIR / "snapshot.json")
    if state["fingerprint"] != context["fingerprint"]:
        raise ValueError("Audit snapshot mismatch")
    output = {"fingerprint": context["fingerprint"], "manual_review_complete": True, "audits": {}}
    for name, field, allowed in [("coherence", "score_0_1_2", {"0", "1", "2"}),
                                 ("metadata", "metadata_complete_and_correct_0_1", {"0", "1"}),
                                 ("grounding", "score_0_1_2", {"0", "1", "2"})]:
        with (AUDIT_DIR / f"{name}.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != state["expected_rows"][name]:
            raise ValueError(f"Review sample count changed: {name}")
        for row in rows:
            if row[field] and row[field] not in allowed:
                raise ValueError(f"Invalid {name} label: {row[field]}")
            if row[field] and (not row["reviewer"].strip() or not row["reason"].strip()):
                raise ValueError("Entered quality labels require a reason and reviewer")
        by_strategy = {}
        for strategy in context["strategies"]:
            subset = [row for row in rows if row["strategy"] == strategy]
            labeled = [row for row in subset if row[field] in allowed]
            complete = len(labeled) == len(subset) and bool(subset)
            by_strategy[strategy] = {"labeled": len(labeled), "sample_size": len(subset),
                                     "complete": complete,
                                     "mean": sum(int(row[field]) for row in labeled) / len(labeled) if complete else None,
                                     "label_counts": dict(Counter(row[field] for row in labeled)) if complete else None}
            if not complete:
                output["manual_review_complete"] = False
        output["audits"][name] = by_strategy
    write_json(ROOT / "results/quality_metrics.json", output)
    return output
