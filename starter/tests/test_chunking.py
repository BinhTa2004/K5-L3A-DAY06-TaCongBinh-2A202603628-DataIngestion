"""Check content preservation, traceability, boundaries and deterministic IDs."""
from copy import deepcopy
import unittest

from src.chunking import by_paragraph, fixed_size
from src.models import DocumentPage


def page(text, metadata=None):
    return DocumentPage("doc", "data/raw/example.pdf", 11, text,
                        metadata if metadata is not None else {"section": "Example"})


class ChunkingTests(unittest.TestCase):
    def test_nonoverlap_preserves_every_character(self):
        original = page("Tiếng Việt 🌱.\n\nNext paragraph.  End.")
        for splitter in [lambda p: fixed_size(p, 9, 0), lambda p: by_paragraph(p, 9)]:
            chunks = splitter(original)
            self.assertEqual("".join(c.text for c in chunks), original.text)
            for c in chunks:
                self.assertEqual((c.document_id, c.source, c.page), ("doc", original.source, 11))
                self.assertEqual(c.metadata["section"], "Example")
                self.assertLessEqual(len(c.text), 9)

    def test_overlap_preserves_offsets_and_coverage(self):
        chunks = fixed_size(page("abcdefghi"), 4, 1)
        self.assertEqual([c.text for c in chunks], ["abcd", "defg", "ghi"])
        self.assertEqual([(c.metadata["page_char_start"], c.metadata["page_char_end"])
                          for c in chunks], [(0, 4), (3, 7), (6, 9)])

    def test_sections_never_mix_and_metadata_is_not_mutated(self):
        metadata = {"section_spans": [
            {"start": 0, "end": 5, "section": "First", "section_id": "1"},
            {"start": 5, "end": 10, "section": "Second", "section_id": "2"}],
            "sections": ["First", "Second"]}
        original = page("abcdefghij", metadata)
        before = deepcopy(metadata)
        for chunks in [fixed_size(original, 100, 3), by_paragraph(original, 100)]:
            self.assertEqual([c.text for c in chunks], ["abcde", "fghij"])
            self.assertEqual([c.metadata["section"] for c in chunks], ["First", "Second"])
            self.assertNotIn("section_spans", chunks[0].metadata)
        self.assertEqual(original.metadata, before)

    def test_paragraph_packing_preserves_separators(self):
        chunks = by_paragraph(page("One.\n\nTwo.\n\nThree."), 12)
        self.assertEqual([c.text for c in chunks], ["One.\n\nTwo.\n\n", "Three."])

    def test_oversized_paragraph_uses_sentence_boundaries(self):
        text = "First statement. Second statement. Third statement."
        chunks = by_paragraph(page(text), 20)
        self.assertEqual([c.text.strip() for c in chunks],
                         ["First statement.", "Second statement.", "Third statement."])
        self.assertEqual("".join(c.text for c in chunks), text)
        self.assertTrue(all("sentence_fallback" in c.metadata["split_rules"] for c in chunks))

    def test_oversized_sentence_falls_back_without_loss(self):
        chunks = by_paragraph(page("x" * 27), 10)
        self.assertEqual([len(c.text) for c in chunks], [10, 10, 7])
        self.assertEqual("".join(c.text for c in chunks), "x" * 27)
        self.assertTrue(all("hard_fallback" in c.metadata["split_rules"] for c in chunks))

    def test_bad_parameters_and_empty_input(self):
        for size in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                fixed_size(page("abc"), size, 0)
            with self.assertRaises(ValueError):
                by_paragraph(page("abc"), size)
        for overlap in [-1, 3, True, 0.5]:
            with self.assertRaises(ValueError):
                fixed_size(page("abc"), 3, overlap)
        self.assertEqual(fixed_size(page(" \n\t"), 3, 0), [])
        self.assertEqual(by_paragraph(page(""), 3), [])

    def test_ids_are_stable_and_change_with_content(self):
        original = page("abcdef")
        self.assertEqual(fixed_size(original, 4, 0), fixed_size(original, 4, 0))
        self.assertNotEqual(fixed_size(original, 4, 0)[0].chunk_id,
                            fixed_size(page("xbcdef"), 4, 0)[0].chunk_id)
        self.assertNotEqual(fixed_size(original, 4, 0)[0].chunk_id,
                            by_paragraph(original, 4)[0].chunk_id)

    def test_section_segment_offsets_remain_relative_to_original_page(self):
        segment = page("abcdef", {"section": "Part", "page_char_start": 100,
                                  "page_char_end": 106})
        chunks = fixed_size(segment, 4, 0)
        self.assertEqual([(c.metadata["page_char_start"], c.metadata["page_char_end"])
                          for c in chunks], [(100, 104), (104, 106)])

    def test_invalid_section_partition_is_rejected(self):
        for spans in [[{"start": 1, "end": 6, "section": "Bad"}],
                      [{"start": 0, "end": 3, "section": "Bad"}],
                      [{"start": 0, "end": 6, "section": ""}]]:
            with self.assertRaises(ValueError):
                fixed_size(page("abcdef", {"section_spans": spans}), 4, 0)


if __name__ == "__main__":
    unittest.main()
