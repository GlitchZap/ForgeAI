"""Judge (requirement 5). Deterministic checks first; the LLM judge only fills the gaps, and is itself checked.

Defences against known LLM-judge failure modes:
- position bias  -> two passes with expected facts AND context chunks in reversed order; a fact only counts if
                    both passes credit it; pass disagreement is recorded and reported as a judge-reliability metric.
- self-preference-> the judge runs on a different model family from the agent (FORGE_JUDGE_MODEL); the report
                    warns when they are the same.
- verbosity bias -> binary per-fact rubric, no holistic score; "length earns no credit" in the prompt; long
                    answers are flagged; unsupported numbers are caught deterministically regardless of prose.
- false accusations -> every claim the LLM calls unsupported is re-checked against the context; claims whose
                    numbers and words are all in the context are discarded.
"""
from __future__ import annotations

import hashlib

from .llm import LLM, LLMError
from .promptlib import P
from .schemas import CaseResult, EvalCase, JudgeOut, Trace
from .textmatch import fact_in, looks_like_refusal, numbers, unsupported_numbers


class Judge:
    def __init__(self, llm: LLM):
        self.llm = llm
        self.cache: dict[str, CaseResult] = {}
        self._passes: list[dict] = []  # unchanged answer + context -> reuse verdict across iterations

    def grade(self, case: EvalCase, trace: Trace, context: str) -> CaseResult:
        key = hashlib.sha1(f"{case.id}|{trace.reply.model_dump_json()}|{trace.retrieved}|{trace.retrieved_docs}|{trace.tool_calls}|{context}".encode()).hexdigest()
        if key in self.cache:
            return self.cache[key].model_copy()
        res = self._grade(case, trace, context)
        self.cache[key] = res
        return res.model_copy()

    def _grade(self, case: EvalCase, trace: Trace, context: str) -> CaseResult:
        rep = trace.reply
        answer = rep.answer
        refused = rep.refused or (looks_like_refusal(answer) and len(answer) < 300)
        base = dict(case_id=case.id, kind=case.kind, split=case.split, refused=refused, answer=answer[:1500])
        notes: list[str] = []
        if len(answer) > 1500:
            notes.append("verbose answer (>1500 chars)")

        # ---- must refuse
        if case.should_refuse:
            if refused:
                return CaseResult(**base, passed=True, refusal_ok=True, notes=notes)
            bad_nums = unsupported_numbers(answer, context + " " + case.question)
            failure = "hallucination" if bad_nums else "prompt_defect"
            notes.append("answered an out-of-scope question" + (f"; invented numbers {sorted(bad_nums)}" if bad_nums else ""))
            return CaseResult(**base, passed=False, refusal_ok=False, failure=failure, notes=notes)

        # ---- tool cases: the right tool must have been called
        if case.kind == "tool":
            called = {c["tool"] for c in trace.tool_calls}
            tool_ok = case.expected_tool in called
            passed = tool_ok and not refused
            failure = None if passed else ("wrong_refusal" if refused and tool_ok else "prompt_defect")
            if not tool_ok:
                notes.append(f"expected tool {case.expected_tool}, called {sorted(called) or 'none'}")
            return CaseResult(**base, passed=passed, refusal_ok=not refused, tool_ok=tool_ok, failure=failure, notes=notes)

        # ---- answerable / multi_doc / ambiguous
        exp = set(case.expected_sources)
        retrieval_hit = exp <= set(trace.retrieved_docs) if exp else True
        cited_docs = {c.split("#")[0] for c in rep.citations}
        cited_hit = bool(exp & cited_docs) if exp else True
        det = [fact_in(f, answer) for f in case.key_facts]
        det_recall = sum(det) / len(det) if det else 0.0
        if refused:
            return CaseResult(**base, passed=False, refusal_ok=False, retrieval_hit=retrieval_hit, cited_hit=cited_hit,
                              fact_recall_det=det_recall,
                              failure="wrong_refusal" if retrieval_hit else "retrieval_miss",
                              notes=notes + ["refused an answerable question"])

        bad_nums = unsupported_numbers(answer, context + " " + case.question)
        if det_recall == 1.0 and cited_hit and not bad_nums:
            # every expected fact is literally in the answer, the right source is cited, no invented numbers:
            # the deterministic evidence is stronger than an LLM opinion, so skip two judge calls
            return CaseResult(**base, passed=True, refusal_ok=True, retrieval_hit=retrieval_hit, cited_hit=cited_hit,
                              fact_recall_det=det_recall, grounded=True, notes=notes + ["passed on deterministic checks"])
        llm_recall, agree, claims = self._llm_passes(case, answer, context)
        claims = [c for c in claims if not _claim_supported(c, context)]
        grounded = not claims and not bad_nums
        if claims:
            notes.append("unsupported claims: " + "; ".join(claims[:3]))
        if bad_nums:
            notes.append(f"numbers not in context: {sorted(bad_nums)}")
        if agree is False:
            notes.append("judge passes disagreed (position-swap)")
        correctness = max(det_recall, llm_recall if llm_recall is not None else 0.0)
        passed = correctness >= 0.5 and grounded
        failure = None
        if not passed:
            failure = "retrieval_miss" if not retrieval_hit else ("hallucination" if not grounded else "prompt_defect")
            if grounded:
                notes.append(f"missing expected facts (recall {correctness:.2f})")
        return CaseResult(**base, passed=passed, refusal_ok=True, retrieval_hit=retrieval_hit, cited_hit=cited_hit,
                          fact_recall_det=det_recall, fact_recall_llm=llm_recall, grounded=grounded,
                          judge_agreement=agree, failure=failure, notes=notes, judge_passes=self._passes)

    def _llm_passes(self, case: EvalCase, answer: str, context: str) -> tuple[float | None, bool | None, list[str]]:
        facts = case.key_facts
        chunks = [c for c in context.split("\n\n") if c.strip()]
        outs = []
        for order in (1, -1):
            fs = facts[::order]
            ctx = "\n\n".join(chunks[::order])[:6000]
            try:
                o = self.llm.structured(P("judge", context=ctx, question=case.question, answer=answer,
                                          facts="\n".join(f"{i + 1}. {f}" for i, f in enumerate(fs)), nfacts=len(fs)),
                                        JudgeOut, judge=True)
            except LLMError:
                continue
            present = (o.facts_present + [False] * len(fs))[:len(fs)][::order]  # map back to original order
            outs.append((present, o.unsupported_claims))
        self._passes = [{"order": "as given" if i == 0 else "reversed", "facts_present": p, "unsupported_claims": c}
                        for i, (p, c) in enumerate(outs)]
        if not outs:
            return None, None, []
        if len(outs) == 1:
            p, c = outs[0]
            return (sum(p) / len(p) if p else None), None, c
        (pa, ca), (pb, cb) = outs
        consensus = [a and b for a, b in zip(pa, pb)]
        agree = pa == pb and bool(ca) == bool(cb)
        return (sum(consensus) / len(consensus) if consensus else None), agree, list(dict.fromkeys(ca + cb))


def _claim_supported(claim: str, context: str) -> bool:
    """Overrule the judge when every number and most words of its 'unsupported claim' are in the context."""
    if not numbers(claim) <= numbers(context):
        return False
    return fact_in(claim, context, threshold=0.75)
