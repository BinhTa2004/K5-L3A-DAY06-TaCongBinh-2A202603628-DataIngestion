"""Persistent PostgreSQL/pgvector snapshots and exact cosine search."""
import math
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Chunk


class PgVectorStore:
    FILTER_FIELDS = {"section", "section_id", "language", "document_id", "source", "page"}

    def __init__(self, database_url: str, dimensions: int, *, schema: str = "day06") -> None:
        if type(dimensions) is not int or dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")
        self.dimensions = dimensions
        self.schema = schema
        self.table = sql.Identifier(schema, "chunks")
        self.states = sql.Identifier(schema, "snapshots")
        self.connection = psycopg.connect(database_url, connect_timeout=5, autocommit=True,
                                          row_factory=dict_row, application_name="day06_ingestion")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self.connection.close()

    def create_schema(self) -> None:
        with self.connection.transaction():
            self.connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            self.connection.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    strategy text NOT NULL,
                    chunk_id text NOT NULL,
                    document_id text NOT NULL,
                    source text NOT NULL,
                    page integer NOT NULL CHECK (page > 0),
                    text text NOT NULL CHECK (length(text) > 0),
                    metadata jsonb NOT NULL,
                    embedding vector({}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )
            """).format(self.table, sql.Literal(self.dimensions)))
            self.connection.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    strategy text PRIMARY KEY,
                    manifest jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """).format(self.states))
            actual = self.connection.execute("""
                SELECT format_type(a.atttypid, a.atttypmod) AS type
                FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = 'chunks' AND a.attname = 'embedding'
            """, (self.schema,)).fetchone()
            if not actual or actual["type"] != f"vector({self.dimensions})":
                raise ValueError("Existing vector column has different dimensions; use a separate schema")

    def _vector(self, values) -> str:
        if len(values) != self.dimensions:
            raise ValueError(f"Expected {self.dimensions} vector dimensions")
        converted = [float(value) for value in values]
        if not all(math.isfinite(value) for value in converted) or not any(converted):
            raise ValueError("Cosine vectors must be finite and nonzero")
        return "[" + ",".join(format(value, ".17g") for value in converted) + "]"

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], *,
               manifest: dict[str, Any] | None = None) -> None:
        """Atomically synchronize the COMPLETE snapshot for one strategy.

        Rows absent from this supplied snapshot are removed only for this
        strategy. Empty snapshots are rejected to avoid accidental clearing.
        Other strategies and schemas are untouched. Validate before mutation.
        """
        if not strategy or not chunks or len(chunks) != len(vectors):
            raise ValueError("A nonempty strategy snapshot needs one vector per chunk")
        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate chunk IDs in snapshot")
        rows = []
        for chunk, vector in zip(chunks, vectors):
            if not chunk.text.strip() or type(chunk.page) is not int or chunk.page <= 0:
                raise ValueError("Chunks require nonempty text and a positive physical page")
            if not chunk.document_id or not chunk.source or not chunk.metadata.get("section"):
                raise ValueError("Chunks require document_id, source and section metadata")
            metadata = {**chunk.metadata, "document_id": chunk.document_id,
                        "source": chunk.source, "page": chunk.page}
            rows.append((strategy, chunk.chunk_id, chunk.document_id, chunk.source,
                         chunk.page, chunk.text, Jsonb(metadata), self._vector(vector)))
        with self.connection.transaction():
            # Serialize concurrent writers for the same strategy snapshot.
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                                    (self.schema, strategy))
            with self.connection.cursor() as cursor:
                cursor.executemany(sql.SQL("""
                    INSERT INTO {} (strategy, chunk_id, document_id, source, page, text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id, source = EXCLUDED.source,
                        page = EXCLUDED.page, text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding
                """).format(self.table), rows)
            self.connection.execute(sql.SQL("DELETE FROM {} WHERE strategy = %s AND NOT (chunk_id = ANY(%s))")
                                    .format(self.table), (strategy, ids))
            self.connection.execute(sql.SQL("""
                INSERT INTO {} (strategy, manifest) VALUES (%s, %s)
                ON CONFLICT (strategy) DO UPDATE SET manifest = EXCLUDED.manifest, updated_at = now()
            """).format(self.states), (strategy, Jsonb(manifest or {})))

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if type(top_k) is not int or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        filters = filters or {}
        if not isinstance(filters, dict) or set(filters) - self.FILTER_FIELDS:
            raise ValueError("Unsupported metadata filter field")
        for key, value in filters.items():
            if key == "page":
                if type(value) is not int or value <= 0:
                    raise ValueError("page filter must be a positive integer")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError("Metadata filters require nonempty string values")
        vector = self._vector(query_vector)
        rows = self.connection.execute(sql.SQL("""
            SELECT chunk_id, document_id, source, page, text, metadata,
                   embedding <=> %s::vector AS distance
            FROM {} WHERE strategy = %s AND metadata @> %s
            ORDER BY distance ASC, chunk_id ASC LIMIT %s
        """).format(self.table), (vector, strategy, Jsonb(filters), top_k)).fetchall()
        return [{**row, "score": 1.0 - float(row["distance"])} for row in rows]

    def count(self, strategy: str) -> int:
        return self.connection.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE strategy = %s")
                                       .format(self.table), (strategy,)).fetchone()["n"]

    def snapshot(self, strategy: str) -> dict[str, Any] | None:
        row = self.connection.execute(sql.SQL("SELECT manifest FROM {} WHERE strategy = %s")
                                      .format(self.states), (strategy,)).fetchone()
        return row["manifest"] if row else None

    def backend_info(self) -> dict[str, Any]:
        row = self.connection.execute("""
            SELECT current_database() AS database, current_setting('server_version') AS postgres_version,
                   extversion AS pgvector_version FROM pg_extension WHERE extname = 'vector'
        """).fetchone()
        return {**row, "schema": self.schema, "dimensions": self.dimensions,
                "metric": "cosine", "search": "exact sequential scan; no ANN index"}
