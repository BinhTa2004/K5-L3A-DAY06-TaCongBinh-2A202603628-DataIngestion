"""Evidence-based retrieval metrics; never infer human quality labels."""
from collections import defaultdict
import re
from typing import Any
import unicodedata


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Accept any complete documented gold passage in one source/page chunk.

    This conservative automatic check uses full normalized quote containment.
    It is not an LLM-answer grade, human grounding label or a union of chunks.
    Additional equivalent passages can be documented in gold_evidence; they
    must be verified against the corpus before evaluation.
    """
    gold = question.get("gold_evidence") or [{key: question[key] for key in
                                            ["gold_source_id", "gold_page", "evidence_quote"]}]
    if not gold or any(not entry["evidence_quote"].strip() for entry in gold):
        raise ValueError("Every question requires nonempty verified gold evidence")
    evaluated = []
    for rank, hit in enumerate(hits[:3], start=1):
        metadata = hit.get("metadata", {})
        document_id = hit.get("document_id", metadata.get("document_id"))
        page = hit.get("page", metadata.get("page"))
        text = _normalize(hit["text"])
        matches = [i for i, evidence in enumerate(gold)
                   if document_id == evidence["gold_source_id"] and page == evidence["gold_page"]
                   and _normalize(evidence["evidence_quote"]) in text]
        same_page = any(document_id == e["gold_source_id"] and page == e["gold_page"] for e in gold)
        evaluated.append({**hit, "rank": rank, "gold_source_page_match": same_page,
                          "evidence_hit": bool(matches), "matched_gold_indices": matches})
    requested = question.get("filter") or {}
    compliant = None
    if requested:
        compliant = bool(evaluated) and all(
            all(hit.get("metadata", {}).get(key) == value for key, value in requested.items())
            for hit in evaluated)
    return {"id": question["id"], "split": question["split"],
            "question": question["question"], "expected_answer": question["expected_answer"],
            "gold_evidence": gold, "requested_filter": requested,
            "hits": evaluated, "hit_at_1": bool(evaluated and evaluated[0]["evidence_hit"]),
            "evidence_hit_at_3": any(hit["evidence_hit"] for hit in evaluated),
            "requested_filter_compliant": compliant,
            "evaluation_method": "Full documented evidence containment on correct source/page after NFC/whitespace normalization; conservative automatic evidence metric"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    groups = defaultdict(list)
    seen = set()
    for trace in traces:
        key = (trace["strategy"], trace["split"], trace["id"])
        if key in seen:
            raise ValueError(f"Duplicate evaluation trace: {key}")
        seen.add(key)
        groups[key[:2]].append(trace)
    rows = []
    for (strategy, split), cases in sorted(groups.items()):
        total = len(cases)
        n1 = sum(bool(case["hit_at_1"]) for case in cases)
        n3 = sum(bool(case["evidence_hit_at_3"]) for case in cases)
        filtered = [case for case in cases if case["requested_filter"]]
        rows.append({"strategy": strategy, "split": split, "questions": total,
                     "hit_at_1_n": n1, "hit_at_1": n1 / total, "hit_at_1_fraction": f"{n1}/{total}",
                     "evidence_hit_at_3_n": n3, "evidence_hit_at_3": n3 / total,
                     "evidence_hit_at_3_fraction": f"{n3}/{total}",
                     "filter_questions": len(filtered),
                     "filter_compliant_questions": sum(bool(case["requested_filter_compliant"]) for case in filtered),
                     "filter_compliance": (sum(bool(case["requested_filter_compliant"]) for case in filtered) / len(filtered)
                                           if filtered else None),
                     "search_seconds": sum(case.get("search_seconds", 0) for case in cases)})
    return {"rows": rows, "quality_labels": "Coherence/metadata correctness/grounding require separate manual audits"}
