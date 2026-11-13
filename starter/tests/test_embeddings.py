"""Integration checks against actual pinned model weights, not mock vectors."""
import unittest

import numpy as np

from src.embeddings import MyEmbedder


class RealEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder = MyEmbedder()

    def test_real_multilingual_query_and_document_vectors(self):
        texts = ["3D Gaussian splatting represents a scene with Gaussian primitives.",
                 "Cây cần nước và ánh sáng để sinh trưởng."]
        vectors = np.asarray(self.embedder.embed_documents(texts))
        query = np.asarray(self.embedder.embed_query("Gaussian Splatting biểu diễn cảnh như thế nào?"))
        self.assertEqual(vectors.shape, (2, 384))
        self.assertEqual(query.shape, (384,))
        self.assertTrue(np.isfinite(vectors).all() and np.isfinite(query).all())
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
        self.assertAlmostEqual(float(np.linalg.norm(query)), 1, places=5)
        self.assertFalse(np.allclose(vectors[0], vectors[1]))

    def test_batch_order_matches_individual_encoding(self):
        texts = ["A Gaussian has a center and covariance.", "The road is wet after rain."]
        together = self.embedder.embed_documents(texts)
        for i, text in enumerate(texts):
            np.testing.assert_allclose(together[i], self.embedder.embed_documents([text])[0], atol=1e-6)

    def test_rejects_empty_and_overlength_instead_of_truncating(self):
        self.assertEqual(self.embedder.embed_documents([]), [])
        with self.assertRaises(ValueError):
            self.embedder.embed_query("  ")
        calls_before = len(self.embedder.calls)
        with self.assertRaisesRegex(ValueError, "exceed 512 tokens"):
            self.embedder.embed_documents(["word " * 600])
        self.assertEqual(len(self.embedder.calls), calls_before)

    def test_e5_role_prefixes_are_explicit(self):
        self.assertEqual(self.embedder._inputs(["hello"], "document"), ["passage: hello"])
        self.assertEqual(self.embedder._inputs(["xin chào"], "query"), ["query: xin chào"])


if __name__ == "__main__":
    unittest.main()
