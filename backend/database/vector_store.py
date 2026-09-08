"""
ChromaDB Vector Store Integration.

Semantic search and similarity matching across ingested drug intelligence, so
a query for "heroin" also reaches records that only ever said "chitta".

A note on chunking. The embedding model behind Chroma's default function is
all-MiniLM-L6-v2, which truncates at 256 word-pieces - roughly 1,000
characters. A 1.5 MB Wikipedia page indexed as a single document therefore
produced a vector describing its opening paragraph and nothing else. Search
looked like it worked because short intercepts embed fine; long pages were
effectively invisible past their first few sentences, and any correlation
built on those vectors would have been comparing introductions.

Documents are now split into overlapping chunks, each embedded separately and
tagged with the record it came from. A record matches if any of its chunks
match, and callers get one result per record rather than a page of fragments
from the same source.
"""

from typing import List, Dict, Any, Optional, Tuple
import os
import logging
from config import settings

logger = logging.getLogger("vector_store")

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except ImportError:
    chromadb = None

# Sized to the embedding model's real context rather than to a round number.
CHUNK_CHARS = 900
CHUNK_OVERLAP = 150
# A cap on how much of one document is embedded. Forty chunks covers ~36,000
# characters, which is past the point where a page is still one topic. Beyond
# it the tail is recorded as skipped rather than silently dropped.
MAX_CHUNKS_PER_DOC = 40


def chunk_text(text: str,
               size: int = CHUNK_CHARS,
               overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping windows, preferring paragraph boundaries.

    The overlap keeps a sentence that straddles a boundary retrievable from
    both sides, which matters when the straddling sentence is the one naming
    a quantity or a handle.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS_PER_DOC:
        end = start + size
        if end < len(text):
            # Prefer to break at a paragraph, then a sentence, then a space.
            window = text[start:end]
            for separator in ("\n\n", ". ", "\n", " "):
                cut = window.rfind(separator)
                if cut > size * 0.5:
                    end = start + cut + len(separator)
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return [c for c in chunks if c]


class VectorStore:
    """ChromaDB wrapper for semantic drug intelligence search."""

    def __init__(self):
        self.client = None
        self.collection = None
        self._init_client()

    def _init_client(self):
        if not getattr(settings, "VECTOR_SEARCH_ENABLED", True):
            logger.info("Vector search disabled by configuration.")
            return
        if chromadb is None:
            logger.warning("chromadb package not installed. Semantic vector search will be disabled.")
            return

        try:
            os.makedirs(settings.CHROMADB_PATH, exist_ok=True)
            self.client = chromadb.PersistentClient(path=settings.CHROMADB_PATH)
            self.collection = self.client.get_or_create_collection(
                name=settings.CHROMADB_COLLECTION,
                metadata={"description": "Drug intelligence text embeddings"}
            )
            logger.info(f"Initialized ChromaDB collection: {settings.CHROMADB_COLLECTION}")
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {e}")
            self.client = None
            self.collection = None

    # ── Indexing ─────────────────────────────────────────────────────

    @staticmethod
    def _clean_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """ChromaDB metadata values must be str, int, float or bool."""
        cleaned: Dict[str, Any] = {}
        for k, v in (metadata or {}).items():
            cleaned[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
        return cleaned

    def _drop_existing(self, doc_id: str) -> None:
        """Remove any prior indexing of this record, chunked or not."""
        try:
            self.collection.delete(where={"parent_id": doc_id})
        except Exception as e:                                # pragma: no cover
            logger.debug("No chunked entries to drop for %s: %s", doc_id, e)
        try:
            # Records indexed before chunking used the bare id.
            self.collection.delete(ids=[doc_id])
        except Exception as e:                                # pragma: no cover
            logger.debug("No legacy entry to drop for %s: %s", doc_id, e)

    def add_intelligence(
        self,
        doc_id: str,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Index one record as a set of overlapping chunks. Idempotent."""
        if not self.collection or not (text_content or "").strip():
            return False

        chunks = chunk_text(text_content)
        if not chunks:
            return False

        base = self._clean_metadata(metadata)
        truncated = len(text_content) > sum(len(c) for c in chunks)

        try:
            self._drop_existing(doc_id)
            self.collection.upsert(
                ids=[f"{doc_id}::c{i}" for i in range(len(chunks))],
                documents=chunks,
                metadatas=[
                    {**base,
                     "parent_id": doc_id,
                     "chunk_index": i,
                     "chunk_count": len(chunks),
                     "truncated": bool(truncated)}
                    for i in range(len(chunks))
                ],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert to ChromaDB: {e}")
            return False

    # ── Retrieval ────────────────────────────────────────────────────

    def query_similar(self, query_text: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """
        Semantic search, returning the best-matching chunk per record.

        Without collapsing by record, one long page monopolises the result set
        with several of its own fragments and buries the other sources.
        """
        if not self.collection or not (query_text or "").strip():
            return []

        try:
            # Over-fetch: several hits may collapse onto the same record.
            results = self.collection.query(
                query_texts=[query_text],
                n_results=max(n_results * 4, n_results),
            )
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            return []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[0.0] * len(ids)])[0]

        best: Dict[str, Dict[str, Any]] = {}
        for i, chunk_id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            parent = meta.get("parent_id") or chunk_id
            distance = dists[i] if i < len(dists) else 0.0
            hit = best.get(parent)
            if hit is None or distance < hit["distance"]:
                best[parent] = {
                    "id": parent,
                    "chunk_id": chunk_id,
                    "document": docs[i] if i < len(docs) else "",
                    "metadata": meta,
                    "distance": distance,
                }

        ordered = sorted(best.values(), key=lambda h: h["distance"])
        return ordered[:n_results]

    # ── Bulk access for the correlation layer ────────────────────────

    def all_record_vectors(self) -> Tuple[List[str], List[List[float]], List[Dict[str, Any]]]:
        """
        Return one averaged vector per record, for offline clustering.

        Chunk vectors are mean-pooled so each record contributes once,
        regardless of how long it is. Returns (parent_ids, vectors, metadata).
        """
        if not self.collection:
            return [], [], []

        try:
            payload = self.collection.get(include=["embeddings", "metadatas"])
        except Exception as e:
            logger.error(f"Error reading embeddings from ChromaDB: {e}")
            return [], [], []

        ids = payload.get("ids") or []
        embeddings = payload.get("embeddings")
        metadatas = payload.get("metadatas") or []
        if embeddings is None or len(embeddings) == 0:
            return [], [], []

        try:
            import numpy as np
        except ImportError:                                   # pragma: no cover
            logger.error("numpy is required to pool chunk vectors.")
            return [], [], []

        grouped: Dict[str, List[Any]] = {}
        meta_by_parent: Dict[str, Dict[str, Any]] = {}
        for i, chunk_id in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            parent = (meta or {}).get("parent_id") or chunk_id
            grouped.setdefault(parent, []).append(embeddings[i])
            # Keep the first chunk's metadata as the record's descriptor.
            if parent not in meta_by_parent or (meta or {}).get("chunk_index") == 0:
                meta_by_parent[parent] = dict(meta or {})

        parents = sorted(grouped)
        pooled = []
        for parent in parents:
            stacked = np.asarray(grouped[parent], dtype=float)
            mean = stacked.mean(axis=0)
            norm = np.linalg.norm(mean)
            pooled.append((mean / norm if norm else mean).tolist())

        return parents, pooled, [meta_by_parent[p] for p in parents]


vector_store = VectorStore()
