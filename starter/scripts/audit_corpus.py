"""Verify the 46-page extraction and generate its manifest and machine audit."""
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pypdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from src.ingestion import CORPUS, normalize_text  # noqa: E402


SOURCES = {
    "gs_driving_review": {
        "authors": ["Huixin Zhu", "Zhili Zhang", "Junyang Zhao", "Hui Duan",
                    "Yao Ding", "Xiongwu Xiao", "Junsong Yuan"],
        "source_url": "https://doi.org/10.1007/s10462-024-10955-4",
        "metadata_verification_url": "https://link.springer.com/article/10.1007/s10462-024-10955-4",
        "version": "Publisher version of record; Artificial Intelligence Review 58, article 30 (2025)",
        "published_online": "2024-11-30",
        "license_or_permission": "CC BY-NC-ND 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
        "license_evidence": "Local PDF physical page 27, Open Access notice; publisher Rights and permissions.",
        "excluded_parts": [
            {"pages": [1], "reason": "Title/author/abstract/affiliation page deliberately outside the chosen snapshot."},
            {"pages": [27], "reason": "Conclusion continuation, declarations, license and figure deliberately excluded."},
            {"pages": list(range(28, 34)), "reason": "Reference-only pages; not counted as content."},
        ],
    },
    "gs_general_survey": {
        "authors": ["Guikun Chen", "Wenguan Wang"],
        "source_url": "https://arxiv.org/abs/2401.03890v9",
        "download_url": "https://arxiv.org/pdf/2401.03890v9",
        "metadata_verification_url": "https://arxiv.org/abs/2401.03890v9",
        "version": "arXiv:2401.03890v9",
        "version_date": "2026-04-09",
        "license_or_permission": "CC BY 4.0 (arXiv license link and embedded PDF /License metadata)",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_evidence": "Version-specific arXiv record, view license; local PDF /License metadata.",
        "license_notes": "The PDF also contains an ACM template permission notice on page 1; both observations are retained rather than treating it as an unconditional rights clearance.",
        "excluded_parts": [
            {"pages": [1], "reason": "Title/author/abstract/permission and initial introduction page deliberately excluded."},
            {"pages": [23], "reason": "Mixed final research discussion/conclusion and start of references deliberately excluded."},
            {"pages": list(range(24, 37)), "reason": "Reference-only pages; not counted as content."},
            {"pages": list(range(37, 42)), "reason": "Supplementary figures/tables deliberately outside this snapshot."},
        ],
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    data = ROOT / "data"
    pages_path = data / "processed/pages.jsonl"
    sections_path = data / "processed/sections.jsonl"
    rows = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    sections = [json.loads(line) for line in sections_path.read_text(encoding="utf-8").splitlines()]
    manifest_path = data / "manifest.json"
    previous_documents = {}
    if manifest_path.exists():
        previous_documents = {doc["document_id"]: doc for doc in
                              json.loads(manifest_path.read_text(encoding="utf-8"))["documents"]}
    require(len(rows) == 46, "Expected exactly 46 page records")
    require(len({(r["document_id"], r["page"]) for r in rows}) == 46, "Duplicate page IDs")
    with (ROOT / "results/text_audit.csv").open(encoding="utf-8", newline="") as handle:
        visual_audit = list(csv.DictReader(handle))
    require(len(visual_audit) == 8, "Expected eight recorded visual samples")
    for sample in visual_audit:
        require((ROOT / sample["preview"]).is_file(), "Missing visual audit preview")

    docs = []
    checked_pages = []
    for spec in CORPUS:
        document_id = spec["document_id"]
        raw = data / "raw" / spec["filename"]
        reader = pypdf.PdfReader(raw)
        selected = [r for r in rows if r["document_id"] == document_id]
        expected_pages = list(range(spec["first_page"], spec["last_page"] + 1))
        require([r["page"] for r in selected] == expected_pages, "Wrong physical page selection")
        for row in selected:
            text = row["text"]
            require(bool(text.strip()), f"Empty selected page: {document_id}:{row['page']}")
            require(row["metadata"]["extraction_status"] == "ok", "Failed extraction status")
            require(row["source"] == f"data/raw/{spec['filename']}", "Incorrect source path")
            require(len(text) == row["metadata"]["char_count"], "Incorrect character count")
            actual = normalize_text(reader.pages[row["page"] - 1].extract_text() or "")
            require(text == actual, f"Text/page mismatch: {document_id}:{row['page']}")
            spans = row["metadata"]["section_spans"]
            require(spans[0]["start"] == 0 and spans[-1]["end"] == len(text), "Incomplete spans")
            cursor = 0
            for span in spans:
                require(span["start"] == cursor and span["end"] > cursor, "Invalid span partition")
                matches = [s for s in sections if s["document_id"] == document_id
                           and s["page"] == row["page"]
                           and s["metadata"]["page_char_start"] == span["start"]]
                require(len(matches) == 1, "Missing or duplicate section segment")
                segment = matches[0]
                require(segment["text"] == text[span["start"]:span["end"]], "Changed section text")
                require(segment["metadata"]["section"] == span["section"], "Wrong section label")
                require(segment["metadata"]["char_count"] == len(segment["text"]), "Wrong segment length")
                cursor = span["end"]
            checked_pages.append({"document_id": document_id, "page": row["page"],
                                  "char_count": len(text), "text_matches_pdf": True,
                                  "extraction_status": "ok", "section_spans_valid": True})

        info = dict(SOURCES[document_id])
        info.update({
            "source_id": document_id, "document_id": document_id, "title": spec["title"],
            "source_path": raw.relative_to(ROOT).as_posix(), "pdf_sha256": digest(raw),
            "physical_page_count": len(reader.pages), "selected_pages": expected_pages,
            "content_page_count": len(selected),
            "page_char_counts": [{"page": r["page"], "char_count": len(r["text"]),
                                   "text_sha256": hashlib.sha256(r["text"].encode("utf-8")).hexdigest()}
                                  for r in selected],
            "total_characters": sum(len(r["text"]) for r in selected),
            "original_downloaded_at": None,
            "accessed_at": datetime.now(timezone(timedelta(hours=7))).date().isoformat(),
            "access_method": "Inspection of user-provided local PDF; not its original download date.",
            "source_web_verified_at": "2026-11-13",
            "how_to_obtain": "Obtain the indicated version from source_url/download_url and place the original PDF at source_path; compare pdf_sha256 to detect a different binary.",
        })
        previous = previous_documents.get(document_id, {})
        if previous.get("pdf_sha256") == info["pdf_sha256"]:
            # Preserve the recorded first inspection date when re-verifying later.
            info["accessed_at"] = previous["accessed_at"]
        docs.append(info)

    checks = {
        "status": "pass", "page_records": len(rows), "section_segments": len(sections),
        "document_counts": dict(Counter(r["document_id"] for r in rows)),
        "empty_pages": [], "failed_pages": [], "duplicate_pages": [],
        "all_page_text_matches_normalized_physical_pdf_pages": True,
        "visual_sample_count": len(visual_audit),
        "visual_review_by": "Codex AI assistant; student sign-off has not been claimed",
        "visual_audit": "results/text_audit.csv", "pages": checked_pages,
    }
    write_json(ROOT / "results/corpus_checks.json", checks)
    manifest = {
        "schema_version": 1, "corpus_version": "gs-papers-v1",
        "topic": "3D Gaussian Splatting: principles, improvements and applications",
        "page_numbering": "One-based physical PDF page numbers; never renumbered after selection.",
        "page_counting_rule": "Count each selected physical page once when it contains substantive topic-related prose, equations, figures or tables. No duplicate padding. Exclude reference-only/title-only/blank pages and the explicitly listed out-of-scope pages. Character count is an audit field, not a minimum PDF-page threshold.",
        "content_page_count": len(rows), "total_characters": sum(len(r["text"]) for r in rows),
        "normalization": "pypdf extraction followed by NFC, normalized whitespace and preserved line/paragraph breaks; no OCR, header/footer deletion, formula reconstruction or automatic dehyphenation.",
        "pypdf_version": pypdf.__version__,
        "pages_path": "data/processed/pages.jsonl", "pages_sha256": digest(pages_path),
        "sections_path": "data/processed/sections.jsonl", "sections_sha256": digest(sections_path),
        "section_boundaries_path": "data/section_boundaries.json",
        "section_boundaries_sha256": digest(data / "section_boundaries.json"),
        "machine_audit": "results/corpus_checks.json", "visual_audit": "results/text_audit.csv",
        "quality_limits": ["Only eight representative pages were inspected visually; all 46 were checked mechanically against PDF extraction.",
                           "Tables/figures/formulas lose two-dimensional layout; running headers/footers and line-end hyphenation remain.",
                           "Some selected pages start/end mid-paragraph or mid-section; benchmark evidence must be self-contained.",
                           "Artifacts are prepared locally; this manifest does not assert blanket permission to publish adapted text, excerpts or third-party images."],
        "documents": docs,
    }
    write_json(data / "manifest.json", manifest)
    print(f"PASS: {len(rows)} pages, {len(sections)} section segments, {len(visual_audit)} visual samples")
    print("Wrote data/manifest.json and results/corpus_checks.json")


if __name__ == "__main__":
    main()
