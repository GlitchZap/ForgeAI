"""Eval generator (req 4). Cases come from the documents; every key fact is verified verbatim against its source
chunk, so a generator hallucination can't become a "ground truth". Written by the JUDGE model, not the agent
model, so the agent is never graded on an exam it wrote itself."""
from __future__ import annotations

import random
import re

from .ingest import Chunk
from .llm import LLM, LLMError
from .promptlib import P
from .schemas import AgentDefinition, EvalCase, GeneratedQAList, GeneratedQuestions, Requirements
from .textmatch import fact_in, jaccard
from .textmatch import key_stems as _key
from .tools import REGISTRY, TRIGGERS


def _sample_chunks(chunks: list[Chunk], n: int, rng: random.Random) -> list[Chunk]:
    """Round-robin across documents so one big file can't dominate the test set."""
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        if len(c.text) >= 120:
            by_doc.setdefault(c.doc, []).append(c)
    for v in by_doc.values():
        rng.shuffle(v)
    out, docs = [], sorted(by_doc)
    while len(out) < n and any(by_doc.values()):
        for d in docs:
            if by_doc[d] and len(out) < n:
                out.append(by_doc[d].pop())
    return out


def _verified_facts(facts: list[str], source: str, question: str) -> list[str]:
    # keep facts that really are in the source and that the question doesn't already give away
    return [f for f in facts if f.strip() and fact_in(f, source, threshold=0.9) and not fact_in(f, question, threshold=0.9)][:4]


class EvalGenerator:
    def __init__(self, llm: LLM, seed: int = 7):
        self.llm, self.rng = llm, random.Random(seed)
        self.log: list[dict] = []  # every rejected item and why, for the report

    def _gen(self, prompt, cls):
        try:
            return self.llm.structured(prompt, cls, judge=True, temperature=0.4)
        except LLMError as e:
            self.log.append({"error": str(e)[:200]})
            return None

    def answerable(self, req: Requirements, chunks: list[Chunk], n_chunks: int) -> list[EvalCase]:
        out = []
        for c in _sample_chunks(chunks, n_chunks, self.rng):
            g = self._gen(P("evalgen_answerable", audience=req.audience, n=2, source=c.doc, excerpt=c.text), GeneratedQAList)
            for it in (g.items if g else [])[:2]:
                facts = _verified_facts(it.key_facts, c.text, it.question)
                if not facts:
                    self.log.append({"rejected": it.question, "why": "no key fact found verbatim in source"})
                    continue
                out.append(EvalCase(id="", kind="answerable", question=it.question, expected_sources=[c.doc],
                                    key_facts=facts, origin=c.id))
        return out

    def multi_doc(self, req: Requirements, chunks: list[Chunk], n: int) -> list[EvalCase]:
        docs = sorted({c.doc for c in chunks})
        if len(docs) < 2:
            self.log.append({"skipped": "multi_doc", "why": "only one document"})
            return []
        out = []
        for _ in range(n * 2):
            if len(out) >= n:
                break
            da, db = self.rng.sample(docs, 2)
            a = self.rng.choice([c for c in chunks if c.doc == da])
            b = self.rng.choice([c for c in chunks if c.doc == db])
            g = self._gen(P("evalgen_multidoc", audience=req.audience, source_a=a.doc, excerpt_a=a.text,
                            source_b=b.doc, excerpt_b=b.text), GeneratedQAList)
            for it in (g.items if g else [])[:1]:
                fa, fb = _verified_facts(it.key_facts, a.text, it.question), _verified_facts(it.key_facts, b.text, it.question)
                if not fa or not fb:
                    self.log.append({"rejected": it.question, "why": "multi-doc case lacks a verified fact from each document"})
                    continue
                q = _key(it.question)
                if not any(_key(f) & q for f in fa) or not any(_key(f) & q for f in fb):
                    # real run: an expenses question whose "expected fact" was about crew leave rules
                    self.log.append({"rejected": it.question, "why": "question is not about the facts from both documents"})
                    continue
                out.append(EvalCase(id="", kind="multi_doc", question=it.question, expected_sources=[a.doc, b.doc],
                                    key_facts=list(dict.fromkeys(fa[:2] + fb[:2])), origin=f"{a.id}+{b.id}"))
        return out

    def ambiguous(self, req: Requirements, chunks: list[Chunk], n: int) -> list[EvalCase]:
        out = []
        for c in _sample_chunks(chunks, n * 2, self.rng):
            if len(out) >= n:
                break
            g = self._gen(P("evalgen_ambiguous", audience=req.audience, source=c.doc, excerpt=c.text), GeneratedQAList)
            for it in (g.items if g else [])[:1]:
                facts = _verified_facts(it.key_facts, c.text, it.question)
                if facts:
                    out.append(EvalCase(id="", kind="ambiguous", question=it.question, expected_sources=[c.doc],
                                        key_facts=facts, origin=c.id))
        return out

    def out_of_scope(self, req: Requirements, n: int) -> list[EvalCase]:
        unsupported = [g.topic for g in req.groundability if g.status == "unsupported"]
        g = self._gen(P("evalgen_out_of_scope", scope=req.scope, must_refuse="\n".join(f"- {x}" for x in req.must_refuse),
                        unsupported="\n".join(f"- {x}" for x in unsupported) or "(none)", n=n), GeneratedQuestions)
        in_scope = set().union(*[_key(t.name) for t in req.must_answer]) if req.must_answer else set()
        out = []
        for q in (g.questions if g else [])[:n]:
            if not q.strip():
                continue
            if _key(q) & in_scope:  # real run: "company policy on work-from-home days?" was labelled must-refuse
                self.log.append({"rejected": q, "why": "labelled must-refuse but names a must-answer topic"})
                continue
            out.append(EvalCase(id="", kind="out_of_scope", question=q, should_refuse=True, origin="must_refuse"))
        return out

    def tool_cases(self, req: Requirements, agent: AgentDefinition, chunks: list[Chunk], n_each: int) -> list[EvalCase]:
        out = []
        for t in agent.tools:
            if t.name == "csv_lookup":
                # CSV rows are also retrievable chunks, so the answerable cases (with verified row facts) already
                # test it; a "did you call the tool" case would fail correct answers that came via retrieval.
                continue
            g = self._gen(P("evalgen_tool", tool=t.name, purpose=REGISTRY[t.name]["purpose"], audience=req.audience,
                            scope=req.scope, n=n_each, context=""), GeneratedQuestions)
            for q in (g.questions if g else [])[:n_each]:
                if not re.search(rf"\b({TRIGGERS[t.name].replace(' ', r'\s+')})", q, re.I):
                    # real run: "standard notice period?" was generated as a current_date case
                    self.log.append({"rejected": q, "why": f"does not actually need {t.name}"})
                    continue
                out.append(EvalCase(id="", kind="tool", question=q, expected_tool=t.name, origin=f"tool:{t.name}"))
        return out


def generate_evalset(req: Requirements, agent: AgentDefinition, chunks: list[Chunk], llm: LLM,
                     target: int = 24, seed: int = 7) -> tuple[list[EvalCase], list[dict]]:
    g = EvalGenerator(llm, seed)
    cases = g.answerable(req, chunks, n_chunks=6)
    cases += g.multi_doc(req, chunks, 3)
    cases += g.ambiguous(req, chunks, 3)
    cases += g.out_of_scope(req, 6)
    cases += g.tool_cases(req, agent, chunks, 2)
    for _ in range(4):  # top up answerable cases until the minimum (20) is met; small models reject a lot
        if len(_dedupe(cases)) >= max(target, 20):
            break
        cases += g.answerable(req, chunks, n_chunks=6)
    cases = _dedupe(cases)
    # stratified dev/holdout split: the optimizer only ever sees dev failures; holdout measures overfitting
    rng = random.Random(seed)
    for kind in sorted({c.kind for c in cases}):
        group = [c for c in cases if c.kind == kind]
        rng.shuffle(group)
        for c in group[:round(len(group) * 0.3)]:
            c.split = "holdout"
    for i, c in enumerate(cases, 1):
        c.id = f"{c.kind[:3]}-{i:02d}"
    return cases, g.log


def _dedupe(cases: list[EvalCase]) -> list[EvalCase]:
    out: list[EvalCase] = []
    for c in cases:
        if all(jaccard(c.question, o.question) < 0.7 for o in out):
            out.append(c)
    return out
