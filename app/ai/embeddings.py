"""Embedding providers and a small semantic index.

The default provider is a deterministic, offline TF-IDF vectorizer
(sklearn). It requires no model downloads and is stable across runs.
If `sentence-transformers` is installed, the SentenceTransformerProvider
can be enabled via EMBEDDING_PROVIDER=sentence-transformers. Both
implement the same interface so the recommender and RAG layers never
change.
"""
from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app import config
from app.utils import get_logger

log = get_logger("embeddings")

_ST_AVAILABLE = False
try:  # optional, heavier dependency — check torch first to avoid noisy warnings
    import torch  # noqa: F401

    from sentence_transformers import SentenceTransformer  # type: ignore

    _ST_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    _ST_AVAILABLE = False


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray:
        ...

    def similarity(self, query: np.ndarray, docs: np.ndarray) -> np.ndarray:
        ...


class TfidfEmbedder:
    """TF-IDF vectorizer + cosine similarity (offline, deterministic)."""

    name = "tfidf"

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            token_pattern=r"(?u)\b[a-zA-Z0-9_+#.-]{2,}\b",
            ngram_range=(1, 2),
            max_features=20000,
            sublinear_tf=True,
        )
        self._fit = False

    def fit(self, texts: list[str]) -> "TfidfEmbedder":
        if texts:
            self._vectorizer.fit(texts)
            self._fit = True
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fit or not texts:
            return np.zeros((len(texts), 1))
        return self._vectorizer.transform(texts).toarray().astype(np.float32)

    @staticmethod
    def similarity(query: np.ndarray, docs: np.ndarray) -> np.ndarray:
        q = query / (np.linalg.norm(query, axis=1, keepdims=True) + 1e-12)
        d = docs / (np.linalg.norm(docs, axis=1, keepdims=True) + 1e-12)
        return (q @ d.T).ravel()


class SentenceTransformerEmbedder:
    """Optional higher-quality embedder (requires sentence-transformers + torch)."""

    name = "sentence-transformers"

    def __init__(self, model_name: str | None = None) -> None:
        if not _ST_AVAILABLE:
            raise RuntimeError(
                "sentence-transformers is not importable; install it or use the tfidf provider."
            )
        self.model_name = model_name or config.EMBEDDING_MODEL
        self._model = SentenceTransformer(self.model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype=np.float32)

    @staticmethod
    def similarity(query: np.ndarray, docs: np.ndarray) -> np.ndarray:
        return (query @ docs.T).ravel()


@dataclass
class SemanticIndex:
    """Indexes documents and returns ranked similarity matches for a query."""

    embedder: Embedder
    doc_ids: list[str] = None  # type: ignore[assignment]
    _matrix: np.ndarray = None  # type: ignore[assignment]

    @classmethod
    def build(cls, items: list[tuple[str, str]], provider: str = "auto") -> "SemanticIndex":
        """items = [(id, text), ...]. Provider: auto|tfidf|sentence-transformers."""
        ids = [i for i, _ in items]
        texts = [t for _, t in items]
        embedder = build_embedder(provider)
        if isinstance(embedder, TfidfEmbedder):
            embedder.fit(texts)
        matrix = embedder.encode(texts)
        idx = cls(embedder=embedder, doc_ids=ids, _matrix=matrix)
        log.info("semantic index built for %d docs with %s", len(ids), embedder.name)
        return idx

    def query(self, text: str, k: int = 5) -> list[tuple[str, float]]:
        if not self.doc_ids:
            return []
        vec = self.embedder.encode([text])
        scores = self.embedder.similarity(vec, self._matrix)
        order = np.argsort(-scores)
        results = []
        for pos in order[:k]:
            score = float(scores[pos])
            if score <= 0:
                break
            results.append((self.doc_ids[int(pos)], round(score, 4)))
        return results

    def similarity_to(self, text: str, doc_id: str) -> float:
        if not self.doc_ids:
            return 0.0
        try:
            pos = self.doc_ids.index(doc_id)
        except ValueError:
            return 0.0
        vec = self.embedder.encode([text])
        return float(self.embedder.similarity(vec, self._matrix)[pos])


def build_embedder(provider: str = "auto") -> Embedder:
    """Factory honoring config.EMBEDDING_PROVIDER; auto prefers tfidf for reliability."""
    choice = provider if provider != "auto" else config.EMBEDDING_PROVIDER
    if choice == "sentence-transformers" and _ST_AVAILABLE:
        try:
            return SentenceTransformerEmbedder()
        except Exception as exc:  # pragma: no cover - model download failure
            log.warning("sentence-transformers unavailable (%s); falling back to tfidf", exc)
    return TfidfEmbedder()


def _corpus_hash(texts: list[str]) -> str:
    payload = "\n".join(texts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


_cached_index: dict[str, SemanticIndex] = {}


def cached_semantic_index(
    items: list[tuple[str, str]], provider: str = "auto"
) -> SemanticIndex:
    """Build (or load from disk) a semantic index for a stable corpus.

    The index is cached in-memory per corpus-hash and persisted to
    `data/embeddings_cache/` as a pickle so application restarts don't
    rebuild it.
    """
    corpus_hash = _corpus_hash([t for _, t in items])
    key = f"{corpus_hash}_{provider}"
    if key in _cached_index:
        return _cached_index[key]

    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.CACHE_DIR / f"semantic_index_{key}.pkl"
    if path.exists():
        try:
            with open(path, "rb") as fh:
                idx = pickle.load(fh)
            _cached_index[key] = idx
            log.info("loaded cached semantic index (%d docs)", len(idx.doc_ids))
            return idx
        except Exception as exc:  # pragma: no cover - corrupt cache
            log.warning("failed to load cached index: %s", exc)

    idx = SemanticIndex.build(items, provider=provider)
    try:
        with open(path, "wb") as fh:
            pickle.dump(idx, fh)
    except OSError:  # pragma: no cover - read-only fs
        pass
    _cached_index[key] = idx
    return idx
