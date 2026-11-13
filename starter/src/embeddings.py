"""Pinned multilingual E5 embeddings, local inference and no mock fallback."""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import time
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Adapter for the E5 model configured in configs/embedding.json.

    Load only the verified local snapshot. Missing dependencies/weights, invalid
    vectors and overlength inputs raise errors rather than switching models or
    silently truncating source evidence. Text is never sent to a provider API.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", *,
                 config_path: Path | None = None) -> None:
        started = time.perf_counter()
        root = Path(__file__).resolve().parents[2]
        self.config_path = config_path or root / "configs/embedding.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        if model_name != self.config["model_name"]:
            raise ValueError("This adapter requires the explicitly configured E5 model")
        self.model_name = model_name
        self.revision = self.config["revision"]
        self.dimensions = self.config["dimensions"]
        self.batch_size = self.config["batch_size"]
        self.calls: list[dict] = []
        path = root / self.config["model_path"]
        manifest_path = path / "download_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError("Embedding snapshot missing: run scripts/download_embedding_model.py")
        self.download_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (self.download_manifest["model_name"] != self.model_name or
                self.download_manifest["revision"] != self.revision):
            raise ValueError("Downloaded model identity/revision does not match configuration")
        for entry in self.download_manifest["files"]:
            file = path / entry["path"]
            if not file.is_file() or file.stat().st_size != entry["bytes"]:
                raise ValueError(f"Model file missing or wrong size: {entry['path']}")
            checksum = hashlib.sha256()
            with file.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    checksum.update(block)
            if checksum.hexdigest() != entry["sha256"]:
                raise ValueError(f"Model file changed: {entry['path']}")

        # This implementation uses PyTorch only; avoid unrelated TensorFlow/Flax
        # initialization in environments where those optional stacks are installed.
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("USE_FLAX", "0")
        try:
            import numpy as np
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError("Install requirements-embeddings.txt in the active Python environment") from error
        self._np = np
        torch.set_num_threads(self.config["cpu_threads"])
        self._model = SentenceTransformer(str(path), device=self.config["device"],
                                          local_files_only=True, trust_remote_code=False)
        self._model.float()
        self._model.eval()
        if self._model.get_embedding_dimension() != self.dimensions:
            raise ValueError("Actual model dimensions do not match configuration")
        if self._model.max_seq_length != self.config["max_seq_length"]:
            raise ValueError("Actual model token limit does not match configuration")
        self.load_and_verify_seconds = time.perf_counter() - started

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, "document")

    def embed_query(self, question: str) -> list[float]:
        return self.embed_queries([question])[0]

    def embed_queries(self, questions: list[str]) -> list[list[float]]:
        return self._encode(questions, "query")

    def token_lengths(self, texts: list[str], role: str) -> list[int]:
        prefixed = self._inputs(texts, role)
        if not prefixed:
            return []
        encoded = self._model.tokenizer(prefixed, add_special_tokens=True, truncation=False)
        return [len(ids) for ids in encoded["input_ids"]]

    def _inputs(self, texts: list[str], role: str) -> list[str]:
        if role not in {"document", "query"}:
            raise ValueError("role must be document or query")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be nonempty strings")
        prefix = self.config["document_prefix" if role == "document" else "query_prefix"]
        return [prefix + text for text in texts]

    def _encode(self, texts: list[str], role: str) -> list[list[float]]:
        if not texts:
            return []
        started = time.perf_counter()
        prefixed = self._inputs(texts, role)
        lengths = self.token_lengths(texts, role)
        oversized = [(i, count) for i, count in enumerate(lengths)
                     if count > self.config["max_seq_length"]]
        if oversized:
            raise ValueError(f"{role} inputs exceed {self.config['max_seq_length']} tokens "
                             f"including prefix/special tokens: {oversized[:5]}; split smaller")
        vectors = self._model.encode(prefixed, batch_size=self.batch_size,
                                     normalize_embeddings=self.config["normalize_embeddings"],
                                     precision=self.config["precision"],
                                     convert_to_numpy=True, show_progress_bar=False)
        vectors = self._np.asarray(vectors, dtype=self._np.float32)
        if vectors.shape != (len(texts), self.dimensions) or not self._np.isfinite(vectors).all():
            raise ValueError("Provider returned invalid vector dimensions or non-finite values")
        norms = self._np.linalg.norm(vectors, axis=1)
        if not self._np.allclose(norms, 1.0, atol=1e-5):
            raise ValueError("Provider returned zero or non-normalized vectors")
        self.calls.append({"role": role, "inputs": len(texts), "tokens": sum(lengths),
                           "min_tokens": min(lengths), "max_tokens": max(lengths),
                           "seconds": round(time.perf_counter() - started, 6),
                           "timing_scope": "Token validation, encoding and vector validation; excludes model load and output IO",
                           "paid_api_cost_usd": 0})
        return vectors.tolist()

    def metadata(self) -> dict:
        return {**self.config, "load_and_verify_seconds": round(self.load_and_verify_seconds, 6),
                "versions": {name: version(name) for name in
                             ["sentence-transformers", "torch", "transformers", "numpy", "safetensors"]},
                "model_files": self.download_manifest["files"],
                "document_and_query_processing": "Same pinned encoder and mean pooling with E5 role prefixes; L2 normalized float32 vectors",
                "calls": list(self.calls)}
