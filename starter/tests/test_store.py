"""Integration tests against PostgreSQL; use only a fresh isolated test schema."""
import os
from pathlib import Path
import unittest
import uuid

from dotenv import load_dotenv
from psycopg import sql

from src.models import Chunk
from src.store import PgVectorStore


def chunk(name, section="one", text=None, metadata=None):
    return Chunk(name, "test_doc", "test.pdf", 11, text or f"Text for {name}",
                 {"section": section, **(metadata or {})})


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        cls.url = os.getenv("DATABASE_URL")
        if not cls.url:
            raise unittest.SkipTest("Set DATABASE_URL and start the local pgvector database")
        cls.schema = "day06_test_" + uuid.uuid4().hex[:12]
        cls.store = PgVectorStore(cls.url, 3, schema=cls.schema)
        cls.store.create_schema()

    @classmethod
    def tearDownClass(cls):
        if not cls.schema.startswith("day06_test_") or len(cls.schema) != 23:
            raise RuntimeError("Refusing unexpected test-schema cleanup")
        cls.store.connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))
        cls.store.close()

    def test_cosine_ranking_and_parameterized_section_filter(self):
        store = self.store
        store.upsert("rank", [chunk("x"), chunk("y", "two"), chunk("diagonal", "two")],
                     [[1, 0, 0], [0, 1, 0], [1, 1, 0]])
        result = store.search("rank", [1, 0, 0])
        self.assertEqual([r["chunk_id"] for r in result], ["x", "diagonal", "y"])
        self.assertAlmostEqual(result[0]["score"], 1)
        self.assertEqual([r["chunk_id"] for r in store.search("rank", [1, 0, 0], filters={"section": "two"})],
                         ["diagonal", "y"])
        self.assertEqual(store.search("rank", [1, 0, 0], filters={"section": "x' OR 1=1 --"}), [])
        self.assertEqual(store.count("rank"), 3)
        with self.assertRaises(ValueError):
            store.search("rank", [1, 0, 0], filters={"gold_source_id": "test_doc"})

    def test_reingest_removes_obsolete_chunks_and_preserves_other_strategies(self):
        store = self.store
        store.upsert("sync", [chunk("a"), chunk("b")], [[1, 0, 0], [0, 1, 0]])
        store.upsert("other", [chunk("b")], [[0, 1, 0]])
        store.upsert("sync", [chunk("a"), chunk("c")], [[1, 0, 0], [0, 0, 1]], manifest={"version": "new"})
        store.upsert("sync", [chunk("a"), chunk("c")], [[1, 0, 0], [0, 0, 1]], manifest={"version": "new"})
        self.assertEqual(store.count("sync"), 2)
        self.assertEqual({r["chunk_id"] for r in store.search("sync", [1, 0, 0])}, {"a", "c"})
        self.assertEqual(store.count("other"), 1)
        with PgVectorStore(self.url, 3, schema=self.schema) as reopened:
            self.assertEqual(reopened.count("sync"), 2)
            self.assertEqual(reopened.snapshot("sync"), {"version": "new"})

    def test_bad_vector_or_duplicate_input_does_not_replace_snapshot(self):
        self.store.upsert("valid", [chunk("kept")], [[1, 0, 0]])
        for vector in [[1, 0], [0, 0, 0], [float("nan"), 0, 1]]:
            with self.assertRaises(ValueError):
                self.store.upsert("valid", [chunk("bad")], [vector])
        with self.assertRaises(ValueError):
            self.store.upsert("valid", [chunk("same"), chunk("same")], [[1, 0, 0], [0, 1, 0]])
        self.assertEqual(self.store.search("valid", [1, 0, 0])[0]["chunk_id"], "kept")

    def test_failed_transaction_rolls_back_partial_updates(self):
        self.store.upsert("atomic", [chunk("kept", text="original")], [[1, 0, 0]])
        with self.assertRaises(TypeError):
            self.store.upsert("atomic", [chunk("kept", text="changed"), chunk("bad", metadata={"bad": {1, 2}})],
                              [[1, 0, 0], [0, 1, 0]])
        result = self.store.search("atomic", [1, 0, 0])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "original")

    def test_dimension_mismatch_cannot_reuse_existing_table(self):
        with PgVectorStore(self.url, 4, schema=self.schema) as wrong:
            with self.assertRaises(ValueError):
                wrong.create_schema()
