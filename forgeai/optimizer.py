"""Critic-optimizer (req 6): failures are already classified by the judge; here each category maps to ONE targeted
fix of one part of the definition. Never a full regeneration."""
from __future__ import annotations

from .llm import LLM, LLMError
from .promptlib import P
from .schemas import AgentDefinition, CaseResult, EvalCase, SectionPatch

MEANING = {
    "retrieval_miss": "the expected source document was not among the retrieved excerpts",
    "hallucination": "the agent stated facts or numbers that are not in the excerpts it was given",
    "wrong_refusal": "the agent refused although the excerpts contained the answer",
    "prompt_defect": "the agent had the right excerpts but answered out-of-scope questions, missed required facts, "
                     "or did not use the right tool",
}


def choose_category(dev_failures: list[CaseResult], exhausted: set[str]) -> str | None:
    counts: dict[str, int] = {}
    for r in dev_failures:
        if r.failure and r.failure not in exhausted:
            counts[r.failure] = counts.get(r.failure, 0) + 1
    return max(counts, key=lambda k: (counts[k], k == "retrieval_miss")) if counts else None


def _failure_text(fails: list[CaseResult], cases: dict[str, EvalCase], limit: int = 5) -> str:
    out = []
    for r in fails[:limit]:
        c = cases[r.case_id]
        exp = "MUST REFUSE" if c.should_refuse else (f"expected tool {c.expected_tool}" if c.expected_tool
                                                     else f"expected facts: {c.key_facts}")
        out.append(f"- Q: {c.question}\n  {exp}\n  agent said: {r.answer[:300]}\n  problem: {'; '.join(r.notes) or r.failure}")
    return "\n".join(out)


def _patch(llm: LLM, defn: AgentDefinition, section: str, category: str, fails, cases) -> tuple[str, str, str]:
    current = getattr(defn.prompt, section)
    max_chars = max(600, int(len(current) * 1.8) + 300)  # a fix may grow a section, not balloon it
    p = llm.structured(P("patch_section", category=category, meaning=MEANING[category], section=section,
                         current=current, failures=_failure_text(fails, cases), max_chars=max_chars), SectionPatch)
    why = p.rationale.strip()
    if len(why) < 15 or why in ("...", "one sentence: what changed and why"):  # small models echo the template
        why = f"model gave no usable rationale; patched {section} for {len(fails)} {category} case(s)"
    return current, p.new_text[:max_chars], why


def apply_fix(category: str, defn: AgentDefinition, fails: list[CaseResult], cases: dict[str, EvalCase],
              llm: LLM) -> tuple[AgentDefinition, str, str, str, str] | None:
    """Returns (new_definition, target, before, after, rationale), or None when no further fix exists."""
    new = defn.model_copy(deep=True)
    new.version += 1
    r = new.retrieval
    try:
        if category == "retrieval_miss":
            before = r.model_dump_json()
            if r.top_k < 8:
                r.top_k += 2
                why = f"retrieval missed the source in {len(fails)} cases; widen top_k to {r.top_k}"
            elif not r.query_expansion:
                r.query_expansion = True
                why = "top_k already wide; add query expansion so user wording maps to document vocabulary"
            elif r.chunk_size > 600:
                r.chunk_size, r.chunk_overlap = 600, 100
                why = "smaller chunks so specific facts are not diluted inside long chunks"
            else:
                return None
            return new, "retrieval", before, r.model_dump_json(), why

        if category == "hallucination":
            if not r.require_citation:
                r.require_citation = True
            before, after, why = _patch(llm, defn, "grounding_rules", category, fails, cases)
            new.prompt.grounding_rules = after
            return new, "prompt.grounding_rules + retrieval.require_citation", before, after, why + " (+ answers without citations are now blocked)"

        if category == "wrong_refusal":
            before, after, why = _patch(llm, defn, "refusal_policy", category, fails, cases)
            from .generator import _ensure_refusals  # the fix must not delete required refusals
            new.prompt.refusal_policy = _ensure_refusals(after, defn.must_refuse)
            return new, "prompt.refusal_policy", before, new.prompt.refusal_policy, why

        if category == "prompt_defect":
            oos = [f for f in fails if cases[f.case_id].should_refuse]
            tool = [f for f in fails if cases[f.case_id].kind == "tool"]
            if len(oos) >= max(len(tool), len(fails) - len(oos) - len(tool)):
                before, after, why = _patch(llm, defn, "refusal_policy", category, oos, cases)
                new.prompt.refusal_policy = _ensure_refusals(after, defn.must_refuse)
                return new, "prompt.refusal_policy", before, new.prompt.refusal_policy, why
            if tool and defn.prompt.tool_guidance:
                before, after, why = _patch(llm, defn, "tool_guidance", category, tool, cases)
                new.prompt.tool_guidance = after
                return new, "prompt.tool_guidance", before, after, why
            before, after, why = _patch(llm, defn, "style", category, fails, cases)
            new.prompt.style = after
            return new, "prompt.style", before, after, why
    except LLMError:
        return None
    return None
