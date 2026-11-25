"""Hybrid retrieval: BM25 (exact terms, part numbers, policy codes) + embeddings (paraphrase), fused with RRF.

Embeddings are optional: if the embed model is unavailable the index degrades to BM25 and says so.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from .ingest import Chunk
from .llm import LLM, LLMError

_STOP = set("a an the of to in on for and or is are was were be by with at as it this that from what how do does i my "
            "can you your we our me which who when where why if any there their they will would should".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:[-./][a-z0-9]+)*", text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / max(len(docs), 1)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> np.ndarray:
        s = np.zeros(len(self.docs))
        for i, (tf, d) in enumerate(zip(self.tf, self.docs)):
            norm = self.k1 * (1 - self.b + self.b * len(d) / (self.avgdl or 1))
            s[i] = sum(self.idf.get(q, 0) * tf[q] * (self.k1 + 1) / (tf[q] + norm) for q in query if q in tf)
        return s


class Index:
    def __init__(self, chunks: list[Chunk], llm: LLM | None = None):
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}
        self.bm25 = BM25([tokenize(c.text) for c in chunks])
        self.llm = llm
        self.emb: np.ndarray | None = None
        self.mode = "bm25"
        if llm is not None and llm.embed_model and chunks:
            try:
                m = np.array(llm.embed([c.text[:2000] for c in chunks]), dtype=np.float32)
                self.emb = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
                self.mode = "hybrid"
            except LLMError:
                self.emb = None  # reported via self.mode

    def search(self, query: str, k: int = 4, expansions: list[str] | None = None) -> list[Chunk]:
        if not self.chunks:
            return []
        rankings = []
        for q in [query, *(expansions or [])]:
            rankings.append(np.argsort(-self.bm25.scores(tokenize(q))))
            if self.emb is not None:
                v = np.array(self.llm.embed([q])[0], dtype=np.float32)
                v /= np.linalg.norm(v) + 1e-9
                rankings.append(np.argsort(-(self.emb @ v)))
        fused = Counter()
        for r in rankings:  # reciprocal rank fusion, k=60
            for rank, idx in enumerate(r[:50]):
                fused[int(idx)] += 1.0 / (60 + rank)
        return [self.chunks[i] for i, _ in fused.most_common(k)]
