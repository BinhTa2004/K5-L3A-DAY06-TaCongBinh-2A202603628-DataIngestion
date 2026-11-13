import unittest

from src.evaluation import evaluate_query, summarize


def question():
    return {"id": "dev01", "split": "dev", "question": "What?", "expected_answer": "answer",
            "gold_source_id": "doc", "gold_page": 11, "evidence_quote": "complete evidence",
            "gold_evidence": [{"gold_source_id": "doc", "gold_page": 11, "evidence_quote": "complete evidence"},
                              {"gold_source_id": "alternative", "gold_page": 4, "evidence_quote": "other proof"}],
            "filter": {"section": "Section"}}


def hit(document="doc", page=11, text="Some complete evidence here", section="Section"):
    return {"chunk_id": "chunk", "document_id": document, "page": page,
            "text": text, "metadata": {"section": section}}


class EvaluationTests(unittest.TestCase):
    def test_requires_source_page_and_complete_evidence(self):
        for candidate in [hit(document="wrong"), hit(page=12), hit(text="complete")]:
            self.assertFalse(evaluate_query(question(), [candidate])["evidence_hit_at_3"])
        self.assertTrue(evaluate_query(question(), [hit()])["hit_at_1"])

    def test_accepts_alternative_and_whitespace_normalization(self):
        case = evaluate_query(question(), [hit("alternative", 4, "prefix other\n proof suffix")])
        self.assertTrue(case["hit_at_1"])
        self.assertEqual(case["hits"][0]["matched_gold_indices"], [1])

    def test_top1_and_top3_are_distinct(self):
        case = evaluate_query(question(), [hit(text="unrelated"), hit()])
        self.assertFalse(case["hit_at_1"])
        self.assertTrue(case["evidence_hit_at_3"])

    def test_does_not_union_chunks_or_use_rank_four(self):
        case = evaluate_query(question(), [hit(text="complete"), hit(text="evidence"),
                                            hit(text="nothing"), hit()])
        self.assertFalse(case["evidence_hit_at_3"])
        self.assertEqual(len(case["hits"]), 3)

    def test_empty_results_are_not_vacuous_filter_success(self):
        case = evaluate_query(question(), [])
        self.assertFalse(case["hit_at_1"])
        self.assertFalse(case["evidence_hit_at_3"])
        self.assertFalse(case["requested_filter_compliant"])

    def test_aggregation_uses_actual_split_denominators(self):
        dev = {**evaluate_query(question(), [hit()]), "strategy": "A"}
        q2 = {**question(), "id": "test01", "split": "test", "filter": {}}
        test = {**evaluate_query(q2, []), "strategy": "A"}
        rows = summarize([dev, test])["rows"]
        self.assertEqual([r["hit_at_1_fraction"] for r in rows], ["1/1", "0/1"])
        self.assertIsNone(rows[1]["filter_compliance"])
        with self.assertRaises(ValueError):
            summarize([dev, dev])

    def test_empty_gold_is_rejected(self):
        q = question()
        q["gold_evidence"][0]["evidence_quote"] = " "
        with self.assertRaises(ValueError):
            evaluate_query(q, [])
