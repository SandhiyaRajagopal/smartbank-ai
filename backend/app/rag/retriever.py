"""Hybrid retrieval = semantic vector search + BM25 keyword search, fused with RRF.

- Vector search (Gemini embeddings stored in Chroma) finds chunks with similar *meaning*:
  "can I close my loan early?" matches the "Prepayment and foreclosure" section.
- BM25 (classic keyword ranking) finds exact terms the embedding may blur: "FOIR", "NACH", "80TTA".
- Reciprocal Rank Fusion merges the two ranked lists: score = sum(1 / (60 + rank)).
  It needs no score normalisation, which is why it's the standard way to combine retrievers.

If embeddings are unavailable (no API key, quota error), retrieval keeps working in
BM25-only mode, so the Compliance Agent degrades instead of failing.
"""
import logging
import re
import threading

from rank_bm25 import BM25Okapi

from ..config import settings
from .ingest import Chunk, load_chunks

log = logging.getLogger("smartbank.rag")
RRF_K = 60
CANDIDATES = 8


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class PolicyIndex:
    def __init__(self, policies_dir: str, chroma_dir: str):
        self.policies_dir = policies_dir
        self.chroma_dir = chroma_dir
        self._lock = threading.Lock()
        self._ready = False
        self.chunks: list[Chunk] = []
        self.bm25: BM25Okapi | None = None
        self.vectorstore = None
        self.mode = "not_built"

    def build(self) -> None:
        with self._lock:
            if self._ready:
                return
            self.chunks = load_chunks(self.policies_dir)
            self.bm25 = BM25Okapi([_tokenize(c.text) for c in self.chunks])
            self.mode = "bm25_only"
            try:
                self.vectorstore = self._build_vectorstore()
                self.mode = "hybrid"
            except Exception as e:
                log.warning("vector index unavailable, using BM25 only: %s", e)
            self._ready = True
            log.info("policy index ready: %d chunks, mode=%s", len(self.chunks), self.mode)

    def _build_vectorstore(self):
        from langchain_chroma import Chroma

        from ..llm import get_embeddings

        store = Chroma(collection_name="smartbank_policies", embedding_function=get_embeddings(),
                       persist_directory=self.chroma_dir)
        existing = set(store.get(include=[])["ids"])
        wanted = {c.id for c in self.chunks}
        if existing != wanted:  # documents changed (or first run) -> re-embed everything
            if existing:
                store.delete(ids=list(existing))
            store.add_texts(texts=[c.text for c in self.chunks], ids=[c.id for c in self.chunks],
                            metadatas=[{"source": c.source, "title": c.title, "section": c.section}
                                       for c in self.chunks])
        return store

    def search(self, query: str, k: int = 4) -> list[dict]:
        self.build()
        by_id = {c.id: c for c in self.chunks}
        fused: dict[str, float] = {}
        signals: dict[str, list[str]] = {}

        bm25_scores = self.bm25.get_scores(_tokenize(query))
        bm25_ranked = sorted(range(len(self.chunks)), key=lambda i: bm25_scores[i], reverse=True)
        for rank, i in enumerate([i for i in bm25_ranked if bm25_scores[i] > 0][:CANDIDATES]):
            cid = self.chunks[i].id
            fused[cid] = fused.get(cid, 0) + 1 / (RRF_K + rank + 1)
            signals.setdefault(cid, []).append("keyword")

        if self.vectorstore is not None:
            try:
                for rank, doc in enumerate(self.vectorstore.similarity_search(query, k=CANDIDATES)):
                    cid = doc.id if doc.id in by_id else next(
                        (c.id for c in self.chunks if c.text == doc.page_content), None)
                    if cid:
                        fused[cid] = fused.get(cid, 0) + 1 / (RRF_K + rank + 1)
                        signals.setdefault(cid, []).append("semantic")
            except Exception as e:
                log.warning("vector search failed, keyword results only: %s", e)

        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [{"source": by_id[cid].source, "title": by_id[cid].title, "section": by_id[cid].section,
                 "text": by_id[cid].text, "score": round(score, 4), "matched_by": signals[cid]}
                for cid, score in top]


_index: PolicyIndex | None = None


def get_index() -> PolicyIndex:
    global _index
    if _index is None:
        _index = PolicyIndex(settings.policies_dir, settings.chroma_dir)
    return _index
