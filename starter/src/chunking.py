"""Lossless character ranges for fixed-size and paragraph-aware chunking."""
from copy import deepcopy
import hashlib
import json
import re

from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split each source section independently; retain exact page offsets.

    Size and overlap are Unicode character counts, not tokens. Whitespace-only
    windows are omitted; no non-whitespace content is discarded.
    """
    _positive_integer(size, "size")
    if type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError("overlap must be an integer satisfying 0 <= overlap < size")
    chunks = []
    for start, end, section in _regions(page):
        cursor = start
        while cursor < end:
            stop = min(cursor + size, end)
            if page.text[cursor:stop].strip():
                chunks.append(_chunk(page, cursor, stop, section, "fixed_size",
                                     size, overlap, ["fixed_window"]))
            if stop == end:
                break
            cursor = stop - overlap
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Greedily pack paragraphs without crossing page or section boundaries.

    Blank lines delimit paragraphs. PDF extraction often has no blank lines;
    oversized paragraphs therefore fall back to sentence boundaries, then hard
    character windows for oversized sentences. Original text is never joined or
    rewritten, including its separator whitespace. There is no overlap.
    """
    _positive_integer(max_size, "max_size")
    chunks = []
    for start, end, section in _regions(page):
        units = []
        for a, b in _split_at(page.text, start, end, r"\n[ \t]*\n+"):
            if b - a <= max_size:
                units.append((a, b, "paragraph"))
                continue
            for c, d in _split_at(page.text, a, b, r"(?<=[.!?])\s+(?=[A-Z\u00c0-\u024f\u1e00-\u1eff\u201c\"(])"):
                if d - c <= max_size:
                    units.append((c, d, "sentence_fallback"))
                else:
                    units.extend((offset, min(offset + max_size, d), "hard_fallback")
                                 for offset in range(c, d, max_size))

        pending_start = pending_end = None
        rules = set()
        for a, b, rule in units:
            if pending_start is not None and b - pending_start > max_size:
                if page.text[pending_start:pending_end].strip():
                    chunks.append(_chunk(page, pending_start, pending_end, section,
                                         "by_paragraph", max_size, 0, sorted(rules)))
                pending_start = None
                rules = set()
            if pending_start is None:
                pending_start = a
            pending_end = b
            rules.add(rule)
        if pending_start is not None and page.text[pending_start:pending_end].strip():
            chunks.append(_chunk(page, pending_start, pending_end, section,
                                 "by_paragraph", max_size, 0, sorted(rules)))
    return chunks


def _positive_integer(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _regions(page: DocumentPage) -> list[tuple[int, int, dict]]:
    if not page.text.strip():
        return []
    spans = page.metadata.get("section_spans")
    if spans is None:
        if len(page.metadata.get("sections", [])) > 1:
            raise ValueError("A mixed-section page requires section_spans")
        return [(0, len(page.text), {key: page.metadata[key] for key in
                                    ["section", "section_id", "heading_page"]
                                    if key in page.metadata})]
    regions = []
    cursor = 0
    for span in spans:
        a, b = span["start"], span["end"]
        if type(a) is not int or type(b) is not int or a != cursor or not a < b <= len(page.text):
            raise ValueError("section_spans must partition the complete page without gaps or overlaps")
        if not isinstance(span.get("section"), str) or not span["section"].strip():
            raise ValueError("Each section span needs a nonempty source section")
        regions.append((a, b, {key: span[key] for key in
                               ["section", "section_id", "heading_page"] if key in span}))
        cursor = b
    if cursor != len(page.text):
        raise ValueError("section_spans do not cover the entire page")
    return regions


def _split_at(text: str, start: int, end: int, pattern: str) -> list[tuple[int, int]]:
    """Assign separator characters to the preceding unit, keeping all offsets."""
    spans = []
    cursor = start
    for match in re.finditer(pattern, text[start:end]):
        boundary = start + match.end()
        if boundary > cursor:
            spans.append((cursor, boundary))
            cursor = boundary
    if cursor < end:
        spans.append((cursor, end))
    return spans


def _chunk(page: DocumentPage, start: int, end: int, section: dict,
           method: str, size: int, overlap: int, rules: list[str]) -> Chunk:
    text = page.text[start:end]
    base = page.metadata.get("page_char_start", 0)
    metadata = deepcopy({key: value for key, value in page.metadata.items()
                         if key not in {"section_spans", "sections"}})
    metadata.update(section)
    metadata.update({"page_char_start": base + start, "page_char_end": base + end,
                     "char_count": len(text), "chunking_method": method,
                     "chunk_size": size, "overlap": overlap, "split_rules": rules})
    identity = {"document_id": page.document_id, "source": page.source, "page": page.page,
                "start": base + start, "end": base + end, "text": text,
                "section": metadata.get("section"), "method": method,
                "size": size, "overlap": overlap}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    return Chunk(chunk_id=f"{page.document_id}:p{page.page}:{method}:{digest}",
                 document_id=page.document_id, source=page.source, page=page.page,
                 text=text, metadata=metadata)
