"""Extract traceable PDF pages and export the selected lab corpus as JSONL."""
import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import re
import unicodedata

from pypdf import PdfReader

from .models import DocumentPage
from .sections import annotate_sections, section_records


LOGGER = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CORPUS = (
    {
        "document_id": "gs_driving_review",
        "filename": "s10462-024-10955-4.pdf",
        "first_page": 2,
        "last_page": 26,
        "title": "Scene reconstruction techniques for autonomous driving: "
                 "a review of 3D Gaussian splatting",
    },
    {
        "document_id": "gs_general_survey",
        "filename": "2401.03890v9.pdf",
        "first_page": 2,
        "last_page": 22,
        "title": "A Survey on 3D Gaussian Splatting",
    },
)


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Read all physical pages, numbered from one, without silently dropping any.

    Blank or failed pages remain in the result with an explicit status and a log
    entry. File-level failures propagate to the caller. No OCR is performed.
    """
    pages = []
    with Path(path).open("rb") as handle:
        reader = PdfReader(handle)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError(f"Password required for PDF: {path}")

        for page_number, pdf_page in enumerate(reader.pages, start=1):
            metadata = {}
            try:
                text = normalize_text(pdf_page.extract_text() or "")
                metadata["extraction_status"] = "ok" if text else "empty"
                if not text:
                    LOGGER.warning("Empty text: document=%s page=%d source=%s",
                                   document_id, page_number, source)
            except Exception as error:
                text = ""
                metadata["extraction_status"] = "error"
                metadata["extraction_error"] = f"{type(error).__name__}: {error}"
                LOGGER.exception("Extraction failed: document=%s page=%d source=%s",
                                 document_id, page_number, source)

            pages.append(DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                text=text,
                metadata=metadata,
            ))

    LOGGER.info("Read document=%s physical_pages=%d", document_id, len(pages))
    return pages


def normalize_text(text: str) -> str:
    """Use NFC and normalize spacing while retaining lines and paragraph breaks.

    Do not flatten paragraphs, guess headings, join hyphenated words, or remove
    headers/formulas: those edits can change evidence or discard real content.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = text.replace("\u2028", "\n").replace("\u2029", "\n\n")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = "".join(character for character in text
                   if character in "\n\t" or unicodedata.category(character) != "Cc")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def export_corpus(data_dir: Path) -> Path:
    """Export selected physical page ranges without replacing output on failure.

    Extraction counts do not replace a manual audit of useful content.
    """
    section_config = json.loads((data_dir / "section_boundaries.json").read_text(encoding="utf-8"))
    selected_pages = []
    for spec in CORPUS:
        source = f"data/raw/{spec['filename']}"
        pages = load_pdf(data_dir / "raw" / spec["filename"],
                         spec["document_id"], source)
        first_page, last_page = spec["first_page"], spec["last_page"]
        if len(pages) < last_page:
            raise ValueError(f"{source}: requested page {last_page}, "
                             f"but PDF has only {len(pages)} pages")

        selected = pages[first_page - 1:last_page]
        for page in selected:
            if page.metadata["extraction_status"] != "ok":
                raise ValueError(f"Selected page needs review: {source}, page {page.page}")
            page.metadata.update({
                "title": spec["title"],
                "language": "en",
                "char_count": len(page.text),
            })
        annotate_sections(selected, section_config["documents"][spec["document_id"]])
        selected_pages.extend(selected)
        LOGGER.info("Selected document=%s range=%d-%d pages=%d characters=%d",
                    spec["document_id"], first_page, last_page, len(selected),
                    sum(len(page.text) for page in selected))

    output = data_dir / "processed" / "pages.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output, [asdict(page) for page in selected_pages])
    sections_output = output.with_name("sections.jsonl")
    records = section_records(selected_pages)
    _write_jsonl(sections_output, records)
    LOGGER.info("Exported pages=%d section_segments=%d output=%s",
                len(selected_pages), len(records), output)
    return output


def _write_jsonl(output: Path, records: list[dict]) -> None:
    temporary = output.with_suffix(".jsonl.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Directory containing raw/; default: repository data/")
    args = parser.parse_args()
    processed = args.data_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(processed / "ingestion.log", encoding="utf-8")],
    )
    try:
        export_corpus(args.data_dir)
    except Exception:
        LOGGER.exception("Ingestion failed; pages.jsonl was not replaced")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
