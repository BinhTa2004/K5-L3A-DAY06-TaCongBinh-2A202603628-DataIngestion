"""Attach source-heading intervals without inventing one section for a mixed page."""
from typing import Any

from .models import DocumentPage


def annotate_sections(pages: list[DocumentPage], config: dict[str, Any]) -> None:
    """Mutate metadata only; start/end offsets index the unchanged page text."""
    page_map = {page.page: page for page in pages}
    by_page: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for heading in config["headings"]:
        page = page_map[heading["page"]]
        marker = heading["heading"]
        start = page.text.find(marker)
        if start < 0 or page.text.find(marker, start + len(marker)) >= 0:
            raise ValueError(f"Heading must occur exactly once: {page.document_id}, "
                             f"page {page.page}, {marker!r}")
        if start and page.text[start - 1] != "\n":
            raise ValueError(f"Heading is not at a line start: {marker!r}")
        by_page.setdefault(page.page, []).append((start, heading))

    current = config["initial_section"]
    for page in pages:
        spans = []
        cursor = 0
        for offset, heading in sorted(by_page.get(page.page, []), key=lambda item: item[0]):
            if (heading["section_id"], heading["section"]) == (
                    current["section_id"], current["section"]):
                continue
            if offset > cursor:
                spans.append(_span(cursor, offset, current))
            cursor = offset
            current = heading
        if cursor < len(page.text):
            spans.append(_span(cursor, len(page.text), current))
        page.metadata["section_spans"] = spans
        page.metadata["sections"] = list(dict.fromkeys(span["section"] for span in spans))
        if len(page.metadata["sections"]) == 1:
            page.metadata["section"] = spans[0]["section"]
            page.metadata["section_id"] = spans[0]["section_id"]


def _span(start: int, end: int, heading: dict[str, Any]) -> dict[str, Any]:
    return {"start": start, "end": end, "section_id": heading["section_id"],
            "section": heading["section"],
            "heading_page": heading.get("heading_page", heading.get("page"))}


def section_records(pages: list[DocumentPage]) -> list[dict[str, Any]]:
    """Produce section-bounded input for future chunking; not retrieval chunks."""
    records = []
    for page in pages:
        for span in page.metadata["section_spans"]:
            text = page.text[span["start"]:span["end"]]
            metadata = {key: value for key, value in page.metadata.items()
                        if key not in {"section_spans", "sections", "section", "section_id"}}
            metadata.update({"section": span["section"], "section_id": span["section_id"],
                             "heading_page": span["heading_page"],
                             "page_char_start": span["start"], "page_char_end": span["end"],
                             "char_count": len(text)})
            records.append({"document_id": page.document_id, "source": page.source,
                            "page": page.page, "text": text, "metadata": metadata})
    return records
